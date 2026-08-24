# Draft Doctrine — how the draft agent values players and makes picks

Evidence-based rules for redraft snake drafts (12-team default), assembled 2026-08-23 from
public fantasy research (sources at the end) plus lessons from our own ESPN mocks. Every
rule is written to be codable; where a number is cited, the source is named. The
`draft-agent` subagent follows this document; `src/draft_optimizer.py` implements the
parts marked **[impl]**.

## 0. House rules (user, non-negotiable)
- **Never roster a 2nd QB** in a 1-QB league. **[impl]** `DraftAdvisor.recommend` blocks QB once the starter is set.
- **No K/DST until the final (open K/DST slots + 1) picks.** **[impl]**
- **Starters first**: no backup at a position while any QB/RB/WR/TE/FLEX starter is open. **[impl]**
- The platform ADP of the *room you are in* is the market — never a different platform's ADP. **[impl]** (`refresh_adp.py --source espn|ffc|sleeper|mfl`; ESPN presets auto-select ESPN ADP.)

## 1. Value = points over replacement, not raw points
1. **VORP** = projected points − replacement-level points at the position; replacement rank = starters-per-team × teams, with FLEX allocated by scarcity (12-team 1QB/2RB/2WR/TE/FLEX: QB13, RB≈29, WR≈31, TE15). 2-FLEX and 3-WR leagues push WR replacement to ~36–43. **[impl]** `replacement_ranks_for`. *(FantasyPros, "Value-Based Drafting", 2026)*
2. **Scoring changes the map**: no-PPR compresses volume WRs toward TD scorers and lifts RBs; PPR lifts target hogs and pass-catching RBs. Always regenerate projections for the room's scoring — never hand-convert stat lines (the consensus anchor lives on points only). **[impl]** `generate_projections.py --preseason --scoring <room>`.

## 2. Tiers, not ranks
3. A tier is a *decision bucket*: players you'd be equally happy with. Break a tier where the projected-value gap is large relative to the position's typical gaps (**[impl]** `draft_tiers.compute_tiers`: drop > 0.35 × std of drops) or where role/workload changes discontinuously. Avoid 1-player tiers and 15+-player tiers. *(FantasyPros "Draft Tiers", DraftSharks 2026)*
4. Real cliffs typically show after ~8 players at a position (TE1–8 flat, cliff at TE9; QB7–QB16 is one flat tier). *(FantasyPros 2026)*
5. **Draft priority is "last player in a tier at a scarce position," not "next-best rank."**

## 3. Cost of waiting — the pick score
6. For every candidate: **opportunity cost = VORP now − expected best VORP at *this position* at my next pick**, where expectation walks the position's candidates in VORP order weighted by survival probability. **[impl]** `draft_availability.expected_best_vorp_at_pick`; `recommend(next_pick_no=…)`.
7. Survival probability: P(gone before pick p) = Φ((p − ADP) / σ), σ = per-player ADP stdev when known (FFC) else max(3, 0.15·ADP). Tight σ = market consensus (must pay ADP); wide σ = disagreement (can wait). *(FantasyDraftCoach methodology; e.g. ADP 66, σ 6.1 → 84% available at 60)*
8. Take the highest **cost of waiting**, not the highest VORP. A flat tier (WR20–40 in standard, ~140 pts flat) has cost ≈ 0: wait. A vanishing tier (last elite TE, QB1 tier in an ESPN room where 9 QBs go between picks 38–88) has high cost: take now.
9. **Turn math**: slots 1–2 and 11–12 draft in pairs; use the double pick to take two players from one thinning tier before the room reacts. Slots 5–8 have ~11-pick gaps both ways.

## 4. ADP arbitrage / mispricing
10. **Value** = model (or consensus) rank ≥ 1 round (≥12 picks in 12-team) ahead of ADP. **Reach** = 2+ rounds above ADP. **[impl]** `UNDERVALUED_THRESHOLD = 15` picks; `market_insights()` in `draft_live.py`. *(FantasyPros Sleeper ADP vs ECR; Bleacher Nation 2026)*
11. **Platforms disagree by up to 2+ rounds on the same player.** ESPN rooms take QBs and TEs much earlier than Sleeper/FFC (Allen ADP 22 vs 32; Bowers 24 vs 43; McBride 20 vs 40 on 2026-08-23); TE has the largest cross-platform variance; ESPN default scoring skews pass-catchers earlier. Price against the room's own ADP. *(FantasySixPack "ADP Values: ESPN, Yahoo, Sleeper & CBS" 2026; FTN "Exploiting Sleeper ADP" 2026; our ESPN mocks)*
12. **ADP momentum** (risers/fallers over the last 2 weeks) is informative but often already priced by draft day; treat as a tie-breaker.

## 5. Positional strategy (12-team)
13. **QB**: the QB7–QB16 tier is flat (339→305 pts in our 2026 standard board); wait until round 8+ unless a tier-1 QB's cost of waiting is decisive *in that room* (ESPN standard rooms run on QBs early — the calc, not the rule, decides). *(RotoWire late-round QB 2026)*
14. **TE**: pay only for the 1–2 elite TEs (weekly edge); otherwise TE9–TE20 are interchangeable — take the cheapest one late (Kittle/Kraft at ADP 80–120 ≈ Loveland/Warren at 40–50 in our model). *(FantasyPros "How to draft TEs" 2026)*
15. **RB dead zone** (rounds ~3–7): highest bust-rate window for RBs; either get 2 RBs in your first 4–5 picks or skip mid-round RBs for WR/upside and backfill after round 7. 2026 caveat: weak rookie RB class → early RB scarcity is real; Hero-RB (one elite RB, then WR) is the consensus middle path. *(FantasyLife "RB Dead Zone 2026"; FantasyPros Zero-RB 2026)*
16. **Bench**: RB/WR depth only (byes/injuries start games); never a backup QB, at most one backup TE and only in the last third of the draft.

## 6. Reading the room
17. **Positional run** = 3+ of the last 4 picks at one position; adjacent drafters follow 4–6 deep. Don't panic-follow — check whether your target tier survives the run; jump it only when you sit near the turn and the tier is thin. **[impl]** `LiveDraftEngine._run_moment`. *(Athlon Sports; SI 2026)*
18. **Handicap opponents' needs**: a team with 3 RBs and 0 WRs isn't taking your RB target; count roster gaps for the teams picking before your next turn and adjust survival odds. (Next implementation step for `expected_best_vorp_at_pick`.)
19. In **ESPN mocks, autopick teams draft by ESPN rank** — a pure-ADP room; reaches come only from humans.

## 7. Bust signals (fade at ADP)
20. **RB age cliff at 27→28**: median −22% PPG from age-27 to age-28 season; 57% of RB1 seasons come at ages 23–26, 19% at 27–28. Flag any RB 27+ on Sept 1. *(Fantasy Football Blueprint 2026; RotoBaller)*
21. **Top-5 finishes don't repeat**: only 24% of top-5 RBs repeat top-5 (52% stay top-12); ~1/3 of top-5 WRs repeat. Discount ADP-implied ceilings for last year's top-5. *(Fantasy Index 2026; PFF)*
22. **TD regression**: actual TDs above expected TDs regressed downward in 91% of cases (2016–25); QBs above xTD% dropped 73% of the time. Flag actual − xTD > 2–3. Proxy without xTD: **TD share of projected points > ~35%** (TD-dependent scorer) or prior-year TD rate far above career rate. *(FantasyPros TD Regression Report; Fantasy Points xTD)*
23. **Efficiency regression**: elite single-season YPC/YPRR is not sticky; > +0.5 YPC over career norm is a regression flag. *(Fantasy Index 2026)*
24. **Volume threat**: team added draft capital within 3 rounds at the position or a comparable FA; round-1 rookie RBs take ≥60% of early carries. Discount the incumbent. *(FF Blueprint 2026)*
25. **Target share floor**: ADP implying WR1/2 production with trailing target share < 17–18% (or declining) = overpriced. WOPR = 1.5·target share + 0.7·air-yards share. *(PFF; Sharp Football)*
26. **Durability**: top-two injury-risk quintiles miss ~3× the games; heavy career touches raise RB risk. *(Draft Sharks Injury Predictor)*
27. **ADP inflation**: ADP positional rank − model positional rank ≥ 15 picks with hype/recency (career year, camp buzz) = standalone bust flag. **[impl]** `value_tier == overvalued`. *(FantasyPros "Players experts avoid at ADP" 2026)*
28. Operational definition used in research: bust = finishes ≥10 positional spots below ADP or ≥100 pts (≈20%) below preseason projection; true collapses are rare (17 RBs in a decade of R1–2 picks). Use the same label when back-testing bust calls. *(CBS/Yahoo bust-rate coverage 2026)*

## 8. Breakout & sleeper signals (target above ADP)
29. **Sleeper** = consensus/model rank ≥ 12 picks ahead of ADP. **Breakout** = years_exp ≤ 3 with a projected role step-up (not just a good line). **Deep sleeper** = ADP > 100–150 with a plausible top-24 positional ceiling. *(FantasyPros; 4for4 "sleepers after pick 150" 2026)*
30. **Age/experience curves**: WR breakouts cluster at age ≤ 23 (94% of rookie-year breakouts) with early draft capital (≤ round 2) and college breakout age < 20; TE breakouts cluster in years 2–3 once target competition clears; round-1 RBs get a lead role immediately, Day-2 RBs are high-variance (16 of 56 produced an RB1 season). *(RotoViz breakout age; 4for4 production curves; DynastyNerds draft capital)*
31. **Vacated opportunity**: sum of departed teammates' prior-year targets/carries; large vacated pools with weak remaining competition lift incumbents. **[impl]** `draft_sleepers.build_sleeper_rows` (UC1 vacated-opportunity features). *(4for4; RotoBaller "Vacated targets 2026")*
32. **Usage thresholds**: target share > 20% ≈ WR1 range (> 25% strongly); snap share ≥ 70% for bankable volume; route participation and air-yards share separate role quality from raw targets. *(PFF; FantasyLife)*
33. **Efficiency on low volume**: YPRR is the best per-opportunity stat — top-20 YPRR WRs outscored bottom-20 by +154% the next season — but only trust it with ≥ 180 routes. *(FantasyPros YPRR explainer)*
34. **Positive TD regression**: WR/TE with ≥ 50 touches and < 5 TDs scored more the next year 66% of the time. *(ESPN 2026 TD regression)*
35. **Environment**: Vegas implied team total (top-8 offenses), new pass-heavy OC, QB upgrade, pace. **[impl]** `season_prop_implied.attach_market_columns` (DK season futures → `prop_anchor_gap`). *(Sharp Football implied totals)*

## 8b. Market-fade rules (added 2026-08-24 from the historical replay)
36. **Market-faded star = red flag, not value.** A prior top-12 positional producer whose current ADP
    sits ≥ 12 positional spots worse is being dropped on *news the stat line can't see* (injury,
    suspension, role loss). Back-test 2021–25: bust 50% vs 39% base, beat-ADP 7% (n=14 — low
    confidence, but this is exactly the class that destroyed the 2025 replay: Mixon proj 260 /
    ADP 136 / actual 0). **[impl]** `draft_value.label_board` §36. The projections cannot see August
    news — when a "value" comes from a star the market dumped, the market wins the argument.
37. **Faded mid-tier producer = often real value.** Prior 13–24 positional producers hard-faded by the
    market beat their ADP 24% vs 15% base — the market overdoes those fades. Info tag, not scored.

## 9. What the agent must output at every pick
- **Cost of waiting by position** (best now vs expected at my next pick) — the strategic view. **[impl]** `position_wait_costs()`
- **Top recommendations** by opportunity cost, respecting house rules. **[impl]**
- **Values/sleepers still on the board** and **busts the room is about to reach for**. **[impl]** `market_insights()`
- **Tier-cliff alerts**: "last player of tier N at RB" — *next implementation step* (`compute_tiers` exists; not yet in the live render).
- Always name the *reason* (which rule above) — a pick without a rule is a guess.

## 10. Back-test results — what our own data says (2021–2025)
`python scripts/backtest_draft_flags.py` — 682 drafted players (FFC ADP ≤ 150, Sept-1 snapshots) scored
by half-PPR finish; bust = ≥10 positional spots below ADP or ≤ 8 games (§28). Base rates: **bust 38%,
beat-by-10 14%**.

| Rule | Flagged n | Bust rate flagged vs rest | Beat rate flagged vs rest | Verdict |
|---|---|---|---|---|
| §20 RB age ≥ 27 | 65 | **45% vs 32%** (lift 1.39) | 8% vs 21% | **confirmed** (age ≥ 28: 49%, lift 1.49) |
| §21 prior top-5 finish, all positions | 95 | 32% vs 39% (0.81) | 0% vs 16% | **not a bust signal** — priced correctly; they just can't "beat" ADP |
| §21 prior top-5, RB only | 24 | 46% vs 34% (1.33) | 0% | **keep for RB only** |
| §22 proxy: prior TD share > 35% | 130 | 32% vs 39% (0.83) | 3% vs 16% | **rejected as a bust proxy** — real §22 needs actual-vs-expected TDs (xTD), not built yet |
| §34 WR/TE ≥ 50 tgt & < 5 TD prior | 86 | 38% vs 43% (0.90) | **17% vs 13%** (1.33) | **mild support** (positive regression) |
| §15 RB drafted rounds 3–7 | 97 | **40% vs 32%** (1.24) | 13% vs 20% | **confirmed** — RB dead zone is real; WR rounds 3–7 show no effect (1.04) |

| §22 real xTD: prior TDs ≥ +3 over expected (ffopportunity) | 60 | 43% vs 38% (1.14) | **3% vs 13%** (0.25) | **ceiling cap**: overachievers almost never beat ADP; mild bust tilt. Underachiever side (≤ −2): no signal (1.02) |

By ADP round (all positions): round 4 is the worst (50% bust); rounds 1–3 ≈ 34–37%; "beat" rates climb
from ~0% in rounds 1–3 to 20–28% in rounds 6–11 — upside lives late, safety early. Engine consequences:
`src/draft_value.py` scores §21 for RBs only, drops the TD-share proxy, and scores the real xTD
overachiever gap (≥ +3) as a mild bust / ceiling-cap signal.

**Historical replay (2026-08-24, `scripts/draft_history_replay.py`):** the advisor drafted 2021–2025
with point-in-time info only (heuristic projections from Silver usage Y-2/Y-1 + that season's real
Sept-1 FFC ADP; opponents = ADP+noise bots), rosters scored by **actual season results**. Three findings:
1. **Unfiltered board = disaster (mean rank 9.94/12).** 79% of the heuristic pool had no ADP that year;
   the advisor drafted retirees (Gronkowski, Antonio Brown) and 1-game ghosts (a 309-pt "projection"
   from a single 2-TD week). *A value engine without a market filter drafts ghosts — the room-universe /
   consensus filter is load-bearing, not cosmetic.*
2. **Room-universe filter → market-even: pooled mean rank 6.42/12** (field 6.5), top-3 31% / bottom-3 32%,
   season range 1.5 (2022) to 10.0 (2025).
3. **Rookie-blind first pass understated the engine.** 6–9 of each year's ADP top-100 (rookies + one
   nickname join-miss) were invisible — worth 689–1,171 actual points/season. With rookie inputs
   (draft-capital `historical_df` + season `roster_df` → the low-sample synthesizer) and the
   Hollywood→Marquise alias fix: **pooled mean rank 5.64/12** (field 6.5), top-3 43% / bottom-3 28% —
   **above market in 4 of 5 seasons** (2021 4.5 · 2022 1.7 · 2023 3.7 · 2024 7.0).
4. **2025 collapsed (11.3, −343 pts) and named the third failure class:** the injury-blind heuristic
   bought market-faded veterans — Mixon (proj 260, ADP 136, actual **0**), post-career-year Daniels,
   Godwin/Najee/Thielen. That produced rules §36/§37 (market-faded star = red flag; faded mid-tier =
   often value). The consensus anchor (production-only, unreplayable) also counters this class.
Net: with the correctable artifacts fixed, the engine drafts **above the ADP market in most seasons by
actual results**; its residual failure mode is August news the stat lines can't see — which §36 flags
and the production anchor prices in.

**Sim study (2026-08-24, `scripts/draft_sim_study.py`):** advisor drafted all 12 slots × 4 seeds against
ADP+noise bots; rosters scored by **ESPN's own projections** (out-of-model yardstick): mean starting-lineup
rank **4.3 of 12** (field 6.5), +2.3 pts/week vs field average, top-3 finish 35%, bottom-3 4%. Scored by our
own projections the advisor ranks 1st in 47/48 — that number is circular and must never be quoted as evidence.
Limitation: opponents are ADP-followers, not sharp humans.

## Sources
FantasyPros: Value-Based Drafting (2026), Draft Tiers (2026), How to Draft TEs (2026), Zero-RB (2026), Sleeper ADP vs ECR, Touchdown Regression Report, "24 players experts avoid at ADP" (2026), YPRR explainer · DraftSharks 2026 Tiers, Injury Predictor · FantasyLife: RB Dead Zone 2026, Route Participation · RotoWire late-round QB 2026 · FantasyDraftCoach availability methodology · FantasySixPack/FantasyInFrames ADP values across ESPN/Yahoo/Sleeper/CBS 2026 · FTN Exploiting Sleeper ADP 2026 · Athlon Sports positional runs · Bleacher Nation/SI snake strategy 2026 · Fantasy Football Blueprint: RB age cliff (2026-08-10), rookie RB workload signals (2026-08-03) · Fantasy Index: top-5 RB repeatability (2026) · PFF top-WR repeatability · Fantasy Points xTD · RotoViz breakout age / Dominator Rating · 4for4 production curves by age, sleepers after pick 150 (2026) · RotoBaller vacated targets 2026 · Sharp Football implied team totals · DynastyNerds draft capital · ESPN 2026 TD regression · Yahoo ADP risers/fallers (2026-08-18) · CBS/Yahoo first-round bust rates.
