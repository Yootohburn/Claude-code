# Beervana — Bangkok New Venue Lead Finder · RUNBOOK

Weekly workflow that finds newly opened Bangkok bars/restaurants, scores them as
craft beer leads, writes `output/leads.csv` + `output/report.html`, DMs a summary
to Slack for approval, then (only after approval) posts to the team channel.

No paid APIs: research uses Claude's built-in web search; Slack goes through the
Slack MCP connector.

---

## 1. How to run it weekly

Just tell Claude:

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
```

First run builds the baseline; from run 2 onward only never-seen venues count as
"new this week".

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
| Thai-Western fusion or international cuisine | +10 |
| Open late (23:00 or later) | +10 |

🔥 threshold: 70+ (`score_hot_threshold`). Hotel/hostel/resort venues are
excluded outright (`exclude_keywords`). Venues older than ~3 months are skipped
at research time unless opening date is unknown AND review count is low
(`low_review_count_threshold`).
