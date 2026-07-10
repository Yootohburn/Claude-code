#!/usr/bin/env python3
"""Beervana — Bangkok New Venue Lead Finder.

Pipeline: ingest researched venues (JSON) + manual adds (CSV)
  -> hotel/area filters -> fuzzy dedupe against SQLite memory
  -> score for craft beer fit -> leads.csv + report.html + slack_summary.txt

Usage:
  python3 lead_finder.py ingest data/runs/2026-07-10-raw_venues.json
  python3 lead_finder.py report            # regenerate outputs from DB only
  python3 lead_finder.py set-status "Venue Name" Contacted
"""

import csv
import html
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DB_PATH = ROOT / "data" / "venues.db"
OUT_DIR = ROOT / "output"
MANUAL_CSV = ROOT / "manual_adds.csv"

STATUSES = ["New", "Contacted", "Meeting", "Closed"]


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).lower()
    s = re.sub(r"[^\w\s฀-๿]", " ", s)
    stop = {"the", "bangkok", "bkk", "bar", "cafe", "restaurant", "at", "rooftop", "by"}
    words = [w for w in s.split() if w not in stop]
    return " ".join(words) or s.strip()


def is_hotel_venue(v: dict) -> bool:
    hay = f"{v.get('name', '')} {v.get('address', '')}".lower()
    return any(k in hay for k in CONFIG["exclude_keywords"])


def maps_link(v: dict) -> str:
    if v.get("maps_link"):
        return v["maps_link"]
    q = quote_plus(f"{v['name']} {v.get('area', '')} Bangkok")
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def score_venue(v: dict) -> tuple[int, list[str]]:
    s = CONFIG["scoring"]
    tags = {t.strip().lower() for t in v.get("tags", []) if t.strip()}
    concept = v.get("concept", "").lower()
    hay = " ".join(tags) + " " + concept
    score, reasons = 0, []

    if any(t in hay for t in s["craft_tags"]):
        score += s["craft_beer_concept"]
        reasons.append(f"craft/beer concept +{s['craft_beer_concept']}")
    elif any(t in hay for t in s["drinks_tags"]):
        score += s["drinks_led"]
        reasons.append(f"drinks-led +{s['drinks_led']}")

    if v.get("area", "").strip().title() in CONFIG["priority_areas"]:
        score += s["priority_area"]
        reasons.append(f"priority area +{s['priority_area']}")

    featured = {f.lower() for f in v.get("featured", [])}
    if any(src.lower() in featured for src in s["featured_sources"]):
        score += s["featured_press"]
        reasons.append(f"featured press +{s['featured_press']}")

    if any(t in hay for t in s.get("portfolio_tags", [])):
        score += s.get("portfolio_fit", 0)
        reasons.append(f"portfolio fit (Vana/Erdinger/Moretti) +{s.get('portfolio_fit', 0)}")

    if any(t in hay for t in s.get("poor_fit_tags", [])):
        score += s.get("poor_fit_penalty", 0)
        reasons.append(f"poor market fit {s.get('poor_fit_penalty', 0)}")

    if any(t in hay for t in s["fusion_tags"]):
        score += s["fusion_international"]
        reasons.append(f"international/fusion +{s['fusion_international']}")

    close_h = v.get("hours_close")
    if close_h is not None and (int(close_h) >= s["open_late_hour"] or int(close_h) < 6):
        score += s["open_late"]
        reasons.append(f"open late +{s['open_late']}")

    return max(0, min(score, 100)), reasons


def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS venues (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        norm_name TEXT NOT NULL,
        area TEXT, address TEXT, concept TEXT, tags TEXT,
        source TEXT, source_url TEXT, maps_link TEXT, phone TEXT,
        opening_date TEXT, hours_close TEXT, featured TEXT, notes TEXT,
        score INTEGER DEFAULT 0, score_reasons TEXT,
        status TEXT DEFAULT 'New',
        first_seen TEXT, excluded INTEGER DEFAULT 0, exclude_reason TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS runs (
        run_date TEXT PRIMARY KEY, ingested INTEGER, new_leads INTEGER,
        duplicates INTEGER, excluded INTEGER
    )""")
    existing = {r[1] for r in con.execute("PRAGMA table_info(venues)")}
    for col, decl in [("instagram", "TEXT"), ("review_count", "INTEGER"),
                      ("last_touch", "TEXT"), ("next_action", "TEXT")]:
        if col not in existing:
            con.execute(f"ALTER TABLE venues ADD COLUMN {col} {decl}")
    return con


def days_between(older: str, newer: str) -> int:
    try:
        return (date.fromisoformat(newer) - date.fromisoformat(older)).days
    except (ValueError, TypeError):
        return 0


def follow_ups_due(leads: list[sqlite3.Row], run_date: str) -> list[tuple[sqlite3.Row, int, str]]:
    """Leads that need attention: in-pipeline gone quiet, or New never contacted."""
    due = []
    for r in leads:
        last = r["last_touch"] or r["first_seen"]
        days = days_between(last, run_date)
        if r["status"] in ("Contacted", "Meeting") and days >= CONFIG["follow_up_days"]:
            due.append((r, days, f"{r['status'].lower()}, {days}d silent"))
        elif r["status"] == "New" and days >= CONFIG["new_untouched_days"]:
            due.append((r, days, f"never contacted, found {days}d ago"))
    return sorted(due, key=lambda t: (-t[0]["score"], -t[1]))


def find_duplicate(con: sqlite3.Connection, nname: str):
    threshold = CONFIG["fuzzy_match_threshold"]
    ntokens = set(nname.split())
    for row in con.execute("SELECT id, name, norm_name FROM venues"):
        if row["norm_name"] == nname:
            return row
        if SequenceMatcher(None, row["norm_name"], nname).ratio() >= threshold:
            return row
        rtokens = set(row["norm_name"].split())
        # "sala saneha" vs "sala saneha silom": one name contained in the other
        if len(ntokens & rtokens) >= 2 and (ntokens <= rtokens or rtokens <= ntokens):
            return row
    return None


def load_manual_adds() -> list[dict]:
    if not MANUAL_CSV.exists():
        return []
    venues = []
    with MANUAL_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            if not name or name.startswith("#"):
                continue
            venues.append({
                "name": name,
                "area": (row.get("area") or "").strip(),
                "address": (row.get("address") or "").strip(),
                "concept": (row.get("concept") or "").strip(),
                "tags": [t for t in (row.get("tags") or "").split(";") if t.strip()],
                "source": (row.get("source") or "Manual (TikTok/IG)").strip(),
                "source_url": (row.get("source_url") or "").strip(),
                "opening_date": (row.get("opening_date") or "").strip(),
                "phone": (row.get("phone") or "").strip(),
                "hours_close": int(row["hours_close"]) if (row.get("hours_close") or "").strip().isdigit() else None,
                "featured": [t for t in (row.get("featured") or "").split(";") if t.strip()],
                "notes": (row.get("notes") or "").strip(),
            })
    return venues


def ingest(raw_path: Path, run_date: str) -> dict:
    venues = json.loads(raw_path.read_text(encoding="utf-8"))
    venues += load_manual_adds()
    con = db_connect()
    stats = {"ingested": len(venues), "new": 0, "dup": 0, "excluded": 0}

    for v in venues:
        nname = norm_name(v["name"])
        dup = find_duplicate(con, nname)
        if dup:
            stats["dup"] += 1
            continue
        excluded, reason = 0, ""
        if is_hotel_venue(v):
            excluded, reason = 1, "hotel/hostel/resort keyword"
            stats["excluded"] += 1
        score, reasons = score_venue(v)
        con.execute(
            """INSERT INTO venues (name, norm_name, area, address, concept, tags,
               source, source_url, maps_link, phone, opening_date, hours_close,
               featured, notes, score, score_reasons, status, first_seen,
               excluded, exclude_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (v["name"], nname, v.get("area", ""), v.get("address", ""),
             v.get("concept", ""), ";".join(v.get("tags", [])),
             v.get("source", ""), v.get("source_url", ""), maps_link(v),
             v.get("phone", ""), v.get("opening_date", ""),
             str(v.get("hours_close") or ""), ";".join(v.get("featured", [])),
             v.get("notes", ""), score, "; ".join(reasons), "New", run_date,
             excluded, reason))
        if v.get("instagram") or v.get("review_count") is not None:
            con.execute(
                "UPDATE venues SET instagram=?, review_count=? WHERE norm_name=?",
                (v.get("instagram", ""), v.get("review_count"), nname))
        if not excluded:
            stats["new"] += 1

    con.execute(
        "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)",
        (run_date, stats["ingested"], stats["new"], stats["dup"], stats["excluded"]))
    con.commit()
    return stats


def fetch_leads(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT * FROM venues WHERE excluded=0 ORDER BY score DESC, name"))


def write_csv(leads: list[sqlite3.Row]) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    with (OUT_DIR / "leads.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["venue name", "area", "source", "date found",
                    "google maps link", "phone", "score", "status",
                    "instagram", "last touch", "next action"])
        for r in leads:
            w.writerow([r["name"], r["area"], r["source"], r["first_seen"],
                        r["maps_link"], r["phone"], r["score"], r["status"],
                        r["instagram"] or "", r["last_touch"] or "",
                        r["next_action"] or ""])


def slack_summary(leads: list[sqlite3.Row], run_date: str) -> str:
    new = [r for r in leads if r["first_seen"] == run_date]
    hot = CONFIG["score_hot_threshold"]
    lines = [f"🍺 *New Leads This Week ({len(new)} found)* — reply 'ok' to post to the team channel", ""]
    for r in sorted(new, key=lambda r: -r["score"])[:10]:
        fire = "🔥 " if r["score"] >= hot else ""
        lines.append(f"{fire}*{r['name']}* | {r['area'] or 'TBC'} | {r['score']} | "
                     f"{r['source']} | <{r['maps_link']}|Maps>")
    due = follow_ups_due(leads, run_date)
    if due:
        lines += ["", f"⏰ *Follow-ups due ({len(due)})*"]
        for r, _days, why in due[:5]:
            lines.append(f"• {r['name']} ({r['area'] or 'TBC'}, {r['score']}) — {why}")
        if len(due) > 5:
            lines.append(f"…and {len(due) - 5} more in the report")
    text = "\n".join(lines)
    (OUT_DIR / "slack_summary.txt").write_text(text, encoding="utf-8")
    return text


def write_report(con: sqlite3.Connection, leads: list[sqlite3.Row], run_date: str) -> None:
    hot = CONFIG["score_hot_threshold"]
    new = [r for r in leads if r["first_seen"] == run_date]
    areas: dict[str, list[sqlite3.Row]] = {}
    for r in leads:
        areas.setdefault(r["area"] or "Area TBC", []).append(r)

    def esc(s):
        return html.escape(str(s or ""))

    def bar(score):
        pct = max(4, score)
        cls = "hot" if score >= hot else ""
        return (f'<div class="scorebar"><div class="scoreval">{score}</div>'
                f'<div class="track"><div class="fill {cls}" style="width:{pct}%"></div></div></div>')

    def row_html(r):
        fire = "🔥 " if r["score"] >= hot else ""
        feat = f'<span class="chip">{esc(r["featured"].replace(";", ", "))}</span>' if r["featured"] else ""
        if not r["opening_date"]:
            feat += ' <span class="chip warn">⚠ verify date</span>'
        ig = (f' · <a href="https://www.instagram.com/{esc(r["instagram"]).lstrip("@")}/"'
              f' target="_blank">@{esc(r["instagram"]).lstrip("@")}</a>') if r["instagram"] else ""
        touch = f'<div class="sub">last touch {esc(r["last_touch"])}</div>' if r["last_touch"] else ""
        return f"""<tr>
<td class="vname">{fire}{esc(r['name'])}<div class="sub">{esc(r['concept'])}{ig}</div>{touch}</td>
<td>{esc(r['area'] or 'TBC')}</td>
<td>{bar(r['score'])}</td>
<td>{esc(r['source'])} {feat}</td>
<td>{esc(r['first_seen'])}</td>
<td>{esc(r['phone']) or '—'}</td>
<td><span class="status s-{esc(r['status']).lower()}">{esc(r['status'])}</span></td>
<td><a href="{esc(r['maps_link'])}" target="_blank">Maps ↗</a></td>
</tr>"""

    def table(rows):
        body = "\n".join(row_html(r) for r in rows)
        return f"""<div class="tablewrap"><table>
<thead><tr><th>Venue</th><th>Area</th><th>Craft-fit score</th><th>Source</th>
<th>Found</th><th>Phone</th><th>Status</th><th>Map</th></tr></thead>
<tbody>{body}</tbody></table></div>"""

    area_sections = ""
    for area in sorted(areas, key=lambda a: -max(r["score"] for r in areas[a])):
        rows = areas[area]
        area_sections += (f'<section><h2>{esc(area)} '
                          f'<span class="count">{len(rows)} venue{"s" if len(rows) != 1 else ""}</span></h2>'
                          f'{table(rows)}</section>')

    tiktok = "".join(f'<li><a href="{u}" target="_blank">{esc(u)}</a></li>'
                     for u in CONFIG["hashtag_watchlist"]["tiktok"])
    insta = "".join(f'<li><a href="{u}" target="_blank">{esc(u)}</a></li>'
                    for u in CONFIG["hashtag_watchlist"]["instagram"])
    hot_count = sum(1 for r in leads if r["score"] >= hot)
    excluded_count = con.execute("SELECT COUNT(*) c FROM venues WHERE excluded=1").fetchone()["c"]
    pipeline_count = sum(1 for r in leads if r["status"] in ("Contacted", "Meeting"))
    due = follow_ups_due(leads, run_date)

    due_section = ""
    if due:
        due_rows = "".join(
            f'<li><b>{esc(r["name"])}</b> ({esc(r["area"] or "TBC")}, score {r["score"]}) '
            f'— {esc(why)}</li>' for r, _d, why in due)
        due_section = (f'<div class="newweek due"><h2>⏰ Follow-ups due ({len(due)})</h2>'
                       f'<ul class="duelist">{due_rows}</ul></div>')

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Beervana Lead Finder — {run_date}</title>
<style>
:root {{
  --bg:#101014; --surface:#17171d; --surface2:#1e1e26; --line:#2a2a35;
  --ink:#e8e6e3; --ink2:#a9a7b0; --muted:#77747f;
  --amber:#e8a33d; --amber-soft:#8a6425; --hot:#e4693d; --link:#7fb4e6;
}}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system,'Segoe UI',Roboto,'Noto Sans Thai',sans-serif; padding:32px 24px 64px; max-width:1080px; margin:0 auto; }}
h1 {{ font-size:24px; letter-spacing:.2px; }}
h1 .beer {{ color:var(--amber); }}
.meta {{ color:var(--ink2); margin:4px 0 24px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:32px; }}
.tile {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.tile .n {{ font-size:26px; font-weight:650; }}
.tile .l {{ color:var(--ink2); font-size:12.5px; margin-top:2px; }}
section {{ margin-bottom:28px; }}
h2 {{ font-size:16px; margin-bottom:10px; color:var(--ink); }}
h2 .count {{ color:var(--muted); font-weight:400; font-size:13px; }}
.newweek {{ border:1px solid var(--amber-soft); border-radius:12px; padding:18px; background:linear-gradient(180deg,#1d1a12,var(--surface)); margin-bottom:32px; }}
.newweek h2 {{ color:var(--amber); }}
.tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:10px; background:var(--surface); }}
table {{ border-collapse:collapse; width:100%; min-width:820px; }}
th {{ text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); padding:10px 12px; border-bottom:1px solid var(--line); }}
td {{ padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
tr:last-child td {{ border-bottom:none; }}
tr:hover td {{ background:var(--surface2); }}
.vname {{ font-weight:600; }}
.sub {{ color:var(--muted); font-weight:400; font-size:12.5px; max-width:260px; }}
.scorebar {{ display:flex; align-items:center; gap:8px; min-width:130px; }}
.scoreval {{ width:26px; text-align:right; font-variant-numeric:tabular-nums; }}
.track {{ flex:1; height:6px; background:var(--surface2); border-radius:4px; overflow:hidden; }}
.fill {{ height:100%; background:var(--amber); border-radius:4px; }}
.fill.hot {{ background:var(--hot); }}
.chip {{ background:var(--surface2); border:1px solid var(--line); border-radius:20px; padding:1px 8px; font-size:11.5px; color:var(--ink2); }}
.chip.warn {{ color:var(--amber); border-color:var(--amber-soft); }}
.newweek.due {{ border-color:#7a4a35; background:linear-gradient(180deg,#1d1512,var(--surface)); }}
.newweek.due h2 {{ color:var(--hot); }}
.duelist {{ list-style:none; }}
.duelist li {{ margin:6px 0; color:var(--ink2); }}
.duelist b {{ color:var(--ink); }}
.status {{ border-radius:20px; padding:2px 9px; font-size:12px; border:1px solid var(--line); }}
.s-new {{ color:var(--amber); border-color:var(--amber-soft); }}
.s-contacted {{ color:var(--link); }}
.s-meeting {{ color:#9ac97f; }}
.s-closed {{ color:var(--muted); }}
a {{ color:var(--link); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.watch {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
.watch .card {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.watch h3 {{ font-size:13.5px; margin-bottom:8px; color:var(--ink2); }}
.watch ul {{ list-style:none; }}
.watch li {{ margin:4px 0; font-size:13px; overflow-wrap:anywhere; }}
footer {{ color:var(--muted); font-size:12.5px; margin-top:36px; }}
</style></head><body>
<h1><span class="beer">🍺 Beervana</span> — Bangkok New Venue Lead Finder</h1>
<div class="meta">Run of {run_date} · scores 0–100 for craft beer fit · 🔥 = {hot}+</div>

<div class="tiles">
  <div class="tile"><div class="n">{len(new)}</div><div class="l">New this week</div></div>
  <div class="tile"><div class="n">{len(leads)}</div><div class="l">Active leads (all time)</div></div>
  <div class="tile"><div class="n">{hot_count}</div><div class="l">Hot (score {hot}+)</div></div>
  <div class="tile"><div class="n">{pipeline_count}</div><div class="l">In pipeline (Contacted/Meeting)</div></div>
  <div class="tile"><div class="n">{len(due)}</div><div class="l">Follow-ups due</div></div>
  <div class="tile"><div class="n">{excluded_count}</div><div class="l">Excluded (hotel/cut)</div></div>
</div>

{due_section}

<div class="newweek">
<h2>🆕 New this week — {run_date}</h2>
{table(sorted(new, key=lambda r: -r["score"])) if new else "<p>No new venues this run.</p>"}
</div>

{area_sections}

<section><h2>📱 TikTok / Instagram watchlist (manual review → manual_adds.csv)</h2>
<div class="watch">
  <div class="card"><h3>TikTok hashtags</h3><ul>{tiktok}</ul></div>
  <div class="card"><h3>Instagram hashtags</h3><ul>{insta}</ul></div>
</div></section>

<footer>Generated by lead_finder.py · data in data/venues.db · statuses: New → Contacted → Meeting → Closed</footer>
</body></html>"""
    (OUT_DIR / "report.html").write_text(page, encoding="utf-8")


def regenerate(run_date: str) -> None:
    con = db_connect()
    leads = fetch_leads(con)
    write_csv(leads)
    write_report(con, leads, run_date)
    print(slack_summary(leads, run_date))
    con.close()


def main() -> None:
    today = date.today().isoformat()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "ingest":
        raw = Path(sys.argv[2])
        run_date = sys.argv[3] if len(sys.argv) > 3 else today
        stats = ingest(raw, run_date)
        print(f"Ingested {stats['ingested']} | new {stats['new']} | "
              f"duplicates skipped {stats['dup']} | hotel-excluded {stats['excluded']}")
        regenerate(run_date)
    elif cmd == "report":
        con = db_connect()
        last = con.execute("SELECT MAX(run_date) d FROM runs").fetchone()["d"]
        con.close()
        regenerate(last or today)
    elif cmd == "rescore":
        con = db_connect()
        for r in con.execute("SELECT * FROM venues"):
            v = {"name": r["name"], "area": r["area"], "concept": r["concept"],
                 "tags": r["tags"].split(";") if r["tags"] else [],
                 "featured": r["featured"].split(";") if r["featured"] else [],
                 "hours_close": int(r["hours_close"]) if str(r["hours_close"]).isdigit() else None}
            score, reasons = score_venue(v)
            con.execute("UPDATE venues SET score=?, score_reasons=? WHERE id=?",
                        (score, "; ".join(reasons), r["id"]))
        con.commit()
        con.close()
        print("Rescored all venues with current config.")
        regenerate(today if len(sys.argv) < 3 else sys.argv[2])
    elif cmd == "cut":
        name = sys.argv[2]
        reason = sys.argv[3] if len(sys.argv) > 3 else "manual cut (market fit)"
        con = db_connect()
        n = con.execute("UPDATE venues SET excluded=1, exclude_reason=? WHERE name LIKE ?",
                        (reason, f"%{name}%")).rowcount
        con.commit()
        con.close()
        print(f"Cut {n} venue(s): {name}")
    elif cmd == "set-status":
        name, status = sys.argv[2], sys.argv[3].title()
        if status not in STATUSES:
            sys.exit(f"Status must be one of {STATUSES}")
        con = db_connect()
        n = con.execute(
            "UPDATE venues SET status=?, last_touch=? WHERE name LIKE ?",
            (status, today, f"%{name}%")).rowcount
        con.commit()
        con.close()
        print(f"Updated {n} venue(s) to {status}")
    elif cmd == "log":
        # log "name" "note" [status] [next-action] — records a sales touch
        name, note = sys.argv[2], sys.argv[3]
        status = sys.argv[4].title() if len(sys.argv) > 4 else None
        nxt = sys.argv[5] if len(sys.argv) > 5 else None
        if status and status not in STATUSES:
            sys.exit(f"Status must be one of {STATUSES}")
        con = db_connect()
        row = con.execute("SELECT id, notes, status FROM venues WHERE name LIKE ?",
                          (f"%{name}%",)).fetchone()
        if not row:
            sys.exit(f"No venue matching {name!r}")
        notes = (row["notes"] + "\n" if row["notes"] else "") + f"[{today}] {note}"
        con.execute(
            "UPDATE venues SET notes=?, last_touch=?, status=?, next_action=? WHERE id=?",
            (notes, today, status or row["status"], nxt, row["id"]))
        con.commit()
        con.close()
        print(f"Logged touch on venue #{row['id']} ({today})"
              + (f", status → {status}" if status else ""))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
