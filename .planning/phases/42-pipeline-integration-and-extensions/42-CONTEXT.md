# Phase 42: Pipeline Integration and Extensions - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire ML predictions into the weekly pipeline, draft tool, and projection CLI. QB uses ML model (Phase 40 SHIP); RB/WR/TE use heuristic fallback (Phase 41 SKIP). Team coherence via soft constraints, preseason mode enhancement, and MAPIE confidence intervals for QB. Requirements: PIPE-02, PIPE-03, PIPE-04, EXTD-01, EXTD-02.

</domain>

<decisions>
## Implementation Decisions

### ML Flag and Routing
- **D-01:** `--ml` flag on `generate_projections.py` routes per position based on `ship_gate_report.json`: QB → ML model predictions via `predict_player_stats()`, RB/WR/TE → existing heuristic via `_weighted_baseline()`
- **D-02:** No blending of ML + heuristic — pure routing. Blending dilutes QB's 75% improvement and adds noise to positions where heuristic wins
- **D-03:** Output format identical to current projections (same columns: player_id, player_name, position, proj_{stat}, fantasy_points, floor, ceiling). Draft assistant and weekly pipeline consume ML projections with zero changes to their code
- **D-04:** Default behavior without `--ml` is unchanged (pure heuristic) for backward compatibility. `--ml` is opt-in

### Heuristic Fallback Rules
- **D-05:** Automatic fallback to heuristic for: (a) positions where ML SKIP'd (RB/WR/TE per ship gate), (b) rookies with no rolling features (all NaN), (c) players with fewer than 3 games of data in current season
- **D-06:** Fallback is silent — no user-visible indication except a `projection_source` column: "ml" or "heuristic" per row
- **D-07:** Ship gate report is read at runtime from `models/player/ship_gate_report.json` — if report is missing or models aren't trained, fall back to full heuristic with a warning

### Team-Total Constraints
- **D-08:** Soft constraints only — do not force normalization. Per-player accuracy is the priority; team coherence is secondary
- **D-09:** After projections are generated, compute per-team stat shares (e.g., sum of projected rushing_yards for all RBs on a team / implied team rushing total). Flag teams exceeding 110% share with a log warning
- **D-10:** No adjustment to individual projections based on team totals. The warning is diagnostic for future investigation, not a correction mechanism
- **D-11:** Implied team totals derived from game prediction model's `opening_total` and `opening_spread` via the existing formula: `(total/2) - (spread/2)` for home, `(total/2) + (spread/2)` for away

### Preseason Mode
- **D-12:** Preseason stays fully heuristic for all positions — ML models require rolling features (roll3, roll6) that don't exist before week 1
- **D-13:** Enhance existing `generate_preseason_projections()` with draft capital weighting: rookies with higher draft picks get slight boost to baseline projections using `draft_round`, `draft_pick` from Silver historical table
- **D-14:** Draft capital adjustment is additive to the existing rookie baseline, not a replacement. First-round picks get larger boost than late-round picks

### MAPIE Confidence Intervals
- **D-15:** MAPIE confidence intervals for QB only (the shipped ML model). Provides player-specific prediction intervals from the model itself, replacing heuristic shrinkage for QB
- **D-16:** For RB/WR/TE (heuristic positions), keep existing `add_floor_ceiling()` with position-specific variance (RB: 40%, WR: 38%, TE: 35%)
- **D-17:** MAPIE uses `MapieRegressor` with `method="plus"` (jackknife+) on the final trained QB models. Outputs floor/ceiling at 80% prediction interval
- **D-18:** If MAPIE import fails (optional dependency), fall back to heuristic floor/ceiling for QB too — graceful degradation

### Claude's Discretion
- How to structure the ML projection pipeline function (new module vs extending projection_engine.py)
- MAPIE integration details (which stat models get intervals, how to combine per-stat intervals into fantasy point intervals)
- Draft capital boost formula (linear decay by round, or categorical tiers)
- Soft constraint warning format and threshold tuning
- Weekly pipeline GHA workflow changes (if any)

</decisions>

<specifics>
## Specific Ideas

- The `--ml` flag should work with both `--week` and `--preseason` modes. In preseason, `--ml` is a no-op (all heuristic) but doesn't error
- The `projection_source` column ("ml"/"heuristic") enables future analysis of which source is more accurate per player
- Draft assistant reads projections from file (`--projections-file`) — no code changes needed if output format matches
- Weekly pipeline (`weekly-pipeline.yml`) can add `--ml` to the `generate_projections.py` call — single-line change

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Projection pipeline (integration target)
- `scripts/generate_projections.py` — Current CLI: `--week`, `--preseason`, `--scoring`, output to Gold layer
- `src/projection_engine.py` — `generate_weekly_projections()`, `generate_preseason_projections()`, `apply_injury_adjustments()`, `add_floor_ceiling()`

### ML model infrastructure (Phase 40-41 output)
- `src/player_model_training.py` — `train_position_models()`, `predict_player_stats()`, `load_player_models()`, `ship_gate_verdict()`
- `src/player_feature_engineering.py` — `assemble_player_features()`, `get_player_feature_columns()`
- `models/player/ship_gate_report.json` — Runtime routing config (which positions use ML)

### Draft tool (consumer)
- `scripts/draft_assistant.py` — `--projections-file` flag, reads CSV/Parquet projections
- `src/draft_optimizer.py` — `DraftBoard`, `DraftAdvisor` consume projections DataFrame

### Scoring and fantasy points
- `src/scoring_calculator.py` — `calculate_fantasy_points_df()` converts raw stats to fantasy points

### Game prediction implied totals
- `src/feature_engineering.py` — `compute_implied_team_totals()` formula for team total constraints
- `src/player_analytics.py` — `compute_implied_team_totals()` same formula used in player analytics

### Prior phase contexts
- `.planning/phases/40-baseline-models-ship-gate/40-CONTEXT.md` — Ship gate design, evaluation method
- `.planning/phases/41-accuracy-improvements/41-CONTEXT.md` — Feature improvements, ensemble decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `projection_engine.generate_weekly_projections()`: Current heuristic pipeline — extend with ML routing, don't replace
- `projection_engine.add_floor_ceiling()`: Heuristic variance bands — keep for RB/WR/TE, replace with MAPIE for QB
- `player_model_training.predict_player_stats()`: Generates raw stat predictions from trained models
- `scoring_calculator.calculate_fantasy_points_df()`: Converts any raw-stat DataFrame to fantasy points
- `draft_assistant.py --projections-file`: Already supports external projection input — no changes needed

### Established Patterns
- **Local-first reads**: `_read_local_parquet()` pattern in generate_projections.py
- **Gold output**: Parquet to `data/gold/projections/` with timestamp suffix
- **Injury adjustments**: Applied after projections, before output — same position in pipeline for ML
- **Floor/ceiling**: Added as last step via `add_floor_ceiling()` — MAPIE replaces this for QB only

### Integration Points
- **generate_projections.py main()**: Add `--ml` argparse flag, routing logic before projection generation
- **projection_engine.py**: New function `generate_ml_projections()` or extend `generate_weekly_projections()` with ml_mode parameter
- **weekly-pipeline.yml**: Add `--ml` to the generate_projections.py call
- **Gold output**: Same path/format regardless of ML or heuristic source

</code_context>

<deferred>
## Deferred Ideas

- Hard team-total normalization (force shares to sum to 100%) — revisit if soft constraints reveal systematic over-projection
- ML preseason mode (train on prior-season aggregates) — needs preseason-specific model architecture
- MAPIE for RB/WR/TE — requires those positions to ship ML first
- Live Sleeper integration for draft tool — separate milestone
- Automated model retraining at season start — v4.0 Production Pipeline

</deferred>

---

*Phase: 42-pipeline-integration-and-extensions*
*Context gathered: 2026-03-31*
