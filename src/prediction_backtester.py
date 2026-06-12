"""Backtest evaluation for NFL game prediction models against historical Vegas lines.

Provides ATS (against the spread) evaluation, over/under evaluation, and
vig-adjusted profit accounting at standard -110 odds.

TRUE CLV vs MODEL-VS-CLOSE NOTE
================================
``evaluate_clv`` computes *model-vs-close*: how far the model's predicted margin
differed from the closing spread.  This is NOT true Closing Line Value — it
measures model signal relative to closing prices, which is useful as a
directional indicator but cannot capture whether our pick beat the number we
actually got.

``evaluate_line_capture`` is true CLV: given the spread/total at the time we
made the pick (open_line) and the final closing line, it measures how many
points the number moved in our favour by kickoff.  This is the primary spread
metric once 2026 live-capture data flows from the odds-capture cron.

See also: ``src/odds_snapshot_loader.py`` for deriving open_line/close_line
from Bronze Parquet snapshots written by ``scripts/bronze_odds_api_ingestion.py``.

Success gate (ELITE 2.4): mean signed capture > +0.3 pts on n ≥ 100 picks by
2026 week 10.  Kill criterion: capture ≤ 0 at n ≥ 150 → declare no betting edge.

Exports:
    evaluate_ats: Add ATS classification columns to a game DataFrame.
    evaluate_ou: Add over/under classification columns to a game DataFrame.
    evaluate_clv: Model-vs-close pseudo-CLV (NOT true CLV — see above).
    evaluate_line_capture: True CLV — signed line movement in our favour.
    compute_line_capture_summary: Summary stats for line capture results.
    compute_profit: Compute vig-adjusted profit from backtest results.
    VIG_WIN: Profit per winning bet at -110 odds (+0.9091 units).
    VIG_LOSS: Loss per losing bet at -110 odds (-1.0 units).
    BREAK_EVEN_PCT: Win percentage needed to break even at -110 (52.38%).
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config import HOLDOUT_SEASON

# Leakage detection threshold — above 58% ATS accuracy triggers investigation
LEAKAGE_THRESHOLD = 0.58

# Standard -110 vig constants
VIG_WIN = 100.0 / 110.0  # +0.9091 units per win at -110
VIG_LOSS = -1.0  # -1.0 units per loss at -110
BREAK_EVEN_PCT = 110.0 / (100.0 + 110.0)  # 52.38%


def evaluate_ats(df: pd.DataFrame) -> pd.DataFrame:
    """Add ATS (against the spread) classification columns.

    Uses nflverse convention: positive spread_line = home team favored.
    Home covers when actual_margin > spread_line.

    Args:
        df: DataFrame with columns actual_margin, spread_line, predicted_margin.

    Returns:
        Copy of df with added columns: push, home_covers, model_picks_home,
        ats_correct.
    """
    df = df.copy()
    df["push"] = df["actual_margin"] == df["spread_line"]
    df["home_covers"] = df["actual_margin"] > df["spread_line"]
    df["model_picks_home"] = df["predicted_margin"] > df["spread_line"]
    df["ats_correct"] = (~df["push"]) & (df["home_covers"] == df["model_picks_home"])
    return df


def evaluate_ou(df: pd.DataFrame) -> pd.DataFrame:
    """Add over/under classification columns.

    Over hits when actual_total > total_line.

    Args:
        df: DataFrame with columns actual_total, total_line, predicted_total.

    Returns:
        Copy of df with added columns: push_ou, actual_over, model_picks_over,
        ou_correct.
    """
    df = df.copy()
    df["push_ou"] = df["actual_total"] == df["total_line"]
    df["actual_over"] = df["actual_total"] > df["total_line"]
    df["model_picks_over"] = df["predicted_total"] > df["total_line"]
    df["ou_correct"] = (~df["push_ou"]) & (df["actual_over"] == df["model_picks_over"])
    return df


def evaluate_clv(df: pd.DataFrame) -> pd.DataFrame:
    """Add model-vs-close pseudo-CLV column.

    WARNING: This is NOT true Closing Line Value (CLV).  It computes
    ``predicted_margin - spread_line`` — i.e., how far the model's prediction
    deviated from the Vegas *closing* line.  Positive values indicate the model
    predicted a bigger home margin than the market implied at close.

    This function is useful as a directional model-signal indicator, but it
    cannot tell you whether a pick made at the *opening* line was captured at a
    better number than the close.  Use ``evaluate_line_capture`` for true CLV
    once 2026 odds-capture data is available.

    Args:
        df: DataFrame with columns predicted_margin, spread_line.

    Returns:
        Copy of df with added column: clv (predicted_margin - spread_line).
    """
    df = df.copy()
    df["clv"] = df["predicted_margin"] - df["spread_line"]
    return df


def evaluate_line_capture(
    df: pd.DataFrame,
    open_col: str = "open_line",
    close_col: str = "close_line",
    pick_side_col: str = "pick_side",
    market: str = "spread",
) -> pd.DataFrame:
    """Compute true line-capture (CLV) for each pick.

    For each game where a pick was made against the open-proxy line, measures
    how many points the number moved in our favour by the time the closing line
    was set.  Positive capture means we got a better number than the close —
    the defining signal of a sharp bettor.

    Sign conventions
    ----------------
    Spread market (``market="spread"``)
        ``open_line`` and ``close_line`` are *home-relative* spread values using
        the **SPORTSBOOK sign convention**: negative = home favoured (e.g.,
        -3.5 means home is a 3.5-point favourite). This matches the raw
        ``home_spread`` stored by ``bronze_odds_api_ingestion.py`` and served
        by ``odds_snapshot_loader``. WARNING: it is the OPPOSITE of nflverse
        ``spread_line`` (expected home margin, positive = home favoured) —
        convert nflverse lines with ``-spread_line`` before passing them here.

        ``pick_side`` must be either ``"home"`` or ``"away"``.

        Capture is defined as: the number of points the line moved away from the
        picked side from open to close.

        - Home pick: home spread improved (moved more negative, i.e. home became
          more favoured) → positive capture.
          ``capture = open_line - close_line``
        - Away pick: away spread improved (home line moved less negative / more
          positive, making the away side a bigger underdog from the line's
          perspective) → positive capture.
          ``capture = close_line - open_line``

    Totals market (``market="total"``)
        ``open_line`` and ``close_line`` are the over/under totals.

        ``pick_side`` must be either ``"over"`` or ``"under"``.

        - Over pick: total moved up (more points needed to hit over) → positive
          capture.  ``capture = open_line - close_line``
        - Under pick: total moved down (fewer total points expected) → positive
          capture.  ``capture = close_line - open_line``

    Handling missing data
    ---------------------
    Rows where ``open_col`` or ``close_col`` are NaN receive NaN capture and are
    excluded from summary statistics.  This handles the pre-season period before
    2026 capture data flows.

    Args:
        df: DataFrame with at minimum the three columns named by ``open_col``,
            ``close_col``, and ``pick_side_col``.  All other columns are
            preserved unchanged.
        open_col: Column name for the open-proxy line value.
        close_col: Column name for the closing-line value.
        pick_side_col: Column name for the side picked ("home"/"away" or
            "over"/"under").
        market: ``"spread"`` or ``"total"``.  Determines which pick-side labels
            are valid and which direction constitutes positive capture.

    Returns:
        Copy of ``df`` with three added columns:

        - ``line_capture``: signed capture in points (positive = we beat the
          close, negative = close beat us, NaN = missing open/close).
        - ``captured``: boolean; True when ``line_capture > 0``.
        - ``line_move``: raw line movement ``close_line - open_line``
          (informational; sign follows home-relative or total convention).

    Raises:
        ValueError: If ``market`` is not ``"spread"`` or ``"total"``.
        ValueError: If ``pick_side_col`` contains values other than the expected
            pair for the given market.

    Examples:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     "game_id": ["2026_01_KC_BUF"],
        ...     "open_line": [-3.5],
        ...     "close_line": [-5.0],
        ...     "pick_side": ["home"],
        ... })
        >>> result = evaluate_line_capture(df)
        >>> float(result["line_capture"].iloc[0])
        1.5
    """
    if market not in ("spread", "total"):
        raise ValueError(f"market must be 'spread' or 'total', got {market!r}")

    valid_sides: dict = {
        "spread": {"home", "away"},
        "total": {"over", "under"},
    }
    expected_sides = valid_sides[market]

    df = df.copy()

    # Normalise pick_side to lower-case before validation and computation.
    # This allows callers to pass "Home", "AWAY", "Over", etc.
    if not df.empty and pick_side_col in df.columns:
        df[pick_side_col] = df[pick_side_col].str.lower()

    # Validate pick_side values (ignore NaN rows — they'll produce NaN capture)
    present_sides = set(df[pick_side_col].dropna().unique())
    bad_sides = present_sides - expected_sides
    if bad_sides:
        raise ValueError(
            f"pick_side column contains unexpected values for market={market!r}: "
            f"{sorted(bad_sides)}.  Expected values from {sorted(expected_sides)}."
        )

    open_vals = pd.to_numeric(df[open_col], errors="coerce")
    close_vals = pd.to_numeric(df[close_col], errors="coerce")

    # Raw line movement (home-relative or total-relative).
    # Positive = line moved in favour of home (home became bigger favourite)
    #           OR total increased.
    line_move = close_vals - open_vals

    if market == "spread":
        # Home pick: want line to move MORE negative (home more favoured).
        # open - close > 0 when home spread got better for home bettors.
        home_capture = open_vals - close_vals
        away_capture = close_vals - open_vals

        is_home = df[pick_side_col] == "home"  # already lower-cased above
        capture = np.where(is_home, home_capture, away_capture)
        capture = pd.Series(capture, index=df.index, dtype=float)

    else:  # total
        # Over pick: want total to move UP (harder to hit → better open price).
        # open - close > 0 when total increased (over is more valuable at open).
        over_capture = open_vals - close_vals
        under_capture = close_vals - open_vals

        is_over = df[pick_side_col] == "over"  # already lower-cased above
        capture = np.where(is_over, over_capture, under_capture)
        capture = pd.Series(capture, index=df.index, dtype=float)

    # Force NaN where either line is missing — cannot compute capture.
    missing_mask = open_vals.isna() | close_vals.isna()
    capture[missing_mask] = np.nan

    df["line_capture"] = capture
    df["captured"] = capture > 0
    df["line_move"] = line_move

    return df


def compute_line_capture_summary(
    df: pd.DataFrame,
    capture_col: str = "line_capture",
    edge_col: Optional[str] = None,
) -> dict:
    """Compute summary statistics for line-capture (true CLV) results.

    Args:
        df: DataFrame with ``line_capture`` column from ``evaluate_line_capture``.
            Rows with NaN capture are automatically excluded.
        capture_col: Column name for signed line-capture values.
        edge_col: Optional column name for model edge magnitude used to split
            results by tier (high/medium/low).  When provided the summary
            includes a ``by_tier`` key.

    Returns:
        Dict with keys:

        - ``n``: number of picks with valid capture data.
        - ``mean_capture``: mean signed capture across all picks.
        - ``median_capture``: median signed capture.
        - ``pct_captured``: fraction of picks where capture > 0.
        - ``std_capture``: standard deviation of capture.
        - ``by_tier``: (only when ``edge_col`` provided) list of dicts, each
          with keys ``tier``, ``n``, ``mean_capture``, ``pct_captured``.
          Tiers use the same thresholds as ``compute_clv_by_tier``:
          high ≥ 3.0, medium ≥ 1.5, low < 1.5.
    """
    valid = df[df[capture_col].notna()].copy()
    n = len(valid)

    if n == 0:
        summary: dict = {
            "n": 0,
            "mean_capture": float("nan"),
            "median_capture": float("nan"),
            "pct_captured": float("nan"),
            "std_capture": float("nan"),
        }
        if edge_col is not None:
            summary["by_tier"] = []
        return summary

    captures = valid[capture_col].astype(float)
    summary = {
        "n": n,
        "mean_capture": float(captures.mean()),
        "median_capture": float(captures.median()),
        "pct_captured": float((captures > 0).mean()),
        "std_capture": float(captures.std()),
    }

    if edge_col is not None and edge_col in valid.columns:
        edge_vals = valid[edge_col].abs()
        tier_labels = pd.cut(
            edge_vals,
            bins=[-float("inf"), 1.5, 3.0, float("inf")],
            labels=["low", "medium", "high"],
        )
        tier_rows: List[dict] = []
        for tier_label, group in valid.groupby(tier_labels, observed=True):
            grp_cap = group[capture_col].astype(float)
            tier_rows.append({
                "tier": str(tier_label),
                "n": len(group),
                "mean_capture": float(grp_cap.mean()),
                "pct_captured": float((grp_cap > 0).mean()),
            })
        summary["by_tier"] = tier_rows

    return summary


def compute_clv_by_tier(df: pd.DataFrame) -> pd.DataFrame:
    """Compute CLV metrics grouped by confidence tier.

    Tiers based on absolute edge (|predicted_margin - spread_line|):
        high: >= 3.0
        medium: >= 1.5
        low: < 1.5

    Args:
        df: DataFrame with columns predicted_margin, spread_line, clv.

    Returns:
        DataFrame with columns: tier, games, mean_clv, median_clv, pct_beating_close.
    """
    edge = (df["predicted_margin"] - df["spread_line"]).abs()
    tier = pd.cut(
        edge,
        bins=[-float("inf"), 1.5, 3.0, float("inf")],
        labels=["low", "medium", "high"],
    )
    rows = []
    for tier_label, group in df.groupby(tier, observed=True):
        rows.append({
            "tier": tier_label,
            "games": len(group),
            "mean_clv": float(group["clv"].mean()),
            "median_clv": float(group["clv"].median()),
            "pct_beating_close": float((group["clv"] > 0).mean()),
        })
    return pd.DataFrame(rows)


def compute_clv_by_season(df: pd.DataFrame) -> pd.DataFrame:
    """Compute CLV metrics grouped by season.

    Args:
        df: DataFrame with columns season, clv.

    Returns:
        DataFrame with columns: season, games, mean_clv, median_clv, pct_beating_close.
    """
    rows = []
    for season, group in df.groupby("season"):
        rows.append({
            "season": int(season),
            "games": len(group),
            "mean_clv": float(group["clv"].mean()),
            "median_clv": float(group["clv"].median()),
            "pct_beating_close": float((group["clv"] > 0).mean()),
        })
    return pd.DataFrame(rows)


def compute_profit(
    results_df: pd.DataFrame,
    correct_col: str = "ats_correct",
    push_col: str = "push",
) -> dict:
    """Compute vig-adjusted profit from backtest results.

    Assumes flat $100 bets at -110 odds. Pushes return the stake (no win/loss).

    Args:
        results_df: DataFrame with boolean columns for correct picks and pushes.
        correct_col: Column name for correct pick boolean.
        push_col: Column name for push boolean.

    Returns:
        Dict with keys: wins, losses, pushes, profit, roi, games_bet.
    """
    non_push = results_df[~results_df[push_col]]
    wins = int(non_push[correct_col].sum())
    losses = int(len(non_push) - wins)
    pushes = int(results_df[push_col].sum())
    games_bet = wins + losses
    profit = wins * VIG_WIN + losses * VIG_LOSS
    roi = (profit / games_bet * 100) if games_bet > 0 else 0.0
    return {
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "profit": profit,
        "roi": roi,
        "games_bet": games_bet,
    }


def evaluate_holdout(
    results_df: pd.DataFrame,
    metadata: dict,
    holdout_season: int = HOLDOUT_SEASON,
) -> dict:
    """Evaluate model on sealed holdout season.

    Args:
        results_df: DataFrame with ats_correct, push, season columns (from evaluate_ats).
        metadata: Model metadata dict (from load_model). Must contain training_seasons.
        holdout_season: Season to evaluate (default: 2024).

    Returns:
        Dict with ats_accuracy, profit_stats, n_games, season.

    Raises:
        ValueError: If holdout_season appears in metadata['training_seasons'].
    """
    if holdout_season in metadata.get("training_seasons", []):
        raise ValueError(
            f"Holdout season {holdout_season} found in training_seasons. "
            "Model has data leakage -- cannot evaluate holdout."
        )
    holdout = results_df[results_df["season"] == holdout_season].copy()
    if holdout.empty:
        return {"ats_accuracy": 0.0, "profit_stats": {}, "n_games": 0, "season": holdout_season}

    non_push = holdout[~holdout["push"]]
    accuracy = non_push["ats_correct"].mean() if len(non_push) > 0 else 0.0
    profit_stats = compute_profit(holdout)
    return {
        "ats_accuracy": float(accuracy),
        "profit_stats": profit_stats,
        "n_games": len(holdout),
        "season": holdout_season,
    }


def compute_season_stability(
    results_df: pd.DataFrame,
    correct_col: str = "ats_correct",
    push_col: str = "push",
) -> tuple:
    """Compute per-season ATS breakdown and stability metrics.

    Args:
        results_df: DataFrame with season, ats_correct, push columns.
        correct_col: Column name for correct predictions.
        push_col: Column name for push flag.

    Returns:
        Tuple of (per_season_df, stability_summary).
        per_season_df: DataFrame with season, games, ats_accuracy, profit, roi.
        stability_summary: Dict with mean_accuracy, std_accuracy, min_accuracy,
            max_accuracy, leakage_warning.
    """
    rows = []
    for season, group in results_df.groupby("season"):
        non_push = group[~group[push_col]]
        accuracy = float(non_push[correct_col].mean()) if len(non_push) > 0 else 0.0
        profit_stats = compute_profit(group, correct_col, push_col)
        rows.append({
            "season": int(season),
            "games": len(group),
            "ats_accuracy": accuracy,
            "profit": profit_stats["profit"],
            "roi": profit_stats["roi"],
        })

    per_season_df = pd.DataFrame(rows)
    accuracies = per_season_df["ats_accuracy"].values
    stability_summary = {
        "mean_accuracy": float(np.mean(accuracies)) if len(accuracies) > 0 else 0.0,
        "std_accuracy": float(np.std(accuracies)) if len(accuracies) > 1 else 0.0,
        "min_accuracy": float(np.min(accuracies)) if len(accuracies) > 0 else 0.0,
        "max_accuracy": float(np.max(accuracies)) if len(accuracies) > 0 else 0.0,
        "leakage_warning": bool(np.any(accuracies > LEAKAGE_THRESHOLD)),
    }
    return per_season_df, stability_summary


def _compute_config_metrics(
    results_df: pd.DataFrame,
    holdout_season: int,
) -> Dict:
    """Compute ATS/O-U/MAE/profit metrics for one config on the holdout season.

    Args:
        results_df: DataFrame with ATS+O/U evaluation columns and season.
        holdout_season: Season to filter to.

    Returns:
        Dict with ats_accuracy, ou_accuracy, mae, profit, roi, n_games.
    """
    holdout = results_df[results_df["season"] == holdout_season].copy()
    n_games = len(holdout)
    if n_games == 0:
        return {
            "ats_accuracy": 0.0,
            "ou_accuracy": 0.0,
            "mae": 0.0,
            "profit": 0.0,
            "roi": 0.0,
            "n_games": 0,
        }

    # ATS accuracy
    non_push_ats = holdout[~holdout["push"]]
    ats_acc = float(non_push_ats["ats_correct"].mean()) if len(non_push_ats) > 0 else 0.0

    # O/U accuracy (if columns present)
    ou_acc = 0.0
    if "ou_correct" in holdout.columns and "push_ou" in holdout.columns:
        non_push_ou = holdout[~holdout["push_ou"]]
        ou_acc = float(non_push_ou["ou_correct"].mean()) if len(non_push_ou) > 0 else 0.0

    # MAE on spread
    mae = float(np.mean(np.abs(
        holdout["predicted_margin"].values - holdout["actual_margin"].values
    )))

    # Profit
    profit_stats = compute_profit(holdout, correct_col="ats_correct", push_col="push")

    return {
        "ats_accuracy": ats_acc,
        "ou_accuracy": ou_acc,
        "mae": mae,
        "profit": profit_stats["profit"],
        "roi": profit_stats["roi"],
        "n_games": n_games,
    }


def print_holdout_comparison(
    xgb_results: pd.DataFrame,
    ens_results: pd.DataFrame,
    full_results: pd.DataFrame,
    holdout_season: int = HOLDOUT_SEASON,
) -> Dict[str, Dict]:
    """Print three-way comparison table for sealed holdout season.

    Compares v1.4 XGBoost, Phase-30 Ensemble, and Phase-31 Full ensemble
    on the sealed holdout season. Prints a formatted table and returns
    metrics for programmatic access.

    Args:
        xgb_results: v1.4 single XGBoost results (with ATS+O/U eval columns).
        ens_results: Phase-30 ensemble results (with ATS+O/U eval columns).
        full_results: Phase-31 full ensemble results (with ATS+O/U eval columns).
        holdout_season: Season to evaluate (default: HOLDOUT_SEASON).

    Returns:
        Dict keyed by config name with metric dicts for each configuration.
    """
    configs = {
        "v1.4 XGB": xgb_results,
        "P30 Ensemble": ens_results,
        "P31 Full": full_results,
    }

    all_metrics: Dict[str, Dict] = {}
    for name, df in configs.items():
        all_metrics[name] = _compute_config_metrics(df, holdout_season)

    # Print header
    print(f"\n{'=' * 72}")
    print(f"SEALED HOLDOUT -- {holdout_season} Season")
    print(f"{'=' * 72}")

    # Column headers
    col_names = list(configs.keys())
    header = f"  {'Metric':<16}"
    for name in col_names:
        header += f" {name:>14}"
    print(header)
    print(f"  {'-' * 60}")

    # ATS Accuracy row
    row = f"  {'ATS Accuracy':<16}"
    for name in col_names:
        row += f" {all_metrics[name]['ats_accuracy']:>13.1%}"
    print(row)

    # O/U Accuracy row
    row = f"  {'O/U Accuracy':<16}"
    for name in col_names:
        row += f" {all_metrics[name]['ou_accuracy']:>13.1%}"
    print(row)

    # MAE row
    row = f"  {'MAE (spread)':<16}"
    for name in col_names:
        row += f" {all_metrics[name]['mae']:>13.2f}"
    print(row)

    # Profit row
    row = f"  {'Profit (units)':<16}"
    for name in col_names:
        row += f" {all_metrics[name]['profit']:>+13.2f}"
    print(row)

    # ROI row
    row = f"  {'ROI':<16}"
    for name in col_names:
        row += f" {all_metrics[name]['roi']:>+12.1f}%"
    print(row)

    # Games row
    row = f"  {'Games':<16}"
    for name in col_names:
        row += f" {all_metrics[name]['n_games']:>13d}"
    print(row)

    print(f"  {'-' * 60}")

    # Best indicator (by ATS accuracy)
    best_name = max(col_names, key=lambda n: all_metrics[n]["ats_accuracy"])
    print(f"  Best ATS: {best_name} ({all_metrics[best_name]['ats_accuracy']:.1%})")

    print(f"{'=' * 72}")

    return all_metrics
