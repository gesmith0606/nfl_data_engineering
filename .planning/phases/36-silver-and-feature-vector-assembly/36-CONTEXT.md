# Phase 36: Silver and Feature Vector Assembly - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Silver market features cover the full 2016-2025 window and 2025 Silver data is complete, enabling feature vector assembly for the new holdout season. This phase runs existing Silver transformation scripts on new data and validates the assembled feature vector.

</domain>

<decisions>
## Implementation Decisions

### Silver market data expansion
- **D-01:** Run `silver_market_transformation.py --season YYYY` for all 6 FinnedAI seasons (2016-2021) to generate line movement features (spread_shift, total_shift, magnitude buckets, key number crossings)
- **D-02:** Run `silver_market_transformation.py --season YYYY` for nflverse-bridge seasons (2022-2025). For these seasons, spread_shift and total_shift will be zero (opening == closing per Phase 35 D-05), but the transformation must still produce valid Parquet with the expected schema
- **D-03:** Silver market data for 2020 may already exist from v2.1 — re-run anyway for consistency (latest-file convention means downstream always reads newest)

### 2025 Silver transformations
- **D-04:** Run all 6 Silver transformation scripts for 2025:
  1. `silver_player_transformation.py --seasons 2025` (usage metrics, rolling averages)
  2. `silver_team_transformation.py --seasons 2025` (PBP metrics, tendencies, SOS, situational)
  3. `silver_game_context_transformation.py` for 2025 (weather, rest, travel, referee)
  4. `silver_advanced_transformation.py` for 2025 (NGS/PFR/QBR merge)
  5. `silver_player_quality_transformation.py --seasons 2025` (QB EPA, injury impact)
  6. `silver_market_transformation.py --season 2025` (covered by D-02)
- **D-05:** If any Silver script fails for 2025 due to missing columns or data gaps, investigate and fix — do not silently skip. Every Silver path must produce output for 2025 to enable complete feature vector assembly
- **D-06:** Injury adjustments for 2025 will be absent (Bronze injuries unavailable per Phase 35). Silver player quality transformation must handle this gracefully — NaN injury columns, not errors

### Feature vector assembly for 2025
- **D-07:** Run `feature_engineering.py` assembly for 2025 games. The feature vector joins 10 Silver sources on [team, season, week]
- **D-08:** Validate opening_spread and opening_total are populated for 2025 games (NaN rate < 5%). These come from Silver market data via the nflverse bridge
- **D-09:** Validate feature vector row count: at least 285 game-team rows for 2025 (matching schedule game count)
- **D-10:** Run feature vector assembly for 2016-2024 as well to verify expanded market features are picked up correctly — this is the training data that Phase 37 will use

### Claude's Discretion
- Order of Silver script execution (no dependencies between scripts except market needing Bronze odds)
- Whether to run 2016-2024 Silver transformations in parallel or sequentially
- Error handling and retry logic for individual Silver scripts
- Exact validation thresholds beyond the stated 5% NaN rate

</decisions>

<specifics>
## Specific Ideas

- For model accuracy: ensure ALL Silver paths produce 2025 output, even if some features are sparse — gradient boosting handles NaN but missing entire Silver sources means missing entire feature groups
- The nflverse-bridge seasons (2022-2025) will have zero line movement (spread_shift=0, total_shift=0, magnitude=0) — this is correct behavior, not an error. The model learns that no movement happened.
- Feature vector for 2016-2024 with expanded market coverage is the key deliverable for the Phase 38 ablation

</specifics>

<canonical_refs>
## Canonical References

### Silver transformation scripts
- `scripts/silver_market_transformation.py` — Market-specific Silver CLI; reads Bronze odds, produces line movement features
- `scripts/silver_player_transformation.py` — Player usage metrics, rolling averages, opponent rankings
- `scripts/silver_team_transformation.py` — PBP metrics, tendencies, SOS, situational splits (1834 lines)
- `scripts/silver_game_context_transformation.py` — Weather, rest, travel, coaching, surface per team per week
- `scripts/silver_advanced_transformation.py` — NGS/PFR/QBR merge into advanced player profiles
- `scripts/silver_player_quality_transformation.py` — QB EPA, positional quality, injury impact

### Feature engineering
- `src/feature_engineering.py` — 310+ column feature vector assembly from 10 Silver sources; `_PRE_GAME_CONTEXT` defines market feature columns
- `src/market_analytics.py` — PRE_GAME vs RETROSPECTIVE feature classification

### Phase 35 outputs (inputs to this phase)
- `data/bronze/odds/season=YYYY/` — Bronze odds for 2016-2025 (10 seasons)
- Phase 35 CONTEXT.md D-05 — closing lines as opening proxies for 2022+

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- All 6 Silver transformation scripts: run as-is with `--seasons 2025` or `--season YYYY` flags
- `silver_market_transformation.py`: proven on season 2020 in v2.1; extend to remaining seasons
- `feature_engineering.py`: assembles full feature vector via left joins; no changes needed

### Established Patterns
- Silver output: `data/silver/{path}/season=YYYY/` with timestamped Parquet files
- Feature vector: `data/silver/feature_vectors/season=YYYY/` or assembled in-memory
- All Silver scripts read Bronze via `download_latest_parquet()` convention
- Season loop: most scripts accept `--seasons 2020 2021 2022 ...` for batch execution

### Integration Points
- Silver market data feeds `feature_engineering.py` via `_PRE_GAME_CONTEXT` (opening_spread, opening_total)
- All Silver paths feed feature vector assembly via left joins on [team, season, week]
- Feature vector output is consumed by Phase 37 (holdout reset + ensemble retraining)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 36-silver-and-feature-vector-assembly*
*Context gathered: 2026-03-28*
