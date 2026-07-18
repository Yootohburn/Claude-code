# Beervana — Bangkok New Venue Lead Finder · RUNBOOK

Weekly workflow that finds newly opened Bangkok bars/restaurants, scores them as
craft beer leads, writes `output/leads.csv` + `output/report.html`, DMs a summary
to Slack for approval, then (only after approval) posts to the team channel.

No paid APIs: research uses Claude's built-in web search; Slack goes through the
Slack MCP connector.

---

## 1. How to run it weekly

**It runs itself**: a Routine ("Beervana lead-finder: weekly run") fires every
**Monday ~09:40 Bangkok time**, does the full research run, and DMs you the
approval summary. You can also trigger it any time by telling Claude:

> **"run the lead finder"**

Claude then:
1. Reads `config.json` and runs the search queries in `search_queries`
   (English + Thai) via web search, plus BK Magazine / Michelin / Time Out /
   Koktail-style roundups.
2. Cross-checks each candidate (Google Maps search link, review count as a
   recency proxy, hotel exclusion).
3. Writes findings to `data/runs/YYYY-MM-DD-raw_venues.json` (same schema as the
   existing run file — copy one entry as a template).
4. Runs the pipeline:
   ```bash
   cd lead-finder
   python3 lead_finder.py ingest data/runs/YYYY-MM-DD-raw_venues.json
   ```
   This dedupes against `data/venues.db` (fuzzy name match), applies the hotel
   filter, scores, and regenerates `output/leads.csv`, `output/report.html`,
   `output/slack_summary.txt`.
5. DMs you the summary and waits for approval (see §4).
6. Commits and pushes so the SQLite memory persists for next week.

Other commands:

```bash
python3 lead_finder.py report                      # regenerate outputs from DB only
python3 lead_finder.py set-status "Sala Saneha" Contacted   # New/Contacted/Meeting/Closed
python3 lead_finder.py log "Sala Saneha" "met GM, wants Vana samples" Meeting "send samples Fri"
python3 lead_finder.py cut "Venue" "reason"        # blacklist a rejected lead
python3 lead_finder.py rescore                     # recompute scores after config changes
```

First run builds the baseline; from run 2 onward only never-seen venues count as
"new this week".

### Follow-up engine

Every report and DM summary includes a **Follow-ups due** section:
- leads in *Contacted*/*Meeting* with no logged touch for `follow_up_days`
  (default 14) days
- *New* leads never contacted after `new_untouched_days` (default 7) days

`log` records a touch (dated note, last-touch date, optional status +
next action), which resets the clock. Log touches straight from Slack DM —
see §4.

## 1b. Rep zones & per-zone coverage

Leads are grouped into **5 sales-rep territories** (B1–B5) defined in
`config.json → zones` by area lists. The report, CSV and Slack summary group by
zone and flag any zone below `coverage.target_leads_per_zone` (default 2), so no
rep's patch goes uncovered.

- **B4** (East/SE: Ekkamai, Phra Khanong, On Nut, Udomsuk, Bangna, Srinakarin,
  Samut Prakan) and **B5** (Nonthaburi, Ratchapruek, Rangsit, Pathum Thani,
  Pak Kret) are set exactly as specified.
- **B1–B3 are PROVISIONAL** (the MyMaps couldn't be read automatically). To
  correct: edit the `areas` list of a zone in `config.json`, then
  `python3 lead_finder.py remap-zones` — it re-maps every venue and regenerates.
- Outer zones (Bangna, Nonthaburi, Rangsit, etc.) are NOT covered by the English
  press — the weekly run must use the **Thai per-zone queries** in each zone's
  `search_terms_th` (Wongnai, Lemon8, Retty, Facebook, Future Park/mall "what's
  new" pages). That is how those zones get filled.
- Freshness = **new-to-DB** (`freshness_mode`): any venue not already in the DB
  and not yet contacted is a valid lead; genuinely just-opened venues also get a
  🆕 flag. This guarantees per-zone volume even where nothing opened this month.

## 1c. Verification — KNOWN WEAK SPOT, read this

**Automated open/closed verification is unreliable in this setup.** Google Maps
(the only real source of truth for "currently open") is network-blocked here, so
the run relies on web signals — and Thai listicles/blog posts are evergreen and
routinely show venues that closed years ago. Venues that slipped through as
"open" but were actually closed 5+ years: The 1925 Brewing, Bros Brew Beers,
Brew Moon, Garden 52, Taproom x Ari. **Treat every lead as UNCONFIRMED until a
human checks Google Maps / calls.** The report shows "☎ confirm open" on every
venue for this reason; there is no "verified open" claim anymore.

Reliable option — NOW INTEGRATED: the **Google Maps scraper**
(gosom/google-maps-scraper). `verify-maps` scrapes each active lead, reads its
Google `business_status`, and **auto-excludes CLOSED venues**, while filling in
real review count, phone and hours.

```bash
bash tools/setup_maps_scraper.sh      # one-time: clone + build the scraper (needs Go)
python3 lead_finder.py verify-maps    # confirm open/closed for all active leads
```

Maps-verified venues then show a green **"✓ open · Google Maps DATE"** badge;
everything else stays **"☎ confirm open"**.

⚠️ **Network requirement:** the scraper must reach Google Maps. Some sandboxes
(including the default cloud environment for the weekly Routine) block Google —
there `verify-maps` exits with a clear message. To make it work:
- **Locally / Docker:** run `verify-maps` (or the scraper's Docker image) on a
  machine with normal internet. Best for a manual weekly pass.
- **In the cloud Routine:** set the environment's network access to **Full**
  (or Custom allowing `google.com,*.google.com,*.googleapis.com`) at
  claude.ai/code — then the weekly run auto-verifies.

Also keep the **customer blocklist** current (`data/customers.txt`); it's
separate from open/closed and already filters existing accounts every run.

### Verification steps the run still performs (best-effort, not proof)

Listicles and old reviews (Wongnai/Lemon8 "best of") include venues that closed
years ago. **A listing is not proof a venue is open.** Before a venue enters the
lead list:

1. Search the venue name + area + a current-status term (`เปิดอยู่ไหม`, `ปิด`,
   `รีวิว 2569`, current year). Look for: recent (this-year) reviews/posts, an
   active Facebook/IG, an opening announcement, or a mall "now open" page.
2. Reject anything with a "permanently closed / ปิดถาวร" signal or no activity
   for 12+ months (hold as unverified rather than presenting it as a lead).
3. Record `"verified": "YYYY-MM-DD"` on the venue (JSON field or set later). The
   report shows a green **✓ open · checked DATE** badge; unverified venues show
   **⚠ verify open/date**.

Note: this environment cannot open Google Maps directly (network-blocked), so
verification is via current web signals; the rep should still confirm on Maps /
by phone before a site visit. If a bad venue slips through, cut it:
`python3 lead_finder.py cut "Name" "permanently closed"` — it's blacklisted and
never resurfaces.

## 2. Connecting the Slack MCP (if not yet connected)

On claude.ai / Claude Code web, enable the **Slack connector** in
Settings → Connectors. On the CLI you can add a Slack MCP server yourself:

```bash
claude mcp add slack -- npx -y @modelcontextprotocol/server-slack
# then set SLACK_BOT_TOKEN / SLACK_TEAM_ID in the env it prompts for
```

Verify with `/mcp` in Claude Code — you should see Slack tools like
`slack_send_message`. Slack IDs used by this project live in `config.json`
(`slack.dm_user_id`, `slack.team_channel_id`).

## 3. Adding manual venues from TikTok / Instagram

The report's watchlist section (and `config.json → hashtag_watchlist`) has ready
hashtag URLs: #bangkoknewbar, #newrestaurantbangkok, #ร้านเปิดใหม่, #บาร์เปิดใหม่,
#คราฟท์เบียร์. Scroll them on your phone; when you spot a new venue:

1. Open `manual_adds.csv` and add a row (see the commented example). `tags` and
   `featured` are `;`-separated; `hours_close` is the 24-h closing hour (24 = midnight, 2 = 2am).
2. Re-run the ingest (or just tell Claude "run the lead finder" — manual adds are
   merged automatically on every ingest and deduped like any other source).

## 4. Approval flow (two-step, channel stays clean)

1. After each run Claude DMs **you** (U06E0DL9Y3D):
   *"🍺 New Leads This Week (X found) — reply 'ok' to post to the team channel"*
   plus the top 10 by score (venue | area | score | source | Maps link, 🔥 = 70+).
2. **Nothing is posted to the channel automatically.**
3. Reply **"ok"** or **"post it"** → Claude posts the same summary to the team
   channel (C0BFZ68S4G7), new venues only.
4. Reply with edits ("remove #3", "add venue X") → Claude applies them and shows
   the revised summary in your DM again before posting.

### Replying in Slack only (no need to open Claude Code)

Slack cannot push your DM reply into a Claude Code session, and constant
polling burns tokens (every wake-up re-reads the whole session context).
So the design avoids any standing loop:

- **Weekly run Routine** (`trig_014AmFZUt9UDAwVCvB2A6oPF`) — Monday ~09:40
  Bangkok: full research run + approval DM.
- **Burst checks** — after each summary DM, Claude arms at most two one-shot
  check-ins (a few hours later, next morning) to catch your Slack reply,
  then stops. Cost: ~3 wake-ups per week instead of 15 per day.
- **On-demand DM command handler** (`trig_01MHyxPUDmL64GEnq4RJoqrk`) — a
  Routine with NO schedule. It runs only when fired, reads the DM, and acts.
  For **instant** Slack-reply handling, wire it to a webhook (one-time setup):
  1. Open https://claude.ai/code/routines → "Beervana lead-finder: DM command
     handler" → edit → Select a trigger → **Add another trigger → API** →
     copy the URL and **Generate token** (shown once).
  2. In Slack **Workflow Builder**, create a workflow triggered by an emoji
     reaction (e.g. you reacting 🍺 in the DM/channel) or a shortcut, with a
     "send a webhook" step: POST to that URL with header
     `Authorization: Bearer <token>` (plus `anthropic-beta:
     experimental-cc-routine-2026-04-01`, `anthropic-version: 2023-06-01`).
     If Workflow Builder can't set headers on your plan, relay through a free
     Make/Zapier webhook instead.
  3. From then on: reply in the DM, tap the reaction, and the handler fires
     within seconds — tokens are spent only when there is real work.

When the handler runs it acts on whatever it finds in the DM:

- "ok" / "post it" → posts the pending summary to the team channel
- "remove #N" / "cut X" / "add venue Y" → applies edits, re-sends revised DM
- "run the lead finder" → kicks off the full weekly run
- sales logging: "contacted Sala Saneha", "meeting with Silo Friday, bring
  Moretti samples", "closed Hannibal", "note Liana: GM is Khun Ploy" →
  recorded via `lead_finder.py log` (status + dated note + next action),
  which feeds the follow-up engine
- no reply → does nothing, silently

So a Slack-only reply is acted on within the hour. Typing in the Claude Code
session is still the instant path. Manage the Routine from the session
("pause/delete the approval poller") if it's ever noisy.

## 5. Files

| Path | What it is |
|---|---|
| `config.json` | Target areas, scoring weights, hot threshold, Slack IDs, search queries, hashtag watchlist |
| `lead_finder.py` | Pipeline: ingest → filter → fuzzy dedupe → score → outputs |
| `manual_adds.csv` | Your TikTok/IG manual finds (merged every run) |
| `data/venues.db` | SQLite memory of every venue ever seen (commit it — it IS the dedupe baseline) |
| `data/runs/*.json` | Raw researched venues per run |
| `output/leads.csv` | venue, area, source, date found, Maps link, phone, score, status |
| `output/report.html` | Dark dashboard: new-this-week on top, grouped by area, sorted by score |
| `output/slack_summary.txt` | Exact text DM'd for approval |

## 6. Scoring (0–100)

| Signal | Points |
|---|---|
| Craft beer / beer garden / gastropub / taproom concept | +30 |
| else: cocktail bar / wine bar / pub / drinks-led bistro | +20 |
| Located in Thonglor / Ekkamai / Ari | +15 |
| Featured in Michelin Guide or BK Magazine | +15 |
| Portfolio fit — Vana (craft), Erdinger (German weissbier), Birra Moretti (Italian): italian / german / european / mediterranean / tapas / aperitivo / beer garden concepts | +15 |
| Thai-Western fusion or international cuisine | +10 |
| Open late (23:00 or later) | +10 |
| Poor market fit (local Thai band-pub, mor lam / luk thung) | −20 |

Portfolio brands live in `config.json → portfolio`; tune `portfolio_tags` /
`poor_fit_tags` as the brand book evolves, then run
`python3 lead_finder.py rescore` to recompute all scores. To drop a lead the
team rejects: `python3 lead_finder.py cut "Venue Name" "reason"` (it stays in
the DB as excluded so it never resurfaces).

🔥 threshold: 70+ (`score_hot_threshold`). Hotel/hostel/resort venues are
excluded outright (`exclude_keywords`). Venues older than ~3 months are skipped
at research time unless opening date is unknown AND review count is low
(`low_review_count_threshold`).
