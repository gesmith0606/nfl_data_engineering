"""Backtest evaluation for NFL game prediction models against historical Vegas lines.

Provides ATS (against the spread) evaluation, over/under evaluation, and
vig-adjusted profit accounting at standard -110 odds.

Exports:
    evaluate_ats: Add ATS classification columns to a game DataFrame.
    evaluate_ou: Add over/under classification columns to a game DataFrame.
    compute_profit: Compute vig-adjusted profit from backtest results.
    VIG_WIN: Profit per winning bet at -110 odds (+0.9091 units).
    VIG_LOSS: Loss per losing bet at -110 odds (-1.0 units).
    BREAK_EVEN_PCT: Win percentage needed to break even at -110 (52.38%).
"""

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
