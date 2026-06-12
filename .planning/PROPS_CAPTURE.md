# Props Capture — Build Notes

*Built 2026-06-12. Extends .planning/PROP_IMPLIED_DECISION.md decision.*

## What was built

**`scripts/bronze_props_ingestion.py`** — sibling script to `bronze_odds_api_ingestion.py`:

1. Fetches the free `/v4/sports/americanfootball_nfl/events` list (0 credits).
2. Filters events to those commencing within `--days-ahead` days (default 7).
3. Estimates credit cost (`events × markets × regions`); aborts if over `--max-credits` (default 60).
4. Per-event: calls `/v4/sports/americanfootball_nfl/events/{id}/odds` for each in-window game.
5. Mid-run reserve guard: stops if `x-requests-remaining` drops to or below 50 (protects spreads cron).
6. Normalises two API response shapes:
   - **Binary** (e.g. `player_anytime_td`): `name="Yes"`, `description=<player>`, single `price` → `price_over`, `price_under=None`, `line=None`.
   - **Over/under** (e.g. `player_reception_yds`): paired `Over`/`Under` outcomes by player description → `price_over`, `price_under`, `line=<point>`.
7. Writes to `data/bronze/odds_api/props/season=YYYY/props_YYYYMMDD_HHMMSS.parquet`.

Reuses `ODDS_API_TO_NFLVERSE`, `infer_nfl_season`, `log_quota` from the spreads script.

**`tests/test_bronze_props_ingestion.py`** — 56 tests (all passing):
- `estimate_credits` × 5
- `filter_events_by_window` × 8
- `normalize_event_props` binary × 11
- `normalize_event_props` over/under × 5
- `normalize_event_props` edge cases × 6
- `normalize_props_response` × 5
- `write_props_parquet` × 4
- `run_props` credit guard × 3
- `run_props` mid-run reserve guard × 1
- `run_props` fail-open × 3
- `run_props` dry-run × 2
- `run_props` round-trip × 3

**`.github/workflows/odds-capture.yml`** — added Sunday 14:00 UTC cron trigger and `capture-props` job with:
- `--days-ahead 7 --max-credits 60`
- Same git commit + rebase-retry pattern as the spreads job
- Guard: only runs on Sunday cron (`0 14 * * 0`) or `workflow_dispatch`

## Credit math

| Component | Credits/run | Runs/month | Credits/month |
|-----------|-------------|------------|---------------|
| Events list | 0 | 4–5 (Sundays) | 0 |
| Per-event props call | `markets × regions` per event | — | — |
| Default config (5 markets, ~5 in-window events, region=us) | 5 × 5 × 1 = 25 | 4–5 | 100–125 |
| Spreads cron (existing) | ~2/run | 60/month | ~120 |
| **Total combined** | — | — | **~220–245** |
| Free tier budget | — | — | 500 |
| Headroom | — | — | ~255 |

Near-game weeks (week 1 SNF primetime week) may have 12–16 events in window:
`16 events × 5 markets = 80 credits/run` — still under the 500/month budget at 4 Sundays.
The `--max-credits 60` default will abort an unusually large week; raise to 120 for playoffs.

## Schema

Output: `data/bronze/odds_api/props/season=YYYY/props_YYYYMMDD_HHMMSS.parquet`

| Column | Type | Notes |
|--------|------|-------|
| `snapshot_ts` | str | UTC ISO-8601 when the snapshot was taken |
| `event_id` | str | The Odds API event id |
| `commence_time` | str | ISO-8601 UTC kickoff |
| `home_team` | str | Full team name (API canonical) |
| `away_team` | str | Full team name (API canonical) |
| `home_team_nfl` | str | nflverse abbreviation |
| `away_team_nfl` | str | nflverse abbreviation |
| `bookmaker` | str | e.g. `"draftkings"` |
| `market` | str | e.g. `"player_anytime_td"` |
| `player_name` | str | From `description` field in outcome |
| `line` | float/None | Point total for over/under; None for binary |
| `price_over` | float/None | American odds for Over (or sole price) |
| `price_under` | float/None | American odds for Under; None for binary |
| `season` | int | Inferred NFL season year |

## How prop-implied evaluation will consume it

From `PROP_IMPLIED_DECISION.md` steps 1–3:

1. **`prop_implied_points`**: For each player-week, de-vig the over/under prices
   (Unabated method), take the median line across bookmakers per market, then
   convert per-market implied stats through `src/scoring_calculator.py` →
   implied half-PPR points. For `player_anytime_td`, use the implied TD
   probability from de-vigged price.

2. **Join key**: `(player_name, season, game_commence_time)` → resolves to
   `player_id` via `src/player_name_resolver.py` (fuzzy name matching).
   Use the snapshot taken closest to game time (latest `snapshot_ts` before
   kickoff) to get the final pre-game prop line.

3. **Backtest window**: 2023 w5–18 + 2024 w1–18. Load props Parquet directly
   with DuckDB:
   ```sql
   SELECT * FROM read_parquet('data/bronze/odds_api/props/season=2023/**/*.parquet')
   WHERE market = 'player_reception_yds'
   ```
   Match to Silver player_weekly on `(player_id, season, week)`.

4. **Blend gate**: SHIP if WR/RB MAE gap improves ≥0.05 or Spearman narrows
   ≥0.02 at either position with no QB/TE regression (per pre-registered plan).
