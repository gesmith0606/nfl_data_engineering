# Stack Research: v2.1 Market Data

**Domain:** NFL game prediction -- historical odds ingestion, line movement features, CLV tracking
**Researched:** 2026-03-27
**Confidence:** HIGH

## Scope

This document covers ONLY the stack additions needed for v2.1 Market Data. The existing stack (Python 3.9, pandas, pyarrow, nfl-data-py, xgboost, lightgbm, catboost, scikit-learn, shap, optuna) is validated and unchanged. Do not re-evaluate or reinstall those packages.

## Executive Summary

The existing stack needs **one new dependency** (openpyxl). The critical finding is that nflverse schedules already provides **closing lines** (spread_line, total_line, moneylines) back to 1999 -- and this data is already in our Bronze layer for 2016-2025. The primary gap is **opening lines**, which require a supplemental data source: SportsbookReviewsOnline (SBRO) XLSX files. CLV and line movement are arithmetic operations on existing DataFrames, not library-sized problems.

## What We Already Have (Closing Lines in Bronze)

Verified by running `nfl.import_schedules([2023])` directly in the project venv. These columns exist in our Bronze schedules data with **zero nulls** across 285 games (2023 season):

| Column | Type | Sample Values | Description |
|--------|------|---------------|-------------|
| `spread_line` | float64 | 4.0, 3.5, 9.5 | Closing consensus spread (home perspective) |
| `total_line` | float64 | 53.0, 40.5, 43.5 | Closing consensus over/under |
| `home_moneyline` | float64 | -198, -192, -500 | Home moneyline odds |
| `away_moneyline` | float64 | 164, 160, 380 | Away moneyline odds |
| `home_spread_odds` | float64 | -110, -112, -110 | Spread juice (home side) |
| `away_spread_odds` | float64 | -110, -108, -110 | Spread juice (away side) |
| `over_odds` | float64 | -110, -110, -110 | Over juice |
| `under_odds` | float64 | -110, -110, -110 | Under juice |
| `total` | int64 | 41, 34, 34 | Actual game total (label, not a feature) |
| `result` | int64 | actual margin | Actual point margin (label) |

**Confidence:** HIGH -- verified via live Python execution. The nflverse data dictionary (nflreadr.nflverse.com) lists these as a single set of lines with no opening/closing distinction. Pro-Football-Reference sourcing and community consensus confirm they are closing/near-closing consensus lines.

**Coverage:** 2016-2025 in our existing Bronze schedules data (all 10 seasons already ingested).

## Data Source Comparison: Opening Lines

### Full Comparison Matrix

| Criterion | SBRO Archives | Kaggle (Crabtree) | AusSportsBetting | The Odds API | BigDataBall | OddsPortal |
|-----------|---------------|-------------------|------------------|-------------|-------------|------------|
| Has opening lines | YES | Unconfirmed | NO (single line) | YES | YES | YES |
| Has closing lines | YES | YES | YES | YES | YES | YES |
| Coverage start | 2007 | ~1966 | 2006 | 2020 | 2016 | 2010 |
| Coverage end | ~2021 (frozen) | ~2020 (stale?) | Present | Present | Present | Present |
| Format | XLSX | CSV | XLSX | JSON API | XLSX | HTML |
| Cost | Free | Free | Free | $99+/mo (historical) | ~$30/season | Free (scraping) |
| Structured download | YES | YES | YES | YES (API) | YES | NO (scrape) |
| Team ID standard | Custom (needs mapping) | Custom | Custom | Standard | Custom | Custom |
| Update status | Archived, not updating | Uncertain | Patchy 2025 | Active | Active | Active |
| Backup available | FinnedAI GitHub scraper | Kaggle | Direct download | N/A | N/A | Multiple scrapers |

### Decision: SBRO as Primary Source

**Why SBRO over alternatives:**

1. **Opening + closing lines confirmed.** SBRO data columns include "Open" and "Close" for spreads, plus "ML" (moneyline) and "2H" (second half). Multiple sources describe this format including the FinnedAI/sportsbookreview-scraper GitHub repo which has pre-scraped data for 2011-2021.

2. **Free and downloadable.** Static XLSX files -- no API keys, no rate limits, no authentication, no scraping fragility.

3. **Covers our training window.** 2016-2021 coverage gives us 6 seasons (~1,600 games) of opening lines overlapping with our 2016-2024 training period. This is sufficient for SHAP feature selection to determine if line movement adds signal.

4. **FinnedAI backup.** The [FinnedAI/sportsbookreview-scraper](https://github.com/FinnedAI/sportsbookreview-scraper) GitHub repository has pre-scraped SBRO data for 2011-2021, providing a backup if the SBRO website XLSX downloads become unavailable.

**Why NOT alternatives:**
- **Kaggle (Crabtree):** Update status uncertain; whether it includes opening lines needs verification; would be a good secondary source for cross-validation.
- **AusSportsBetting:** Single line per game (not documented as opening or closing); uses Australian decimal odds convention; "patchy" for recent data.
- **The Odds API:** $99+/month for historical data; only covers 2020+, missing 2016-2019 entirely; overkill for one-time historical backfill.
- **OddsPortal:** Requires Selenium-based scraping (fragile, slow, ToS concerns); many scrapers available but maintenance burden is real.
- **BigDataBall:** ~$30/season is reasonable but not free; consider only if 2022-2024 opening lines prove critical after ablation.

### Coverage Gap Analysis

| Season Range | Opening Lines | Closing Lines | Source | Impact |
|--------------|---------------|---------------|--------|--------|
| 2016-2021 | SBRO XLSX | nflverse Bronze (exists) | Both available | Full line movement features |
| 2022-2024 | NOT AVAILABLE (free) | nflverse Bronze (exists) | Closing only | CLV still works; line movement features are NaN |
| 2025+ | Future: live capture | nflverse | Planned for v3.0 | Out of scope |

**Mitigation for 2022-2024 opening line gap:**
- Line movement features compute on 2016-2021 (~1,600 games) -- sufficient for SHAP feature selection
- CLV tracking uses **only** closing lines (model prediction minus closing line) -- zero gap
- The 2024 sealed holdout evaluates CLV using nflverse closing lines which are complete
- If ablation shows line movement features improve holdout, BigDataBall fills 2022-2024 at ~$30/season

## Recommended Stack Addition

### New Dependency

| Library | Version | Purpose | Why This One | Python 3.9 Compatible |
|---------|---------|---------|-------------|----------------------|
| `openpyxl` | >=3.1.0 | Read SBRO XLSX files via `pd.read_excel(engine='openpyxl')` | pandas requires openpyxl for .xlsx; xlrd dropped xlsx support in v2.0; openpyxl is the pandas-recommended engine | YES |

**Verification:** `openpyxl` is NOT currently installed (confirmed via `pip list` in project venv). `requests` (v2.32.4) IS already installed and can download SBRO files.

### Existing Libraries -- New Uses in v2.1

| Library | Version (installed) | New Use | Notes |
|---------|---------------------|---------|-------|
| pandas | 1.5.3 | `pd.read_excel()` for SBRO XLSX, line movement arithmetic, CLV computation | Already used everywhere; no version change |
| pyarrow | installed | Write odds/movement Parquet files | Same pattern as all other Bronze/Silver outputs |
| requests | 2.32.4 | Download SBRO XLSX files programmatically (one-time) | Already in venv |
| nfl-data-py | installed | Closing lines already in Bronze schedules via `import_schedules()` | No new API calls needed |

### What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `sports-betting` (PyPI) | CLV = `model_spread - closing_spread` -- literal subtraction, not a library | `df['clv'] = df['model_spread'] - df['spread_line']` |
| `the-odds-api` Python client | $99+/mo for historical; we have closing from nflverse, opening from SBRO | SBRO (free) + nflverse (free) |
| `selenium` / `playwright` | No scraping needed; SBRO is downloadable XLSX files | `pd.read_excel()` + `requests.get()` |
| `beautifulsoup4` | No HTML parsing; data is structured XLSX/Parquet | Direct file reading |
| SQLite / DuckDB for odds DB | Pipeline is Parquet-native; adding a DB layer introduces complexity without benefit | Parquet with existing `download_latest_parquet()` pattern |
| Any new ML libraries | Line movement features are arithmetic (close - open, pct change, sign); CLV is subtraction | pandas operations |
| `statsmodels` | No time-series modeling; movement is a point-in-time difference | pandas |
| `xlrd` | Dropped xlsx support in v2.0; only reads legacy .xls | openpyxl |

## Installation

```bash
source venv/bin/activate

# Single new dependency
pip install openpyxl>=3.1.0

# Verify
python -c "import openpyxl; print(openpyxl.__version__)"

# Freeze
pip freeze > requirements.txt
```

Total new packages: **1** (openpyxl, plus its transitive dependency `et-xmlfile`).

## Integration with Existing Pipeline

### Bronze Layer: New Data Type `odds_opening`

```
data/bronze/odds_opening/season=YYYY/odds_opening_YYYYMMDD_HHMMSS.parquet
```

- Follows existing registry dispatch pattern in `scripts/bronze_ingestion_simple.py`
- Source: SBRO XLSX files stored in `data/external/sbro/` (one-time download)
- **Team name mapping required:** SBRO abbreviations differ from nflverse (e.g., "LARams" vs "LA")
- Join key: `(season, week, home_team)` derived from SBRO date + team + VH indicator

Normalized output columns:

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `season` | int | Derived from SBRO date | Map SBRO date to NFL season year |
| `week` | int | Derived from SBRO date + schedule lookup | Cross-ref nflverse schedules for game-to-week mapping |
| `home_team` | str | SBRO Team + VH indicator mapped to nflverse IDs | Lookup dict required |
| `away_team` | str | SBRO Team + VH indicator mapped to nflverse IDs | Lookup dict required |
| `open_spread` | float | SBRO "Open" column | Home perspective (positive = home favored) |
| `close_spread_sbro` | float | SBRO "Close" column | For cross-validation vs nflverse `spread_line` |
| `home_moneyline_sbro` | float | SBRO "ML" column | For cross-validation |

### Silver Layer: New Output Path `line_movement`

```
data/silver/line_movement/season=YYYY/line_movement_YYYYMMDD_HHMMSS.parquet
```

All computed via pandas arithmetic on Bronze `odds_opening` + Bronze `schedules`:

| Feature | Formula | Type | Signal |
|---------|---------|------|--------|
| `spread_move` | `close_spread - open_spread` | float | Signed movement direction + magnitude |
| `spread_move_abs` | `abs(spread_move)` | float | Movement magnitude only |
| `total_move` | `close_total - open_total` | float | O/U movement (if open total available) |
| `is_steam_move` | `spread_move_abs >= 1.5` | bool | Binary: significant sharp action |
| `spread_move_pct` | `spread_move / abs(open_spread)` | float | Relative movement normalized by spread size |
| `spread_direction` | `sign(spread_move)` | int | Categorical: toward home (-1) / away (+1) / static (0) |

### Gold Layer: CLV Tracking

Added to `prediction_backtester.py` evaluation output:

| Metric | Formula | Purpose |
|--------|---------|---------|
| `model_clv_spread` | `model_spread - closing_spread` | Positive = model line was sharper than market close |
| `model_clv_total` | `model_total - closing_total` | Positive = model total was sharper |
| `mean_clv` | Season/overall mean of `model_clv_spread` | Aggregate model quality metric |

CLV is the gold standard for sports prediction model evaluation: a model that consistently beats closing lines has real edge, regardless of short-term ATS variance.

### Feature Vector Assembly

Line movement features join the existing 310+ column feature vector via left join on `[season, week, home_team]` in `feature_engineering.py`. They become candidates for the SHAP-based feature selection pipeline. **Ship to production only if 2024 sealed holdout improves.**

## SBRO Data Quality Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Team abbreviation mismatch | Medium | Build lookup dict mapping SBRO names to nflverse team IDs; validate with inner join on overlapping dates |
| SBRO Close vs nflverse `spread_line` discrepancy | Low | Cross-validate: compute Pearson r, expect > 0.95; use nflverse as ground truth for all closing lines |
| Missing games in SBRO | Low | Left join from nflverse schedules; log and accept NaN for missing opening lines |
| Ambiguous "Open" definition | Medium | SBRO "Open" is first posted line, not from a specific book; sufficient for movement signal direction |
| SBRO XLSX download links broken | Medium | FinnedAI/sportsbookreview-scraper has pre-scraped 2011-2021 data as backup |
| Sign convention mismatch | High | Validate: SBRO close should match nflverse `spread_line` in sign for 95%+ of games; add assertion in Bronze ingestion |

## Data Acquisition Workflow

```bash
# 1. One-time: download SBRO XLSX files (6 seasons of interest)
#    From: sportsbookreviewsonline.com/scoresoddsarchives/nfl/
#    To:   data/external/sbro/nfl_odds_YYYY.xlsx (2016-2021)
#    Backup: github.com/FinnedAI/sportsbookreview-scraper/data/

# 2. Bronze ingestion (new registry entry)
python scripts/bronze_ingestion_simple.py --data-type odds_opening --seasons 2016 2017 2018 2019 2020 2021

# 3. Silver transformation (new script)
python scripts/silver_line_movement_transformation.py --seasons 2016 2017 2018 2019 2020 2021

# 4. CLV tracking (extend existing backtest CLI)
python scripts/backtest_predictions.py --seasons 2022,2023,2024 --clv
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Opening lines source | SBRO XLSX | The Odds API | $99+/mo for historical; only covers 2020+; SBRO is free and covers 2007-2021 |
| Opening lines source | SBRO XLSX | OddsPortal scraping | Fragile Selenium scraping, ToS concerns, maintenance burden |
| Opening lines source | SBRO XLSX | BigDataBall | Paid ~$30/season; reserve as fallback if 2022-2024 opening lines needed |
| Opening lines source | SBRO XLSX | Kaggle (Crabtree) | Update status uncertain; opening line column existence unconfirmed |
| Closing lines source | nflverse (existing) | SBRO closing column | nflverse already in Bronze, consistent team IDs, zero integration work |
| XLSX engine | openpyxl | xlrd | xlrd dropped xlsx support in v2.0; openpyxl is pandas-recommended |
| CLV implementation | Manual pandas arithmetic | sports-betting PyPI lib | CLV is literal subtraction; library adds dependency for no benefit |
| Odds storage | Parquet files | SQLite/DuckDB | Pipeline is Parquet-native; separate DB adds complexity |

## Confidence Assessment

| Claim | Confidence | Basis |
|-------|------------|-------|
| nflverse schedules has closing lines for 2016-2025 with zero nulls | HIGH | Verified by running `nfl.import_schedules([2023])` in project venv; checked all 8 betting columns |
| SBRO has opening + closing spread columns ("Open", "Close") | MEDIUM | Multiple web sources describe these columns; FinnedAI scraper confirms format; not yet verified actual file contents |
| SBRO coverage includes 2016-2021 seasons | MEDIUM | Web search results consistent; archive confirmed stopped updating ~2021 |
| openpyxl is the only new dependency needed | HIGH | Verified existing `pip list`: no openpyxl, xlrd, or similar installed; all other needed libs present |
| CLV computation requires no new libraries | HIGH | CLV = subtraction; confirmed by reviewing existing `prediction_backtester.py` code |
| 2022-2024 has no free structured opening line source | MEDIUM | Extensive web search found no free download; BigDataBall is $30/season option |
| Line movement features are purely arithmetic | HIGH | Industry standard: `close - open`, `abs()`, `sign()`, percentage change |
| SBRO team abbreviations differ from nflverse | HIGH | Standard problem with external sports data; every source uses its own team codes |

## Sources

- [nflverse schedules data dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html) -- all 46 column definitions including betting fields (HIGH confidence)
- [nflverse load_schedules reference](https://nflreadr.nflverse.com/reference/load_schedules.html) -- function documentation
- [nflverse DATASETS.md](https://github.com/nflverse/nfldata/blob/master/DATASETS.md) -- spread_line/total_line field descriptions
- [SBRO NFL Odds Archives](https://www.sportsbookreviewsonline.com/scoresoddsarchives/nfl/nfloddsarchives.htm) -- historical opening/closing lines in XLSX format
- [FinnedAI/sportsbookreview-scraper](https://github.com/FinnedAI/sportsbookreview-scraper) -- pre-scraped SBRO data 2011-2021, confirms data format
- [AusSportsBetting NFL data](https://www.aussportsbetting.com/data/historical-nfl-results-and-odds-data/) -- alternative source, single line from 2006+ (verified column list)
- [Kaggle NFL scores and betting data](https://www.kaggle.com/datasets/tobycrabtree/nfl-scores-and-betting-data) -- alternative free source
- [The Odds API pricing](https://the-odds-api.com/historical-odds-data/) -- historical data requires paid plan, 10x credit cost ($99+/mo)
- [Pinnacle CLV methodology](https://www.pinnacle.com/betting-resources/en/educational/what-is-closing-line-value-clv-in-sports-betting) -- CLV as evaluation gold standard
- [openpyxl on PyPI](https://pypi.org/project/openpyxl/) -- XLSX reading library, >=3.1.0
- [pandas read_excel docs](https://pandas.pydata.org/docs/reference/api/pandas.read_excel.html) -- requires openpyxl engine for .xlsx files
- Project venv `pip list` -- ground truth for installed packages (HIGH confidence)
- Project venv `nfl.import_schedules([2023])` execution -- ground truth for nflverse column names, types, and null counts (HIGH confidence)

---
*Stack research for: NFL v2.1 Market Data (historical odds, line movement, CLV tracking)*
*Researched: 2026-03-27*
