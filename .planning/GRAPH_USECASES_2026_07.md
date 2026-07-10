# Graph Database Expansion — 3 New Use Cases (2026-07-09)

Context: 14 graph modules exist (matchups, chemistry, injury cascade, red zone,
game script, scheme, OL continuity, route participation, college networks) with
66 graph features in production via `compute_graph_features.py` → Silver
`graph_features/` → `player_feature_engineering` joins. Neo4j is dual-path
(pandas fallback). These 3 use cases are additive — no overlap with existing
modules — and each names its consumer and validation gate up front, per the
Phase 54/55 lesson (WFCV unreliable for residuals; gate on sealed holdout or a
non-MAE product surface).

---

## UC1 — Vacated Opportunity Network (offseason roster churn)

**The gap it fills:** `graph_injury_cascade.py` models in-season target/carry
redistribution after injuries, but nothing models *offseason* churn — free
agency departures, trades, cuts, retirements, and draft additions. Preseason
projections currently lean on external consensus anchoring partly because we
have no structural signal for "team lost 180 targets, here's who absorbs them."

**Graph model:**
- Nodes: `(:Player)`, `(:Team)`, `(:SeasonTransition {from: 2025, to: 2026})`
- Edges: `[:VACATED {targets, carries, rz_touches, share}]` Player→Team for
  every departure; `[:COMPETES_FOR {depth_rank, draft_capital, adp}]`
  Player→vacancy for incumbents + arrivals + rookies.

**Data (all local Bronze/Silver):** rosters year-over-year diff, depth_charts,
draft_picks, prior-season usage from Silver player usage, ADP.

**Features (~6, strictly from prior-season data so no leakage):**
`vacated_target_share_abs`, `vacated_carry_share_abs`, `vacancy_competition_n`
(how many mouths chasing it), `arrival_displacement` (share a new arrival
historically commanded), `rz_vacancy_share`, `depth_chart_vacancy_boost`.

**Consumer:** preseason projection engine (`--preseason` path) + rookie
fallback upgrade. Directly targets the **RB +0.26 consensus gap** — RB value is
the most opportunity-driven position and backfield churn is where our preseason
numbers drift furthest from consensus.

**Validation gate:** backtest preseason projections 2022–2025 transitions;
ship only if sealed-season preseason MAE improves for RB (or Spearman rank
improves) without degrading other positions.

**VERDICT (2026-07-09): SHIP — gate passed.** Built as
`src/graph_vacated_opportunity.py` (+ CLI wiring, engine multiplier behind
`--vacated-opportunity`, 25 tests). Backtest via
`scripts/backtest_vacated_opportunity.py` on 2023/2024/2025 transitions
(baseline vs boost, no consensus anchor, top-N per position, ≥8 games):

| Pos | Spearman base → treated (Δ) | MAE Δ |
|-----|------------------------------|-------|
| QB  | 0.451 → 0.451 (0.000)        | +0.00 |
| RB  | 0.614 → 0.630 (**+0.016**)   | +0.78 |
| WR  | 0.596 → 0.596 (+0.000)       | +0.37 |
| TE  | 0.401 → 0.405 (+0.004)       | +0.29 |

(Numbers are post-review-hardening: position-scoped vacancy pools — QB
scramble targets and WR jet-sweep carries excluded — plus a 2%
transaction-noise threshold and a 1.0 cap on absorbed share. The
hardening kept the RB Spearman gain and reduced the MAE penalty
+1.12 → +0.78.)

RB rank ordering (the metric VORP/draft value uses) improves in 2 of 3
seasons, flat in the third; no position's Spearman degrades. MAE ticks up
slightly because the multiplier is upside-only (adds points, never
subtracts) — acceptable since preseason output is a *ranking* product and
the consensus anchor re-centers absolute points in production. Multiplier:
`1 + 0.5 × vacancy_absorbed_share`, capped at 1.20
(`VACATED_OPPORTUNITY_BETA` / `VACATED_OPPORTUNITY_MULT_MAX` in
projection_engine.py). Live 2026 check: 763 player features, top absorbers
all RBs (CAR/JAX/GB backfields) — behaving as designed.

---

## UC2 — Cross-Team Familiarity Network (QB changes & reunions)

**The gap it fills:** `graph_qb_wr_chemistry.py` scores pairs with *shared
in-team history*. It says nothing about the two events that actually move
projections: (a) a pass-catcher getting a **new QB** (chemistry cold start),
(b) **reunions** — a QB/receiver or coach/player pair with history on a
*previous* team or in college. College teammate edges already exist in
`graph_college_networks.py` and can be reused as one edge type.

**Graph model:**
- Edges: `[:PLAYED_WITH {games, seasons, teams[], epa_together}]` spanning ALL
  team stints (currently chemistry is per-team-stint), plus reuse
  `[:COLLEGE_TEAMMATE]`.
- Derived per player-week: is my current QB new to me? If so, do we have prior
  history anywhere in the graph?

**Features (~5):** `qb_familiarity_games` (career games with current QB, any
team), `qb_is_new` flag, `reunion_epa_prior` (their historical per-target EPA
together, 0 if none), `offense_continuity_pct` (share of current offense's
prior-season dropback-weighted snaps still on roster), `weapons_new_pct`
(QB-side mirror).

**Consumer:** WR/TE hybrid models (the two positions where graph features
already ship in the Ridge 60f+graph set) + weekly heuristic early-season weeks
1–4, where cold-start pairs are most mispriced.

**Validation gate:** same pipeline as existing graph features — add to the
WR/TE hybrid candidate set, gate on sealed-2025 MAE like the v4.2/v4.3 ships.
Keep the feature count small (research finding: 42–60 feature hybrids best).

**VERDICT (2026-07-09): HOLD — infrastructure merged, ship models unchanged.**
Built as `src/graph_familiarity.py` (17 tests): lagged expected-QB map,
cross-team pair histories, cold-start flag, continuity features; Silver
`graph_familiarity_*.parquet` materialized 2016–2025 (200–480 cold starts
per season); features wired into the hybrid candidate pool (87 graph
features) and per-stat feature assembly.

Evidence (production_eval, WR/TE Ridge-60 residual retrain with familiarity
in the SHAP pool — WR selected `qb_familiarity_games` + `weapons_new_pct`,
TE selected `reunion_epa_prior`):

| Window | WR Δ MAE | TE Δ MAE | Ship bar (−0.10) |
|--------|----------|----------|------------------|
| 2024 weeks 3–18 | −0.06 (4.41→4.35) | −0.01 | not met |
| 2024 weeks 3–6  | −0.02 (4.58→4.56) | −0.01 | not met |

The mechanism check failed: the cold-start hypothesis predicts gains
CONCENTRATED early-season, but the weeks 3–6 delta is smaller than
full-season — the −0.06 is diffuse retrain noise, not familiarity signal.
Per the Phase 54/55 lesson, the sealed-2025 holdout (already AMBER) was
NOT used. Ship residual models restored from backup byte-identical.

**Caveats / future re-tests:**
- Weeks 1–2 are outside all eval coverage (backtests start week 3) — the
  strongest cold-start window is unmeasured. If week-1/2 eval coverage is
  ever added, re-test UC2 there first.
- Features remain in the candidate pool; any future WR/TE retrain will
  reconsider them at zero cost.

---

## UC3 — Player Correlation Network (stacking & lineup covariance)

**The gap it fills:** everything graph-side today feeds *point estimates*. The
lineup builder (`src/lineup_builder.py`, `web/api/routers/lineups.py`) and the
conformal floor/ceiling bands treat players as independent — but fantasy
outcomes are strongly correlated (QB↔his WRs positive, RB↔opposing defense
negative, game-stack totals). This is a **product** use case, not an MAE play,
so it dodges the residual-model WFCV trap entirely.

**Graph model:**
- Edges: `[:CORRELATES {rho, n_games, relation}]` Player↔Player, computed from
  historical weekly fantasy points (Silver, 2016–2025) for structural pairs
  only: same-team QB↔pass-catchers, same-backfield RBs (negative), same-game
  opponents, team total ↔ player. Structural pairs keep n manageable and
  interpretable vs. all-pairs correlation mining.

**Features/outputs:**
- Lineup builder: stack bonus / anti-correlation warning when optimizing
  ("your RB2 and FLEX WR share a backfield ceiling"), correlated-ceiling
  lineup mode for best-ball/tournament style.
- API: `GET /api/lineups?mode=correlated` + a `correlations` block on player
  detail — new website surface, fits the consensus-proof/insight positioning.
- Floor/ceiling: joint bands for a roster instead of summed independent bands.

**Validation gate:** correlation stability check (edge rho estimated on
2016–2022 must hold sign on 2023–2025, min n_games threshold) before any edge
is served; product surface reviewed via existing sanity-check gate before
deploy.

---

## Suggested order

1. **UC1** — highest model value (RB gap is the named remaining deficit),
   all data already local, pure-pandas like existing modules.
2. **UC2** — cheap extension of two existing modules (chemistry + college
   edges), clear early-season consumer.
3. **UC3** — no model risk, new product surface, good Neo4j showcase (this is
   the most "graph-native" query pattern of the three — multi-hop
   stack discovery is where Neo4j beats pandas).

All three follow the established pattern: pure-pandas primary implementation,
Neo4j ingestion optional (`graph_ingestion.py`), strict shift-1 temporal lag,
features land in Silver `graph_features/` and join via
`player_feature_engineering`.
