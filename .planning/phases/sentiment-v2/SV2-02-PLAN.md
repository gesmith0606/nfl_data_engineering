---
phase: SV2-team-sentiment-game-lines
plan: 02
type: execute
wave: 2
depends_on: [SV2-01]
files_modified:
  - src/sentiment/aggregation/team_weekly.py
  - src/sentiment/aggregation/weekly.py
  - scripts/generate_predictions.py
  - scripts/process_sentiment.py
  - tests/test_team_sentiment.py
autonomous: true
requirements: [SV2-05, SV2-06, SV2-07, SV2-08]

must_haves:
  truths:
    - "Team-level sentiment is aggregated from player signals plus team-specific mentions"
    - "Team sentiment multiplier is available per team per week as a Parquet file"
    - "Game predictions can be adjusted by team sentiment (post-prediction edge modifier)"
    - "Sentiment pipeline CLI runs both player and team aggregation in one pass"
  artifacts:
    - path: "src/sentiment/aggregation/team_weekly.py"
      provides: "Team-level sentiment aggregation"
      exports: ["TeamWeeklyAggregator"]
    - path: "tests/test_team_sentiment.py"
      provides: "Team sentiment unit tests"
      min_lines: 60
  key_links:
    - from: "src/sentiment/aggregation/team_weekly.py"
      to: "src/sentiment/aggregation/weekly.py"
      via: "Reads player-level Gold sentiment, aggregates by team"
      pattern: "player_id.*team"
    - from: "scripts/generate_predictions.py"
      to: "src/sentiment/aggregation/team_weekly.py"
      via: "Loads team sentiment and applies as edge modifier"
      pattern: "team_sentiment"
---

<objective>
Build team-level sentiment aggregation and wire it into game predictions as a
post-prediction edge modifier. This extends sentiment from player-only (fantasy)
to team-level (game predictions).

Purpose: Team sentiment captures aggregate momentum (e.g., "BAL has 5 positive news
items this week") that can shift game line edges. This is analogous to how the
existing `spread_edge` works but adds a sentiment-derived adjustment.

Output: Team aggregation module, updated prediction script with --use-sentiment flag.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/sentiment-v2/SV2-01-SUMMARY.md

@src/sentiment/aggregation/weekly.py
@scripts/generate_predictions.py
@src/config.py

<interfaces>
<!-- From weekly.py (player-level Gold output) -->
```python
# Gold Parquet columns per player-week:
# player_id, player_name, team, position, sentiment_score, sentiment_multiplier,
# confidence, doc_count, signal_count, categories (JSON), events (JSON)
```

<!-- From generate_predictions.py (edge computation) -->
```python
# After model prediction:
# week_df["spread_edge"] = week_df["model_spread"] - week_df["vegas_spread"]
# week_df["total_edge"] = week_df["model_total"] - week_df["vegas_total"]
# classify_tier(edge) -> "high" | "medium" | "low"
```

<!-- From PlayerSignal dataclass -->
```python
@dataclass
class PlayerSignal:
    player_name: str
    sentiment: float  # -1.0 to +1.0
    confidence: float
    category: str
    events: Dict[str, bool]
    excerpt: str
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Team-level sentiment aggregation</name>
  <files>
    src/sentiment/aggregation/team_weekly.py,
    tests/test_team_sentiment.py
  </files>
  <behavior>
    - TeamWeeklyAggregator.aggregate(season, week) returns DataFrame with team-level sentiment
    - Output columns: team, season, week, team_sentiment_score (-1 to +1), team_sentiment_multiplier (0.95 to 1.05), player_signal_count, team_signal_count, positive_count, negative_count, net_sentiment
    - Aggregation logic: weighted average of player sentiments for that team, plus team-name mentions from Reddit/RSS
    - Team mentions detected via team name/abbreviation in article text (e.g., "Ravens", "BAL", "Baltimore")
    - team_sentiment_multiplier range is tighter than player (0.95-1.05) because team sentiment is noisier
    - Output saved to data/gold/sentiment/team_sentiment/season=YYYY/week=WW/
    - Empty player signals for a team -> neutral multiplier (1.0)
  </behavior>
  <action>
    Create `src/sentiment/aggregation/team_weekly.py` with `TeamWeeklyAggregator`:

    1. **Input sources**:
       - Gold player sentiment (from weekly.py output): group by team, weighted-average sentiment
       - Silver signals: scan for team-name mentions in excerpts (team abbreviations from a TEAM_ABBREVIATIONS dict of all 32 NFL teams)
       - Bronze Reddit/RSS: scan titles for team mentions (cheaper than full text)

    2. **Team name detection**:
       - Build a dict mapping team names, abbreviations, and city names to canonical 3-letter code
       - Example: {"Ravens": "BAL", "BAL": "BAL", "Baltimore": "BAL", "Baltimore Ravens": "BAL"}
       - Apply regex word-boundary matching to avoid false positives ("car" matching "CAR")

    3. **Aggregation formula**:
       ```
       player_component = mean(player_sentiment_scores for team) * 0.6
       team_mention_component = mean(team_mention_sentiments) * 0.4
       team_sentiment_score = player_component + team_mention_component  # clamped [-1, +1]
       team_sentiment_multiplier = 1.0 + (team_sentiment_score * 0.05)  # clamped [0.95, 1.05]
       ```

    4. **Output**: Save as Parquet to `data/gold/sentiment/team_sentiment/season=YYYY/week=WW/team_sentiment_{timestamp}.parquet`

    5. **Tests**: Test with mock player sentiment data, test team name detection, test multiplier clamping, test empty data -> neutral.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -m pytest tests/test_team_sentiment.py -v</automated>
  </verify>
  <done>
    - TeamWeeklyAggregator produces per-team sentiment for all 32 teams
    - Multiplier is always in [0.95, 1.05] range
    - Tests cover aggregation logic, team detection, and edge cases
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire team sentiment into game predictions</name>
  <files>
    scripts/generate_predictions.py,
    scripts/process_sentiment.py
  </files>
  <action>
    **Game prediction adjustment** (`scripts/generate_predictions.py`):

    1. Add `--use-sentiment` flag (mirrors the existing flag in `generate_projections.py`).

    2. When flag is set, after computing `spread_edge` and `total_edge`:
       - Load team sentiment from `data/gold/sentiment/team_sentiment/season=YYYY/week=WW/`
       - For each game, look up home_team and away_team sentiment multipliers
       - Compute `sentiment_edge_adjustment = (home_sentiment_mult - away_sentiment_mult) * SENTIMENT_EDGE_WEIGHT`
         where `SENTIMENT_EDGE_WEIGHT = 1.5` (configurable, represents max +/- 0.15 pts adjustment)
       - Apply: `adjusted_spread_edge = spread_edge + sentiment_edge_adjustment`
       - Add columns: `home_sentiment`, `away_sentiment`, `sentiment_adjustment` for transparency
       - Do NOT change the model prediction itself -- this is a post-prediction transparency layer

    3. Print sentiment context in the summary output when verbose.

    **Pipeline CLI** (`scripts/process_sentiment.py`):

    1. After running player-level aggregation (existing), also run TeamWeeklyAggregator.
    2. Add `--skip-team` flag to skip team aggregation if desired.
    3. Print summary of team sentiment results.

    This approach is conservative: sentiment adjusts the edge detection (which is already
    a comparison layer), not the model predictions themselves. If team sentiment proves
    valuable, it can be promoted to a training feature in a future phase.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -m pytest tests/test_sentiment_processing.py tests/test_sentiment_integration.py -v</automated>
  </verify>
  <done>
    - generate_predictions.py accepts --use-sentiment and loads team sentiment
    - Edge adjustment is bounded and transparent (new columns show the math)
    - process_sentiment.py runs both player and team aggregation
    - No change to underlying model predictions
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Sentiment data -> prediction edge | Untrusted sentiment scores influence game line edges |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-SV2-05 | Tampering | Team sentiment | mitigate | Multiplier clamped to [0.95, 1.05]; edge adjustment max +/- 0.15 pts |
| T-SV2-06 | Elevation | Edge override | mitigate | Sentiment adjusts edge transparency layer only, never model predictions |
</threat_model>

<verification>
1. Team aggregation produces Parquet: `ls data/gold/sentiment/team_sentiment/`
2. `python scripts/process_sentiment.py --season 2025 --week 1 --verbose` runs both player + team
3. `python scripts/generate_predictions.py --use-sentiment --season 2024 --week 1` shows sentiment columns
4. Tests pass: `python -m pytest tests/test_team_sentiment.py tests/test_sentiment_processing.py -v`
</verification>

<success_criteria>
- Team sentiment aggregated for all 32 teams per week
- Game predictions show sentiment-adjusted edges when --use-sentiment is used
- Adjustment is bounded and conservative (max +/- 0.15 pts)
- All tests pass
</success_criteria>

<output>
After completion, create `.planning/phases/sentiment-v2/SV2-02-SUMMARY.md`
</output>
