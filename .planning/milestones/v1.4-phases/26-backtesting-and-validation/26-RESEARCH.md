# Phase 26: Backtesting and Validation - Research

**Researched:** 2026-03-21
**Domain:** Sports betting backtesting, ATS evaluation, holdout validation
**Confidence:** HIGH

## Summary

Phase 26 validates the XGBoost spread and total models built in Phase 25 against historical Vegas closing lines. The core deliverable is a `scripts/backtest_predictions.py` CLI that computes ATS (against the spread) accuracy, vig-adjusted profit/loss, ROI, and per-season stability metrics. The sealed 2024 holdout season must be evaluated using a model that never saw 2024 data during training.

All required data is already available: Bronze schedules contain `spread_line` and `total_line` for all 2,367 regular-season games (2016-2024) with zero nulls. The models from Phase 25 are saved as JSON with metadata sidecars. The existing `scripts/backtest_projections.py` (fantasy) provides a proven CLI pattern to follow.

**Primary recommendation:** Build a `src/prediction_backtester.py` library module for ATS/O-U evaluation logic, then a `scripts/backtest_predictions.py` CLI that loads trained models, generates predictions per game, and produces a formatted report with ATS accuracy, profit, ROI, and per-season breakdown.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BACK-01 | ATS accuracy computed against historical closing lines with vig-adjusted profit/loss | spread_line/total_line confirmed in Bronze schedules for all seasons (0% null). ATS logic: home covers when actual_margin > spread_line. Vig: -110 standard = 4.545% per bet. |
| BACK-02 | 2024 season sealed as untouched holdout for final model validation | HOLDOUT_SEASON=2024 in config.py. train_final_model() trains on seasons < 2024. load_model() retrieves saved model. 272 games available for holdout eval. |
| BACK-03 | Per-season stability analysis across training and validation windows | walk_forward_cv() already returns per-fold details. Backtest script computes per-season ATS accuracy to show stability/degradation across 2016-2024. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | existing | DataFrame manipulation for game-level backtest results | Already used throughout project |
| numpy | existing | Statistical computations (cumulative profit, std dev) | Already used throughout project |
| xgboost | existing | Load and predict from saved models | Already installed from Phase 25 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | existing | Test backtest logic with synthetic data | Test ATS computation, profit math |

No new libraries needed. All computation is basic arithmetic on DataFrames.

## Architecture Patterns

### Recommended Project Structure
```
src/
    prediction_backtester.py    # NEW: ATS/OU evaluation, profit accounting, stability analysis
scripts/
    backtest_predictions.py     # NEW: CLI for running backtests and printing reports
tests/
    test_prediction_backtester.py  # NEW: Unit tests for backtest logic
```

### Pattern 1: Backtest Evaluation Pipeline
**What:** Load model -> assemble features -> predict -> join with Vegas lines -> compute ATS metrics
**When to use:** Every backtest run
**Example:**
```python
# 1. Load trained model
model, metadata = load_model("spread", model_dir=MODEL_DIR)

# 2. Assemble game features (includes spread_line, total_line, actual_margin, actual_total)
all_data = assemble_multiyear_features(PREDICTION_SEASONS)
feature_cols = get_feature_columns(all_data)

# 3. Predict
all_data["predicted_margin"] = model.predict(all_data[feature_cols])

# 4. ATS evaluation
all_data["home_covers"] = all_data["actual_margin"] > all_data["spread_line"]
all_data["model_picks_home"] = all_data["predicted_margin"] > all_data["spread_line"]
all_data["correct"] = all_data["home_covers"] == all_data["model_picks_home"]
ats_accuracy = all_data["correct"].mean()
```

### Pattern 2: Vig-Adjusted Profit Accounting
**What:** Track profit/loss assuming -110 standard vig on every bet
**When to use:** BACK-01 profit analysis
**Example:**
```python
# Standard -110 vig: risk 110 to win 100
# Win: profit = +100/110 = +0.909 units
# Loss: profit = -1.0 units
# Push: profit = 0.0 units (money returned)
VIG_WIN = 100.0 / 110.0  # 0.9091
VIG_LOSS = -1.0

def compute_profit(correct_series: pd.Series, push_series: pd.Series) -> dict:
    wins = correct_series.sum() - push_series.sum()  # exclude pushes from wins
    losses = (~correct_series).sum() - push_series.sum()  # exclude pushes from losses
    pushes = push_series.sum()
    profit = wins * VIG_WIN + losses * VIG_LOSS
    roi = profit / (wins + losses) * 100 if (wins + losses) > 0 else 0.0
    return {"wins": wins, "losses": losses, "pushes": pushes, "profit": profit, "roi": roi}
```

### Pattern 3: Sealed Holdout Evaluation
**What:** Load the model trained on 2016-2023, predict on 2024, compute ATS
**When to use:** BACK-02 final validation
**Example:**
```python
# Model was trained by train_final_model() which uses season < HOLDOUT_SEASON
# Load that model and predict ONLY on 2024 data
holdout_data = all_data[all_data["season"] == HOLDOUT_SEASON]
holdout_data["predicted_margin"] = model.predict(holdout_data[feature_cols])
# Compute ATS on holdout
```

### Pattern 4: Per-Season Stability Analysis
**What:** Break ATS accuracy by season to detect degradation or variance
**When to use:** BACK-03 stability check
**Example:**
```python
stability = all_data.groupby("season").apply(
    lambda g: pd.Series({
        "games": len(g),
        "ats_accuracy": (g["correct"]).mean(),
        "profit": compute_profit(g["correct"], g["push"])["profit"],
    })
)
```

### Anti-Patterns to Avoid
- **Using spread_line as a feature:** spread_line is in LABEL_COLUMNS for a reason. Vegas lines as inputs produce zero edge by definition (the line IS the market's best estimate).
- **Including 2024 in any training data:** The model loaded from disk was trained on < 2024. Never retrain for holdout evaluation.
- **Comparing raw accuracy (win %) instead of ATS accuracy:** Raw win prediction is trivial (home teams win ~57%). ATS accuracy is the only meaningful metric.
- **Forgetting pushes:** When actual_margin == spread_line exactly, it's a push (no win/no loss). Must handle separately in profit accounting.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature assembly | Custom data loading | `assemble_multiyear_features()` from feature_engineering.py | Already handles 8 Silver sources, differentials, labels |
| Model loading | Custom deserialization | `load_model()` from model_training.py | Handles JSON model + metadata sidecar |
| Walk-forward CV details | Custom fold tracking | `walk_forward_cv()` fold_details | Already returns per-fold train_seasons, val_season, train_size, mae |

## Common Pitfalls

### Pitfall 1: Wrong Spread Convention
**What goes wrong:** Assuming spread_line follows standard betting convention (negative = favorite)
**Why it happens:** nflverse uses OPPOSITE convention from sportsbooks
**How to avoid:** nflverse spread_line: **positive = home team favored**. Home covers when `actual_margin > spread_line`. This is VERIFIED from nflverse data dictionary.
**Warning signs:** ATS accuracy near 50% is expected and correct; accuracy near 0% or 100% means the sign is flipped.

### Pitfall 2: Data Leakage in Holdout
**What goes wrong:** Accidentally retraining on data that includes 2024
**Why it happens:** Calling train_final_model() or walk_forward_cv() with 2024 data included
**How to avoid:** ONLY use load_model() to get the pre-trained model. Never retrain for holdout evaluation.
**Warning signs:** Holdout ATS accuracy suspiciously higher than validation seasons.

### Pitfall 3: Overstating Edge
**What goes wrong:** Reporting 55%+ ATS accuracy without suspecting leakage
**Why it happens:** Feature leakage, look-ahead bias, or insufficient sample size
**How to avoid:** Per STATE.md: "Realistic ATS accuracy: 52-55%; above 58% should trigger leakage investigation." A season has only 272 games, so confidence intervals are wide (~3-4% at 95% CI).
**Warning signs:** Any season above 58% ATS accuracy.

### Pitfall 4: Ignoring the Vig
**What goes wrong:** Reporting 53% accuracy as "profitable" without accounting for -110 vig
**Why it happens:** Break-even at -110 is 52.38%, not 50%
**How to avoid:** Always compute vig-adjusted profit. 52.38% is break-even. Only above that is genuinely profitable.
**Warning signs:** Claiming profitability at 51-52% accuracy.

### Pitfall 5: Push Handling
**What goes wrong:** Counting pushes as wins or losses, distorting ATS accuracy
**Why it happens:** Spread lines can land exactly on the margin (especially at common numbers like 3, 7)
**How to avoid:** Track pushes separately. ATS accuracy = correct / (correct + incorrect), excluding pushes. Pushes return the stake (0 profit).
**Warning signs:** Flat bets showing unexpected profit/loss that doesn't match accuracy.

## Code Examples

### ATS Evaluation Function
```python
# Source: Project-specific implementation based on nflverse conventions
def evaluate_ats(df: pd.DataFrame) -> pd.DataFrame:
    """Add ATS columns to game DataFrame.

    Expects columns: actual_margin, spread_line, predicted_margin.
    """
    df = df.copy()
    # Push when margin equals spread exactly
    df["push"] = df["actual_margin"] == df["spread_line"]
    # Home covers when actual margin exceeds spread (positive spread = home favored)
    df["home_covers"] = df["actual_margin"] > df["spread_line"]
    # Model picks home to cover when predicted margin exceeds spread
    df["model_picks_home"] = df["predicted_margin"] > df["spread_line"]
    # Correct prediction (excluding pushes)
    df["ats_correct"] = (~df["push"]) & (df["home_covers"] == df["model_picks_home"])
    return df
```

### Over/Under Evaluation
```python
def evaluate_ou(df: pd.DataFrame) -> pd.DataFrame:
    """Add O/U columns to game DataFrame.

    Expects columns: actual_total, total_line, predicted_total.
    """
    df = df.copy()
    df["push_ou"] = df["actual_total"] == df["total_line"]
    df["actual_over"] = df["actual_total"] > df["total_line"]
    df["model_picks_over"] = df["predicted_total"] > df["total_line"]
    df["ou_correct"] = (~df["push_ou"]) & (df["actual_over"] == df["model_picks_over"])
    return df
```

### CLI Report Pattern (follow backtest_projections.py style)
```python
def print_ats_report(results: pd.DataFrame, label: str = "Overall"):
    non_push = results[~results["push"]]
    accuracy = non_push["ats_correct"].mean()
    n_games = len(non_push)
    wins = non_push["ats_correct"].sum()
    losses = n_games - wins
    profit = wins * (100 / 110) - losses * 1.0
    roi = profit / n_games * 100

    print(f"\n{'=' * 60}")
    print(f"ATS RESULTS -- {label}")
    print(f"{'=' * 60}")
    print(f"  Record:     {wins}-{losses}-{results['push'].sum()} (W-L-P)")
    print(f"  ATS Accuracy: {accuracy:.1%}")
    print(f"  Break-even:   52.38% (-110 vig)")
    print(f"  Profit:       {profit:+.2f} units (flat $100 bets)")
    print(f"  ROI:          {roi:+.2f}%")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw win/loss prediction | ATS (against the spread) | Always standard | Spread prediction is what matters for edge detection |
| Simple accuracy % | Vig-adjusted profit + ROI | Industry standard | 53% sounds good but may still lose money with wrong vig |
| Single-season eval | Walk-forward + holdout | Phase 25 | Prevents temporal leakage, tests stability |

## Data Availability (Verified)

| Season | REG Games | spread_line Nulls | total_line Nulls |
|--------|-----------|-------------------|------------------|
| 2016 | 256 | 0 | 0 |
| 2017 | 256 | 0 | 0 |
| 2018 | 256 | 0 | 0 |
| 2019 | 256 | 0 | 0 |
| 2020 | 256 | 0 | 0 |
| 2021 | 272 | 0 | 0 |
| 2022 | 271 | 0 | 0 |
| 2023 | 272 | 0 | 0 |
| 2024 | 272 | 0 | 0 |
| **Total** | **2,367** | **0** | **0** |

**Key data facts:**
- `spread_line`: Positive = home favored (nflverse convention, OPPOSITE of sportsbook convention)
- `result` / `actual_margin` = home_score - away_score
- Home covers ATS when `actual_margin > spread_line`
- Over hits when `actual_total > total_line`
- 2021+ has 17-game regular season (272 games vs 256 prior)

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | tests/ directory, no pytest.ini (uses defaults) |
| Quick run command | `python -m pytest tests/test_prediction_backtester.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACK-01 | ATS accuracy + vig-adjusted profit computed correctly | unit | `python -m pytest tests/test_prediction_backtester.py::TestATSEvaluation -x` | Wave 0 |
| BACK-01 | Profit accounting with -110 vig matches manual calculation | unit | `python -m pytest tests/test_prediction_backtester.py::TestProfitAccounting -x` | Wave 0 |
| BACK-02 | Holdout evaluation uses model that never saw 2024 | unit | `python -m pytest tests/test_prediction_backtester.py::TestHoldoutValidation -x` | Wave 0 |
| BACK-03 | Per-season breakdown computed with stability metrics | unit | `python -m pytest tests/test_prediction_backtester.py::TestStabilityAnalysis -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_prediction_backtester.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
- [ ] `tests/test_prediction_backtester.py` -- covers BACK-01, BACK-02, BACK-03
- No framework install needed (pytest already present, 382 tests collected)

## Open Questions

1. **Is spread_line the closing line or opening line?**
   - What we know: nflverse documentation says "spread_line" without specifying opening vs closing. STATE.md flags this: "Verify spread_line in schedules is closing line (not opening) before backtesting."
   - What's unclear: Official nflverse docs don't explicitly say "closing." However, industry convention for schedule-level data is closing lines (the line at kickoff).
   - Recommendation: Treat as closing line (industry standard for schedule data). Note this assumption in backtest output. If we had opening lines, we'd see more integer values; the prevalence of half-point lines suggests closing.

2. **Should we evaluate the total (O/U) model too?**
   - What we know: Phase 25 trained both spread and total models. BACK-01 mentions "ATS accuracy" specifically.
   - What's unclear: Whether O/U evaluation is in scope for BACK-01 or deferred.
   - Recommendation: Include O/U evaluation alongside ATS. Same data, same pattern, minimal extra code. Report both in the CLI output.

## Sources

### Primary (HIGH confidence)
- nflverse data dictionary for schedules: spread_line convention verified (positive = home favored)
- Local Bronze schedules data: 2,367 games with 0% null spread/total lines verified
- `src/model_training.py`, `src/feature_engineering.py`, `src/config.py`: model training and data pipeline verified from source code
- `scripts/backtest_projections.py`: existing CLI pattern verified from source code

### Secondary (MEDIUM confidence)
- [nflverse schedules data dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html) - spread_line definition

### Tertiary (LOW confidence)
- Spread_line as "closing line" assumption: industry convention, not explicitly documented by nflverse

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all existing
- Architecture: HIGH - follows established project patterns (backtest_projections.py, model_training.py)
- Pitfalls: HIGH - spread convention verified with data + docs, vig math is standard
- Data availability: HIGH - verified all 2,367 games have complete Vegas lines

**Research date:** 2026-03-21
**Valid until:** Indefinite (historical data, stable conventions)
