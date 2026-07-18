#!/usr/bin/env python3
"""Google Maps verification for the Beervana lead finder.

Uses the gosom/google-maps-scraper binary to get ground-truth business data for
venues (open/closed status, review count, phone, hours) so we stop relying on
undated web listicles. Requires network access to Google Maps.

Invoked via:  python3 lead_finder.py verify-maps
Build the scraper first:  bash tools/setup_maps_scraper.sh
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import lead_finder as lf

ROOT = Path(__file__).resolve().parent
MAPS_OUT = ROOT / "maps-output"


def _cfg() -> dict:
    return lf.CONFIG.get("maps_scraper", {})


def _binary() -> Path:
    return (ROOT / _cfg().get("binary", "tools/google-maps-scraper/gms")).resolve()


def run_scraper(queries: list[str]) -> list[dict]:
    """Run the scraper on the given queries; return parsed JSON entries."""
    binary = _binary()
    if not binary.exists():
        sys.exit(f"Scraper binary not found at {binary}\n"
                 f"Build it first:  bash tools/setup_maps_scraper.sh")
    MAPS_OUT.mkdir(exist_ok=True)
    cfg = _cfg()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as qf:
        qf.write("\n".join(queries) + "\n")
        qpath = qf.name
    out = MAPS_OUT / f"results-{date.today().isoformat()}.json"
    cmd = [str(binary), "-input", qpath, "-json", "-results", str(out),
           "-depth", str(cfg.get("depth", 1)),
           "-c", str(cfg.get("concurrency", 2)),
           "-lang", cfg.get("lang", "en"),
           "-exit-on-inactivity", cfg.get("exit_on_inactivity", "3m")]
    print("Running:", " ".join(cmd))
    env = dict(os.environ)
    # playwright.azureedge.net was retired by Microsoft (404s since 2025);
    # point playwright-go's driver download at the current CDN.
    env.setdefault("PLAYWRIGHT_DOWNLOAD_HOST",
                   "https://cdn.playwright.dev/dbazure/download/playwright")
    try:
        subprocess.run(cmd, check=True, timeout=1800, env=env)
    except subprocess.CalledProcessError as e:
        sys.exit(f"Scraper failed (exit {e.returncode}). If this is a network "
                 f"sandbox, Google Maps may be blocked — run where Maps is reachable.")
    except subprocess.TimeoutExpired:
        print("Scraper timed out; parsing whatever was written.")
    return parse_results(out)


def parse_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:                       # JSON array
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:  # JSONL fallback
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return rows


def _closing_hour(open_hours) -> int | None:
    """Best-effort extraction of a closing hour (24h int) from open_hours."""
    if not isinstance(open_hours, dict):
        return None
    import re
    best = None
    for spans in open_hours.values():
        for span in spans if isinstance(spans, list) else [spans]:
            for m in re.finditer(r"(\d{1,2})(?::\d{2})?\s*(AM|PM)?", str(span)):
                h = int(m.group(1)) % 12
                if (m.group(2) or "").upper() == "PM":
                    h += 12
                if best is None or h == 0 or (0 < h < 6) or h > best:
                    best = h if h else 24
    return best


def verify_active_leads() -> None:
    """Scrape each active lead, update DB with Maps truth, exclude CLOSED ones."""
    con = lf.db_connect()
    lf.backfill_zones(con)
    leads = list(con.execute("SELECT * FROM venues WHERE excluded=0"))
    if not leads:
        print("No active leads to verify.")
        return
    queries = [f"{r['name']} {r['area'] or ''} Bangkok".strip() for r in leads]
    entries = run_scraper(queries)
    print(f"Scraper returned {len(entries)} place(s).")

    today = date.today().isoformat()
    thr = _cfg().get("match_threshold", 0.6)
    closed = updated = notfound = 0
    for r in leads:
        vn = lf.norm_name(r["name"])
        best, bestscore = None, 0.0
        for e in entries:
            title = e.get("title", "")
            s = SequenceMatcher(None, vn, lf.norm_name(title)).ratio()
            if s > bestscore:
                best, bestscore = e, s
        if not best or bestscore < thr:
            notfound += 1
            con.execute("UPDATE venues SET notes=? WHERE id=?",
                        ((r["notes"] or "") + f"\n[{today}] maps: no confident match", r["id"]))
            continue
        status = (best.get("status") or "").upper()
        if "CLOSED" in status and "TEMPORARILY" not in status:
            con.execute("UPDATE venues SET excluded=1, exclude_reason=? WHERE id=?",
                        (f"CLOSED per Google Maps (verify-maps {today})", r["id"]))
            closed += 1
            print(f"  CLOSED: {r['name']}")
            continue
        rc = best.get("review_count") or None
        phone = best.get("phone") or r["phone"]
        ch = _closing_hour(best.get("open_hours")) or (
            int(r["hours_close"]) if str(r["hours_close"]).isdigit() else None)
        con.execute(
            "UPDATE venues SET verified=?, review_count=?, phone=?, hours_close=?, "
            "maps_link=? WHERE id=?",
            (f"maps:{today}", rc, phone, str(ch or ""),
             best.get("link") or r["maps_link"], r["id"]))
        updated += 1
    con.commit()
    con.close()
    print(f"\nMaps verify {today}: {updated} confirmed open, {closed} closed & excluded, "
          f"{notfound} no-match.")
    lf.regenerate(today)


if __name__ == "__main__":
    verify_active_leads()
