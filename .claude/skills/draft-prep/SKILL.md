---
name: draft-prep
description: Run the pre-season fantasy football draft preparation workflow. Generates preseason projections from historical data, fetches live ADP from Sleeper or FantasyPros, computes value scores, and launches the interactive draft assistant. Use in the weeks before an NFL draft (typically August).
argument-hint: "[season] [scoring] [my-pick] [teams]"
allowed-tools: Bash, Read, mcp__sleeper__*, mcp__fetch__fetch
---

Run the complete pre-season fantasy football draft preparation workflow.

## Arguments
`$ARGUMENTS` — parsed as: `[season] [scoring] [my-pick] [teams]`
- Defaults: season=2026, scoring=half_ppr, my-pick=1, teams=12
- Scoring options: ppr, half_ppr, standard

## Current projection files
!`cd /Users/georgesmith/repos/nfl_data_engineering && ls output/projections/ 2>/dev/null | grep -i preseason | tail -5 || echo "No preseason projections yet"`

## Steps

### Step 1 — Check for existing preseason projections
If a recent preseason projections CSV exists in `output/projections/`, offer to use it or regenerate.

### Step 2 — Generate preseason projections (if needed)
```bash
source venv/bin/activate && python scripts/generate_projections.py \
  --preseason \
  --season SEASON \
  --scoring SCORING \
  --output both
```
This fetches 2 seasons of historical data from nfl-data-py and produces ranked projections.

### Step 3 — Fetch ADP data (use MCP, then save to data/adp.csv)

**Option A — Sleeper MCP (preferred, always current):**
Use the sleeper MCP to fetch current ADP rankings. Call the Sleeper trending/ADP endpoints to get player draft positions, then save to `data/adp.csv` with columns `player_name,adp_rank`.

**Option B — fetch MCP (FantasyPros fallback):**
Use the fetch MCP to retrieve the FantasyPros consensus ADP page and parse player rankings:
- URL: `https://www.fantasypros.com/nfl/adp/overall.php`
- Extract player name and ADP rank from the rankings table
- Save to `data/adp.csv`

After saving ADP data, confirm row count and show the top 10 ADP players.

### Step 4 — Show pre-draft summary
After projections and ADP are loaded, display:
- Top 30 overall players by model rank vs ADP rank
- Top 5 per position (QB/RB/WR/TE)
- Top 10 undervalued players (model rank >> ADP rank)
- Top 5 overvalued players to avoid (ADP rank >> model rank)
- Positional depth: how many viable starters at each position

### Step 5 — Launch interactive draft assistant
```bash
source venv/bin/activate && python scripts/draft_assistant.py \
  --scoring SCORING \
  --teams TEAMS \
  --my-pick MY_PICK \
  --season SEASON \
  --projections-file output/projections/LATEST_PROJECTION_FILE \
  --adp-file data/adp.csv
```

## Draft assistant quick-reference
Once the draft starts, remind the user of key commands:
- `rec` — get pick recommendations for your turn
- `pick <name>` — you draft this player
- `draft <name>` — another team drafted this player
- `best [QB/RB/WR/TE]` — best available by position
- `undervalued` — players the model likes more than ADP
- `roster` — see your current roster
- `undo` — undo your last pick

## Notes
- Sleeper MCP gives real-time ADP; re-run Step 3 on draft day for the most current data
- Best run 1–2 weeks before draft day so projections reflect final depth charts
- Re-run after major injuries or trades to refresh rankings
- Save the draft results for season-long reference
