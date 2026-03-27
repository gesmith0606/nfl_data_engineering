# Project Research Summary

**Project:** NFL v2.1 Market Data
**Domain:** Historical odds ingestion, line movement features, CLV tracking for NFL game prediction
**Researched:** 2026-03-27
**Confidence:** HIGH

## Executive Summary

The v2.1 Market Data milestone adds historical betting line data to an existing, well-validated NFL prediction pipeline. The core discovery is that the heaviest lift is already done: nflverse schedules (already in Bronze for 2016-2025) contains complete closing lines with zero nulls — spread_line, total_line, and moneylines verified by live Python execution in the project venv. The only missing data is opening lines, required to compute line movement features. SBRO (SportsbookReviewsOnline) XLSX archives are the recommended free source for 2016-2021, with FinnedAI/sportsbookreview-scraper as a backup. The single new dependency is `openpyxl` for XLSX parsing. CLV and all line movement computations are arithmetic operations on existing DataFrames, not library-sized problems.

The recommended build order is: (1) Bronze odds ingestion with careful team name mapping and game_id joining from nflverse schedules, (2) Silver line movement feature computation with explicit temporal categorization to prevent leakage, (3) CLV tracking added to the backtester using nflverse closing lines already in Gold. A clean data quality gate after Bronze ingestion — asserting 95%+ closing line agreement between SBRO and nflverse — is the most important single step before building anything downstream.

The primary risk is not technical complexity but data quality: SBRO team abbreviations differ from nflverse, sign convention for spreads must be validated empirically, and closing line leakage into prediction features must be strictly prevented. Line movement features (spread_shift, etc.) are valid for historical backtesting and ablation but cannot be used in live predictions since the closing line is only known at kickoff. If the ablation shows opening_spread dominates SHAP importance (>30%), the model may become a thin market wrapper rather than a genuine performance-based predictor — this is a design choice to document and decide, not a bug.

## Key Findings

### Recommended Stack

The existing stack requires exactly one new dependency: `openpyxl >= 3.1.0` for reading SBRO XLSX files via `pd.read_excel(engine='openpyxl')`. All other libraries (pandas, pyarrow, requests, nfl-data-py, xgboost, scikit-learn, shap) are already installed and cover every required operation. The `requests` library handles SBRO file downloads. CLV computation is a pandas subtraction expression, not a library concern.

**Core technologies:**
- `openpyxl >= 3.1.0`: XLSX parsing — only new dependency; xlrd is not an option (dropped .xlsx support in v2.0; openpyxl is the pandas-recommended engine)
- `pandas 1.5.3` (existing): `pd.read_excel()`, line movement arithmetic, CLV computation — no version change needed
- `nfl-data-py` (existing): closing lines already in Bronze schedules via `import_schedules()` — no new API calls required
- `pyarrow` (existing): write Bronze/Silver Parquet outputs following existing timestamped filename pattern
- `requests 2.32.4` (existing): one-time SBRO XLSX file downloads

**What NOT to add:** sports-betting PyPI library (CLV is literal subtraction), The Odds API ($99+/mo, only covers 2020+), Selenium/BeautifulSoup (no scraping needed), SQLite/DuckDB (pipeline is Parquet-native), statsmodels (movement is point-in-time arithmetic).

### Expected Features

**Must have (table stakes):**
- CLV tracking — gold standard for model evaluation; compares model line at prediction time vs closing line; required for any serious betting model validation
- Opening/closing line pairs in Bronze — foundation for all downstream line movement analysis
- Opening-to-closing spread and total shifts — most basic line movement signals once Bronze data exists

**Should have (competitive differentiators):**
- Line movement magnitude — absolute movement >1.5 pts correlates with sharp action; binary steam move flag
- Opening spread as candidate prediction feature — market's initial assessment; pre-game knowable; subject to ablation
- Signed spread movement direction — directional shift captures where sharp money went
- Key number crossing flag — movement across NFL key numbers 3, 7, 10 carries disproportionate significance

**Defer to v2.2+:**
- No-vig implied probability — requires devigging logic; save for v2.2 Betting Framework
- Real-time line tracking — requires live API polling infrastructure; out of scope for batch pipeline
- Public betting percentages — no free reliable source
- Multi-book line comparison — marginal signal for game-level models
- Player prop odds, in-game live odds, futures — different scope entirely

**CRITICAL leakage note:** Line movement features using the closing line (spread_shift, etc.) are NOT pre-game knowable. They are valid for historical backtesting and ablation but constitute leakage if used as live prediction features. Only `opening_spread` and `opening_total` can safely be live prediction features. This distinction must be enforced in `get_feature_columns()`.

### Architecture Approach

The integration follows the existing medallion architecture pattern without structural changes. Bronze adds a new `odds` data type via the existing registry dispatch pattern in `bronze_ingestion_simple.py`. Silver adds a new `market_data` path under `data/silver/teams/` computed by a new `src/market_analytics.py` following the exact same structure as `team_analytics.py`. The critical architectural constraint: Silver market_data MUST be reshaped to per-team-per-week rows (two rows per game — home and away) to join cleanly in `_assemble_team_features()`. CLV tracking is purely additive to `src/prediction_backtester.py` and uses nflverse closing lines already in the assembled Gold DataFrame — no additional data join required.

**Major components:**
1. `scripts/bronze_odds_ingestion.py` — Download SBRO XLSX, normalize schema, map team names to nflverse IDs, cross-validate closing lines, write `data/bronze/odds/season=YYYY/`
2. `src/market_analytics.py` — Read Bronze odds + schedules, compute movement features, reshape to per-team-per-week with sign flips for directional features, write `data/silver/teams/market_data/season=YYYY/`
3. `scripts/silver_market_transformation.py` — CLI wrapper for market_analytics.py following existing CLI pattern
4. `src/feature_engineering.py` (modified) — Add market_data to Silver source loop; extend `_PRE_GAME_CONTEXT` with `opening_spread`, `opening_total`; document closing-line movement features as retrospective-only
5. `src/prediction_backtester.py` (modified) — Add `evaluate_clv()` function; CLV uses nflverse spread_line/total_line already in Gold DataFrame

**Unchanged:** ensemble training, XGBoost/LGB/CB models, feature selection pipeline, prediction generation, all existing Silver transforms, all existing Gold outputs.

### Critical Pitfalls

1. **Closing line leakage as prediction feature** — spread_shift and all closing-line-derived features are only known at kickoff. For live predictions use only `opening_spread`/`opening_total`. Red flag: adding line movement features improves ATS accuracy >5% — check for leakage.

2. **Team name mapping errors** — SBRO abbreviations differ from nflverse (e.g., "JAC" vs "JAX", "LAR" vs "LA", Washington name changes across seasons). Silent join failures mean missing market data. Prevention: explicit mapping dict; assert every nflverse game_id gets a matching odds row after join.

3. **game_id construction mismatch** — Do not construct game_id independently from SBRO data. Join external odds to nflverse schedules by `(season, week, home_team, away_team)` or `(gameday, home_team)` to inherit the correct nflverse game_id. Assert zero orphan rows after merge.

4. **Duplicate closing line sources** — nflverse spread_line/total_line is canonical truth. Do not store SBRO closing lines as a second truth source. Cross-validate SBRO close vs nflverse close as a data quality check only; assert >95% of games are within 1.0 point of each other.

5. **Sign convention confusion** — SBRO may express spread from the favorite's perspective; nflverse uses home-team perspective. Empirically validate: for clearly home-favored games, check sign alignment. Compute Pearson r between SBRO open and nflverse close — expect >0.95 before proceeding.

## Implications for Roadmap

The natural phase structure follows Bronze → Silver → Gold data flow with an explicit ablation/evaluation gate at the end. Three phases with clear dependencies.

### Phase 1: Bronze Odds Ingestion

**Rationale:** Everything downstream depends on clean Bronze data. Team name mapping and game_id joining are the highest-risk steps in the entire milestone. Completing and validating Bronze before any Silver work prevents cascading data quality errors.
**Delivers:** `data/bronze/odds/season=YYYY/` Parquet for 2016-2021 (opening + cross-validated closing lines per game), new `odds` entry in bronze_ingestion_simple.py registry, team name mapping dict, data quality assertions (row counts vs expected games per season, sign convention check, closing line cross-validation at 95%+ agreement).
**Addresses:** Opening/closing line pairs (table stakes), data foundation for all downstream features.
**Avoids:** Team name mapping errors (Pitfall 3), game_id mismatch (Pitfall 4), duplicate closing line sources (Pitfall 2), sign convention confusion (Pitfall 5), Excel parsing edge cases (Pitfall 10).
**Research flag:** Standard pattern (follows existing registry-driven Bronze ingestion). Inspect actual SBRO XLSX file before writing the parser — do not assume column names from web descriptions. FinnedAI/sportsbookreview-scraper provides a secondary format reference.

### Phase 2: Silver Line Movement Features + Feature Integration

**Rationale:** Depends on validated Bronze odds data from Phase 1. Silver transform follows the established team_analytics.py pattern. Feature integration in feature_engineering.py requires careful temporal categorization — this is where leakage is introduced if not handled deliberately.
**Delivers:** `src/market_analytics.py`, `scripts/silver_market_transformation.py`, `data/silver/teams/market_data/season=YYYY/` for 2016-2021, updated `feature_engineering.py` with `opening_spread`/`opening_total` in `_PRE_GAME_CONTEXT`, documented retrospective-only status for closing-line-derived features.
**Uses:** pandas arithmetic (spread_shift, spread_move_abs, spread_move_dir, total_shift, crosses_key_spread), existing Silver transform pattern, per-team-per-week reshape with explicit symmetric/directional feature categorization.
**Implements:** Market analytics module, Silver market_data path, feature assembly integration.
**Avoids:** Closing line leakage (Pitfall 1), per-team reshape sign errors for symmetric vs directional features (Pitfall 7), opening line domination awareness built in from the start (Pitfall 8).
**Research flag:** Standard pattern for Silver transform. The temporal feature categorization (which features are pre-game knowable vs retrospective) is the one design decision requiring explicit review — get this wrong and every ablation result is invalid.

### Phase 3: CLV Tracking + Ablation Evaluation

**Rationale:** Comes last because it consumes both Gold predictions (existing) and the closing lines from nflverse already in Bronze/Gold. CLV tracking does not require Phase 2 market data at all — it uses nflverse spread_line. The ablation testing requires Phase 2 features to exist. This is the value gate: the phase produces the ship-or-skip decision for market features.
**Delivers:** `evaluate_clv()` in prediction_backtester.py, CLV metrics in backtest report (mean_clv, pct_beating_close, clv_by_season), ablation results for opening_spread and line movement features on 2024 sealed holdout, SHAP importance report, go/no-go recommendation for including market features in the production model.
**Addresses:** CLV tracking (table stakes), movement magnitude ablation, opening spread as feature (ablation-gated, not shipped by default).
**Avoids:** CLV without no-vig adjustment (Pitfall 9 — acceptable for v2.1, documented as known limitation), opening line domination (Pitfall 8 — detected via SHAP importance threshold check at 30%).
**Research flag:** CLV computation is standard arithmetic, no research needed. The ablation outcome is empirically unknown — if opening_spread dominates SHAP importance, team must decide between a market-informed model vs a pure performance model. This is a product decision, not a technical one.

### Phase Ordering Rationale

- Bronze before Silver: market_analytics.py reads Bronze odds Parquet; no Bronze data means no Silver compute possible
- Silver before ablation: feature_engineering.py must include market_data in the assembly loop before ablation can test market features
- CLV independent of Phases 1-2: CLV uses nflverse closing lines from existing Bronze/Gold — could ship as a standalone improvement without any SBRO data; ordered last to bundle with the ablation evaluation decision
- Coverage gap (2022-2024 has no free opening lines) is explicitly acceptable: CLV works on all 10 seasons; line movement features train on 2016-2021 (~1,600 games) which is sufficient for SHAP feature selection; if ablation shows material signal, BigDataBall at ~$30/season fills the 2022-2024 gap post-v2.1

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Bronze ingestion):** Inspect actual SBRO XLSX file format before finalizing the ingestion script. Web descriptions of column names may not match the actual file. Validate one season's data end-to-end (row counts, team names, sign convention) as a mandatory spike before writing production ingestion code.
- **Phase 3 (Ablation outcome):** SHAP importance distribution for opening_spread is unknown in advance. If it dominates (>30%), the team must decide whether a market-informed model is the desired direction. No research resolves this — it is an empirical outcome and a product decision.

Phases with standard patterns (can skip research-phase):
- **Phase 2 (Silver transform):** Follows exact pattern of team_analytics.py → silver_team_transformation.py. Well-documented internal pattern; the only non-standard element is the per-team reshape with sign flips, which is addressed in ARCHITECTURE.md.
- **Phase 3 (CLV implementation):** CLV = model_spread - closing_spread. Trivial arithmetic. No research needed for implementation, only for the interpretation of results.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | nflverse closing lines verified by running live Python in project venv; openpyxl confirmed as only missing dependency via pip list |
| Features | MEDIUM-HIGH | Feature definitions are unambiguous arithmetic; leakage temporal categorization is definitive; SBRO column names confirmed by multiple independent sources but actual file not yet opened |
| Architecture | HIGH | Based on direct inspection of feature_engineering.py, config.py, and prediction_backtester.py; join pattern, leakage guard, and assembly loop are confirmed code paths |
| Pitfalls | HIGH | Team name mapping, game_id matching, sign convention, and leakage pitfalls are well-known external data integration problems with established mitigations; validated against actual codebase structure |

**Overall confidence:** HIGH

### Gaps to Address

- **SBRO XLSX actual column names:** Research confirms the data exists and describes the format, but the actual file has not been opened and parsed. The ingestion script must inspect a real file before any parser code is written. Mitigation: download one SBRO XLSX as the first task in Phase 1 and validate column names, row structure, and game counts before writing ingestion logic.
- **2022-2024 opening line coverage:** No free structured source found. Line movement features will have NaN for 3 of 9 training seasons. Ablation on 2016-2021 (6 seasons, ~1,600 games) is sufficient for SHAP feature selection. If line movement features prove material, BigDataBall (~$30/season) fills the gap post-v2.1.
- **Opening line dominance in model:** Whether `opening_spread` as a prediction feature provides genuine value vs re-encoding market consensus is empirically unknown. This is resolved by the Phase 3 ablation, not by research.
- **SBRO site availability:** The SBRO archive stopped updating circa 2021 and could go offline. The FinnedAI/sportsbookreview-scraper repo provides pre-scraped 2011-2021 data as a backup; link should be verified at project start.

## Sources

### Primary (HIGH confidence)
- Project venv `nfl.import_schedules([2023])` live execution — verified 8 betting columns, zero nulls, 285 games (2023 season)
- Project venv `pip list` — verified openpyxl not installed; requests, pandas, pyarrow confirmed present
- Direct inspection of `src/feature_engineering.py` (lines 168-415) — join pattern, `get_feature_columns()`, `_PRE_GAME_CONTEXT` definition, leakage guard
- Direct inspection of `src/config.py` — SILVER_TEAM_LOCAL_DIRS, LABEL_COLUMNS structure
- Direct inspection of `src/prediction_backtester.py` — existing evaluation functions and output format
- [nflverse schedules data dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html) — all 46 column definitions including spread_line, total_line, moneylines
- [openpyxl on PyPI](https://pypi.org/project/openpyxl/) — XLSX engine, Python 3.9 compatible, >=3.1.0

### Secondary (MEDIUM confidence)
- [SBRO NFL Odds Archives](https://www.sportsbookreviewsonline.com/scoresoddsarchives/nfl/nfloddsarchives.htm) — XLSX format, Open/Close column descriptions; not yet verified against actual downloaded file
- [FinnedAI/sportsbookreview-scraper](https://github.com/FinnedAI/sportsbookreview-scraper) — pre-scraped SBRO data 2011-2021; confirms data format structure and column names
- [Pinnacle CLV methodology](https://www.pinnacle.com/betting-resources/en/educational/what-is-closing-line-value-clv-in-sports-betting) — CLV as evaluation gold standard
- [Action Network: Reverse Line Movement](https://www.actionnetwork.com/education/reverse-line-movement) — line movement concepts and steam move thresholds
- [Dimers: How to Read Line Movement](https://www.dimers.com/sports-betting-101/sports-betting-explained/how-to-read-line-movement-in-sports-betting) — NFL key numbers (3, 7, 10)

### Tertiary (LOW confidence)
- [Kaggle NFL scores and betting data (Crabtree)](https://www.kaggle.com/datasets/tobycrabtree/nfl-scores-and-betting-data) — alternative source; update status uncertain; opening line column presence unconfirmed; rejected as primary
- [AusSportsBetting NFL data](https://www.aussportsbetting.com/data/historical-nfl-results-and-odds-data/) — alternative source; verified single-line-per-game format only (not opening/closing pair); rejected

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
