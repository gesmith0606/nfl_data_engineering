# State-of-the-Art Research: Fantasy Projections & NFL Spread Models

**Date:** 2026-06-12
**Purpose:** Benchmark the best available systems, extract their methodology, and produce ranked, actionable ideas for closing our two measured gaps: (1) within-week rank-ordering vs Sleeper consensus (RB −0.08 Spearman, WR −0.056, QB −0.027), and (2) spread model stuck at ~52.9% OOF ATS.

---

## (a) Accuracy Benchmarks — what "best available" actually achieves

| Domain | System / Source | Measured Result | Sample / Caveat | Source |
|---|---|---|---|---|
| Fantasy weekly MAE | Vegas prop-derived rankings (ParlaySavant, FanDuel odds) | **4.76 MAE** vs DraftSharks 4.84; tied on start/sit | 13 weeks, 2025 season; vendor self-report but concrete head-to-head | [ParlaySavant test](https://www.parlaysavant.com/insights/can-vegas-betting-lines-beat-the-best-fantasy-rankings) |
| Fantasy weekly MAE | Our production heuristic | 4.71 MAE (half-PPR, 2022-24 W3-18) | Different player pool/window — not directly comparable to above, but same order of magnitude | internal |
| Fantasy weekly rank accuracy | FantasyPros contest winners: 2024 Tyler Orginski (JWB), 2025 Justin Boone (Yahoo); Sean Koerner (Action) 4x winner, never below 14th in 11 years | Scored as rank→points "accuracy gap," worst week dropped, 152+ experts | Winners rotate yearly; Koerner/Thorman (ETR) are the only consistently-top performers | [2024 results](https://www.fantasypros.com/2025/01/2024-fantasy-football-weekly-rankings-most-accurate-experts/), [2025 results](https://www.fantasypros.com/2026/01/2025-fantasy-football-rankings-most-accurate-experts/) |
| Fantasy consensus strength | FantasyPros ECR (40+ expert consensus) | 2nd-highest accuracy overall; top-10 at all 4 positions | Index-fund analogy holds: consensus beats nearly every individual expert | [FantasyPros ECR study](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/) |
| Fantasy source comparison | FFA aggregation study 2019-23 (CBS, FFToday, numberFire, NFL, FantasySharks, RTSports) | Simple **average of sources beats or ties the best single source**; single-source leaders are volatile year to year | MAE only; top-20 QB/TE, top-50 RB/WR | [FFA study](https://fantasyfootballanalytics.net/2024/12/which-fantasy-football-projections-are-most-accurate.html) |
| Spread ATS (public model, full slate) | nfelo | **56.97% vs OPENING line; 53.70% vs CLOSING line (−0.16% edge — does NOT beat close)**; 66.6% SU; +5.61% avg CLV per play | Since 2009, ~1,500+ games, verifiable live performance page | [nfelo performance](https://www.nfeloapp.com/games/nfl-model-performance/) |
| Spread ATS (selective picks) | Massey-Peabody (WSJ, Cade Massey + Rufus Peabody) | **55.4% lifetime on official picks** (314-256-18); "outperforms Vegas for an identifiable subset of games" | Selective betting, not full slate — this is near the practical ceiling | [Wharton interview](https://alumni.wharton.upenn.edu/all-stories/data-and-analytics/prof-cade-massey-explains-the-analytics-behind-his-nfl-rankings-how-data-science-led-this-undergrad-to-business-analytics/), [Data Colada](https://datacolada.org/14) |
| Spread ATS (academic) | Various ML papers | 53-58% claimed; break-even = 52.4% at −110 | Mostly small samples, often in-sample or single-season; treat skeptically | [arXiv systematic review](https://arxiv.org/pdf/2410.21484), [CMU Gimpel](https://www.cs.cmu.edu/~epxing/Class/10701-06f/project-reports/gimpel.pdf) |
| Market efficiency | Pinnacle closing lines | r² = 0.997 between closing lines and outcomes (397,935 games); +CLV bettors almost universally profitable, −CLV almost universally not | The closing line is effectively the truth; realistic sharp edge is **2-5% CLV**, not ATS% heroics | [Trademate CLV](https://tradematesports.medium.com/closing-line-the-most-important-metric-in-sports-trading-58e56cdb4458), [Pinnacle](https://www.pinnacle.com/betting-resources/en/educational/how-to-track-your-sports-betting-results-to-find-an-edge) |

**Calibration of our standing:** our 52.9% OOF ATS is *normal* for a competent full-slate model. nfelo — the best fully transparent public model — loses to the closing line. The realistic path is (a) beat openers, (b) bet selectively, (c) measure CLV, not chase 55%+ full-slate ATS. On fantasy, the realistic path to consensus-level rank-ordering runs through props, late updates, and opportunity decomposition (below).

---

## (b) Methodology Findings

### Q1. How the most accurate weekly projection systems work

**Who actually wins.** FantasyPros weekly contest winners 2024: Tyler Orginski overall; per-position Ben Wasley (QB), Joe Bond (RB), Sean Koerner (WR), Matt Schauf (TE). 2025: Justin Boone (Yahoo) overall; Pat Thorman (ETR) 2nd with 4 straight top-4 finishes. Sean Koerner (Action Network, ex-Excalibur sportsbook oddsmaker, FSTA "most accurate projections" 4x) is the most persistent name — and his approach is explicitly **odds-derived**: power ratings → game-level projections → player projections, organized into tiers, **updated continuously until Sunday lock** as injury/news arrives ([Koerner profile](https://www.actionnetwork.com/picks/profile/The_Oddsmaker), [FantasyLabs tiers](https://www.fantasylabs.com/articles/sean-koerners-fantasy-football-qb-rankings-and-tiers/)).

**The common architecture (Peabody, PFF, ETR, McFarland) is opportunity-first decomposition, not points-first:**

1. **Team plays projection** — pace/no-huddle trends, opponent pace (ETR's Thorman publishes snaps & pace analysis).
2. **Pass/run split conditioned on game state** — historical run/pass ratio *by leading/trailing/close*, weighted by the expected game state implied by **the spread** ([Rufus Peabody's full prop process](https://unabated.com/articles/pie-for-dinner-rufus-peabodys-nfl-player-prop-process)). PFF does the same via Greenline game projections: projected winners get RB carry volume, projected trailers get WR target volume ([PFF methodology](https://www.pff.com/news/fantasy-the-logic-behind-pffs-fantasy-projections)).
3. **Player share of the pie** — snap %, **route participation** (routes per dropback), **TPRR** (targets per route run), carry share, red-zone/goal-line share. McFarland: route participation × TPRR → projected target range; "opportunity is the lifeblood of fantasy performance" ([PFF utilization framework](https://www.pff.com/news/fantasy-football-rankings-and-strategy-articles-by-dwain-mcfarland)).
4. **Efficiency applied last** — yards per target/carry; PFF uniquely splits efficiency into context (OL run-block grade → yards before contact) vs. skill (yards after contact).
5. **Distribution, not point estimate** — Peabody simulates 10k outcomes to get mean vs median; PFF computes "a distribution of possible outcomes."

**ETR's in-season ML model** (Buy Leone): expected fantasy points **per individual opportunity** (each carry/target valued by team scoring expectation, air yards, down/distance, goal-line proximity) over the **last 6 weeks with recency weighting** ([ETR Buy Leone](https://establishtherun.com/buy-leone-rb-underperformers/)). This is XFP/expected-points-over-opportunity — the same concept as Scott Barrett's Expected Fantasy Points at Fantasy Points Data.

**Injury/news timing is a first-class input, not an afterthought.** FantasyPros snapshots rankings at TNF kickoff and again at Sunday 1pm ET ([methodology](https://www.fantasypros.com/about/faq/football-inseason-accuracy-methodology/)). Winners revise through Sunday-morning inactives (~11:30am ET). Vegas-derived rankings "update every hour... respond to injury news faster than any traditional fantasy site" — and that freshness alone beat a top-3 accuracy shop (DraftSharks) in 2025.

**Why consensus rank-ordering is hard to beat:** the efficient-market/index-fund effect. ECR finished 2nd overall and top-10 at every position; FFA found the plain average of sources beats the best single source because single-source skill is volatile. Beating an average of 40+ experts requires either (a) information they don't have, (b) information *later* than they have it, or (c) systematic decomposition they don't bother with. Props deliver (a)+(b); opportunity decomposition delivers (c).

### Q2. What data separates the best — and the props question

**Inputs the top systems credit:**
- **Routes run & route participation** (routes/dropback) — leading indicator of targets; role changes show in routes before points.
- **TPRR** — stickiest receiving skill stat: ~0.65 year-over-year correlation; prior-season TPRR has r²=0.36 to next-season targets ([Fantasy Points research](https://www.fantasypoints.com/nfl/articles/season/2023/fantasy-points-data-most-important-wr-stats)). First-downs-per-route-run is their newer favorite.
- **Air yards / aDOT** — converts target counts to yardage expectation; ETR values each target by air yards.
- **Red-zone / goal-line shares** — drives TD projection (we have this via graph features).
- **PFF grades** — used for the *efficiency* layer (OL run-blocking → YBC; coverage grades), not the volume layer. Volume ≫ efficiency for weekly rank-ordering.
- **Vegas team totals AND spreads** — totals for scoring environment, **spread for game script → run/pass split** (we only use the total multiplier; nobody stops there).

**KEY ANSWER — player props as input/benchmark: YES, this is real and measured.**
- Props are "essentially the sharpest per-player consensus": books move millions weekly and bake injury risk/benching probability into lines.
- **Unabated productized exactly this**: median prop line across books → invert the distribution → market-implied **mean** projection, updating as the market moves; explicitly intended to be "blended with existing or custom projections" ([Unabated market-based projections](https://unabated.com/articles/introducing-market-based-prop-projections)).
- **Measured result:** ParlaySavant's purely FanDuel-derived rankings beat DraftSharks 4.76 vs 4.84 MAE over 13 weeks of 2025 and tied on start/sit — with zero football modeling, just market reads + hourly refresh.
- Anytime-TD odds → implied TD probability is a direct, sharper replacement/blend for heuristic TD regression.
- Mechanical notes: prop medians ≠ means (skewed distributions — must adjust via over/under juice); props price in benching/injury, so they're "lower than expert projections" systematically for questionable players.

**Historical player-prop data — obtainability and price:**

| Vendor | Coverage | Price | Notes |
|---|---|---|---|
| **The Odds API** (we already integrate it) | Historical props since **May 3, 2023**, 5-min snapshots; game lines since June 2020 | $29/mo (20k credits) – $99/mo (200k); historical archive included on paid tiers; cost = 10 credits/region/market/event | **Best fit**: ~3 seasons of NFL props history; we can backfill 2023-2025 and snapshot 2026 live ([historical docs](https://the-odds-api.com/historical-odds-data/)) |
| SportsGameOdds | Historical props 2-3 seasons | $75–$299/mo | [pricing](https://sportsgameodds.com/comparing-odds-api-providers/) |
| OddsJam / OpticOdds | Full historical feed incl. openers, line moves, props | Enterprise, contact-sales (reputedly $1k+/mo) | Overkill for us |
| Unabated Props+ | Market-implied projections tool (not raw API) | ~$50-100/mo retail | Useful as methodology reference |
| Free (Kaggle/nflverse) | **No free historical player-prop dataset exists** | — | Game spreads/totals only (e.g. Kaggle nfl-scores-and-betting-data) |

Other paid data: Fantasy Points Data (Barrett — routes, TPRR, separation, XFP; standard/premium tiers ~$10-30/mo), PFF ($300-500/yr), FTN (already being spiked). Note: routes/TPRR are **computable free** from nflverse PBP participation (2020-25) — we already parse participation for graph features.

### Q3. Spread models — realistic state of the art

- **The market is near-efficient.** Pinnacle closing line r²=0.997 to outcomes. Break-even 52.4%. The correct success metric for a model is **CLV vs the opener** (bet Sunday-Wednesday lines, measure vs close), not raw ATS. Sharp professionals sustain **2-5% CLV**.
- **nfelo (fully transparent benchmark):** Elo + win-total-market initial ratings + custom HFA model + **QB performance/availability model (nfeloqb)** + rest/weather adjustments + **"market reversion" logic** (regress model spread toward Vegas spread, preserving only non-market signal; bet only on residual divergence). Result: +0.34% edge vs open, **−0.16% vs close**. Even with all of this, it doesn't beat the close ([nfelo about](https://www.nfeloapp.com/about/), [github](https://github.com/greerreNFL/nfelo)).
- **Massey-Peabody (55.4% lifetime, selective):** four factors — rushing, passing, scoring, play success — weighted **by predictive ability** (not explanatory), adjusted for HFA and game situation; bets only an "identifiable subset" where the model diverges from Vegas. Selectivity is the edge, not the model.
- **Features credible efforts use that we don't (or use weakly):**
  1. **QB availability/quality adjustment** — QB out swings lines 3-7 pts; nfeloqb is an open-source implementation of QB-adjusted ratings.
  2. **Market reversion / divergence betting** — treat the Vegas line as a feature with a strong prior; model only residuals; bet only large divergences. (Our 120-feature ensemble predicts margin directly — restructuring around line-residual is the standard sharp formulation.)
  3. **Opener timing** — the achievable edge lives in the open→close window. We just started Odds API capture; capturing openers + tracking CLV per pick is the single most informative evaluation change.
  4. **Discounted EPA (wepa)** — open-source framework that reweights EPA components by predictiveness ([github](https://github.com/greerreNFL/wepa)); analogous to Massey-Peabody's predictive weighting.
  5. **Weather (wind > 15 mph)** — worth 3-5 pts on totals, marginal on spreads ([Sports Insights](https://www.sportsinsights.com/blog/how-do-sharp-nfl-bettors-use-weather-forecasts-to-make-money/)). We killed totals, so low priority.
  6. **Line movement / steam detection** — needs the live-snapshot capture we just started; retrospective-only with current data.

### Q4. Open-source repos worth studying

| Repo | Why | Accuracy verifiable? |
|---|---|---|
| [greerreNFL/nfelo](https://github.com/greerreNFL/nfelo) + [nfeloqb](https://github.com/greerreNFL/nfeloqb) + [wepa](https://github.com/greerreNFL/wepa) + [nfl_cover_probability](https://github.com/greerreNFL/nfl_cover_probability) | Complete, maintained spread stack on nflverse: QB model, HFA, market reversion, cover probabilities | **Yes** — live [performance page](https://www.nfeloapp.com/games/nfl-model-performance/) since 2009 |
| [ffanalytics (FFA)](https://fantasyfootballanalytics.net/) R package | Projection scraping + weighted aggregation across sources; the "consensus blend" reference implementation | Yes — published MAE studies |
| Open Source Football ([opensourcefootball.com](https://opensourcefootball.com/)) | Peer-reviewed-ish nflverse analysis posts (game script, EPA predictiveness) | Mixed |
| Student/academic ML repos (zzhangusf, rohand24, etc.) | Weak baselines (QB MAE ~6) | No — skip |

---

## (c) Ranked Actionable Ideas

**#1. Prop-implied projections as anchor + benchmark (attacks rank-ordering directly).**
Data: The Odds API player props — receiving/rushing/passing yards, receptions, anytime TD. Backfill historical (May 2023→now, 5-min snapshots, covers 2023-2025 eval seasons) and snapshot 2026 weekly with our existing key. Cost: $29-99/mo tier we largely already pay; backfill is credit-cost only.
Mechanism: convert median line + juice → implied mean (Unabated method); use as (a) a *benchmark* (is our Spearman gap vs Sleeper also a gap vs props?), (b) a *blend input* (shrink our projection toward market-implied per-player mean), (c) per-player Vegas signal far sharper than team implied total.
Why it attacks the gap: props ARE the sharpest per-player consensus; a pure props ranking beat a top accuracy shop (4.76 vs 4.84 MAE). Within-week ordering is exactly what books price.

**#2. Late-update / freshness pipeline (attacks RB gap specifically).**
Data: already have (injuries, depth charts, props once #1 lands). Cost: engineering only.
Mechanism: regenerate projections at T-minus ~2h from Sunday lock incorporating inactives, prop line moves, and depth-chart changes — instead of a Tuesday-cron snapshot. Sleeper consensus updates near lock; we're being graded against a fresher opponent. RB committees reshuffled by Sunday inactives are the highest-variance case → plausibly a large slice of the −0.08 RB Spearman.

**#3. Opportunity-first decomposition of the heuristic (structural, attacks WR+RB ordering).**
Data: free — nflverse PBP participation (2020-25), already parsed for graph features; FTN spike supplements.
Mechanism: replace "rolling fantasy points" core with: team plays × pass rate(game-script-conditioned) × route participation × TPRR × aDOT → yards; carry share × game-script run tilt → RB volume. Points-based rolling averages conflate role and luck; routes/TPRR isolate role, which is what predicts the *order* of players within a week. Every top system (Peabody, PFF, ETR, McFarland) is built this way.

**#4. Spread-conditioned game-script volume shift (cheap, attacks RB ordering).**
Data: already have (spreads). Cost: small.
Mechanism: per-player volume multiplier from spread — favorites' lead RBs get carry boost, underdogs' pass-catchers get target boost (PFF/Peabody standard). We currently use only the implied-total multiplier, which moves *teams* up/down but not the run/pass mix *within* a team — i.e., it can't reorder an RB vs his own WR teammates.

**#5. Consensus/market blend layer (cheapest Spearman win).**
Data: Sleeper projections (already pulled) and/or prop-implied means from #1. Cost: trivial.
Mechanism: final projection = w·ours + (1−w)·consensus, w tuned per position on 2022-24. FFA evidence says the average beats the best single source; we are one source. Even w=0.5 should close most of the Spearman gap while preserving our QB/TE edge (tune w per position; keep w high where we already win).

**#6. Market-implied TD rates (upgrade existing TD regression).**
Data: anytime-TD props from #1. Cost: included in #1.
Mechanism: blend heuristic TD regression toward market-implied expected TDs (convert anytime-TD odds → Poisson λ). TDs are the highest-variance fantasy component and the books' TD pricing embeds red-zone role news we get late or never.

**#7. Spread model: reframe to line-residual + CLV evaluation + selectivity.**
Data: our new Odds API capture (openers + snapshots). Cost: engineering.
Mechanism: (a) predict residual vs Vegas line, not raw margin; (b) bet/flag only divergences ≥ threshold (Massey-Peabody selectivity); (c) grade by CLV vs close, not ATS%. Port nfeloqb-style QB availability adjustment (open source). Accept the evidence: 53-55% selective / +CLV vs openers is the actual frontier; nothing public beats the close.

**#8. Buy nothing yet (PFF/Fantasy Points Data deferred).**
Routes, TPRR, red-zone shares are computable free from nflverse participation. PFF grades matter mostly for the *efficiency* layer, which matters less than volume for weekly ordering. Re-evaluate after #1-#4 land: if WR efficiency residuals remain the gap, Fantasy Points Data (~$10-30/mo) before PFF ($300-500/yr).

---

## (d) Sources

**Fantasy accuracy / contests**
- https://www.fantasypros.com/2025/01/2024-fantasy-football-weekly-rankings-most-accurate-experts/
- https://www.fantasypros.com/2026/01/2025-fantasy-football-rankings-most-accurate-experts/
- https://www.fantasypros.com/about/faq/football-inseason-accuracy-methodology/
- https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/
- https://fantasyfootballanalytics.net/2024/12/which-fantasy-football-projections-are-most-accurate.html
- https://www.parlaysavant.com/insights/can-vegas-betting-lines-beat-the-best-fantasy-rankings
- https://www.4for4.com/4for4-fantasy-football-accuracy

**Methodology (projections)**
- https://unabated.com/articles/pie-for-dinner-rufus-peabodys-nfl-player-prop-process
- https://unabated.com/articles/introducing-market-based-prop-projections
- https://www.pff.com/news/fantasy-the-logic-behind-pffs-fantasy-projections
- https://www.pff.com/news/fantasy-football-rankings-and-strategy-articles-by-dwain-mcfarland
- https://establishtherun.com/buy-leone-rb-underperformers/
- https://www.actionnetwork.com/picks/profile/The_Oddsmaker
- https://www.fantasylabs.com/articles/sean-koerners-fantasy-football-qb-rankings-and-tiers/
- https://www.fantasypoints.com/nfl/articles/season/2023/fantasy-points-data-most-important-wr-stats

**Props data vendors**
- https://the-odds-api.com/historical-odds-data/
- https://sportsgameodds.com/comparing-odds-api-providers/
- https://oddsjam.com/odds-api

**Spread / betting markets**
- https://www.nfeloapp.com/games/nfl-model-performance/
- https://www.nfeloapp.com/about/
- https://github.com/greerreNFL/nfelo , /nfeloqb , /wepa , /nfl_cover_probability
- https://alumni.wharton.upenn.edu/all-stories/data-and-analytics/prof-cade-massey-explains-the-analytics-behind-his-nfl-rankings-how-data-science-led-this-undergrad-to-business-analytics/
- https://datacolada.org/14
- https://tradematesports.medium.com/closing-line-the-most-important-metric-in-sports-trading-58e56cdb4458
- https://www.pinnacle.com/betting-resources/en/educational/how-to-track-your-sports-betting-results-to-find-an-edge
- https://arxiv.org/pdf/2410.21484
- https://www.cs.cmu.edu/~epxing/Class/10701-06f/project-reports/gimpel.pdf
- https://www.sportsinsights.com/blog/how-do-sharp-nfl-bettors-use-weather-forecasts-to-make-money/

**Open source**
- https://github.com/greerreNFL (nfelo ecosystem)
- https://fantasyfootballanalytics.net/ (ffanalytics R package)
- https://opensourcefootball.com/
