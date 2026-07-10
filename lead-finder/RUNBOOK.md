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

Slack cannot push your DM reply into a Claude Code session — there is no
Slack-event → session trigger today, and the @Claude Slack app starts separate
channel-based sessions with none of this project's context. Instead, a
**Routine** ("Beervana lead-finder: Slack DM approval poller",
`trig_01V3CgC4TNtzV3pfbQJRDEXD`) wakes this session **hourly at :03,
09:00–23:00 Bangkok time**, reads the DM, and acts on whatever it finds
(a second Routine, "Beervana lead-finder: weekly run"
`trig_014AmFZUt9UDAwVCvB2A6oPF`, fires the full research run every Monday
~09:40 Bangkok):

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
