"""
diagnose_totals_edge.py — Phase 1.2 of ELITE_MODELS_PLAN.md

One-shot diagnostic answering three pre-specified questions about the game totals model:

1. Signal beyond the line: OLS actual_total ~ total_line + meta_oof_pred.
   Reports coefficients, t-stats, partial correlation of meta_oof_pred
   controlling for total_line, and overall OOF O/U accuracy.

2. Residual edges: tests five pre-specified subgroups on resid = actual - total_line.
   Reports n, mean_resid, std, t-stat vs 0, and naive "always under" hit rate.
   Multiple-testing threshold: |t| > 2.5 required to call a finding real.

3. Verdict: KILL or FIX based on plan gates (|t| > 2.5 AND implied O/U ≥ 52.5% on n ≥ 100).

Output: prints results to stdout and writes .planning/TOTALS_VERDICT.md.

Usage:
    source venv/bin/activate
    python scripts/diagnose_totals_edge.py
"""

import glob
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
OOF_PATH = REPO_ROOT / "models" / "ensemble" / "oof_total.parquet"
SCHED_GLOB = str(REPO_ROOT / "data" / "bronze" / "schedules" / "season=*" / "*.parquet")
CTX_GLOB = str(REPO_ROOT / "data" / "silver" / "teams" / "game_context" / "season=*" / "*.parquet")
TEND_GLOB = str(REPO_ROOT / "data" / "silver" / "teams" / "tendencies" / "season=*" / "*.parquet")
VERDICT_PATH = REPO_ROOT / ".planning" / "TOTALS_VERDICT.md"

# Multiple-testing threshold (5 pre-specified tests → require |t| > 2.5)
T_THRESHOLD = 2.5
# Gate: O/U accuracy ≥ 52.5% AND n ≥ 100 for "fix" verdict
MIN_OU_ACC = 0.525
MIN_N_SUBGROUP = 100

OOF_SEASONS = [2019, 2020, 2021, 2022, 2023, 2024]


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_latest_per_partition(pattern: str) -> pd.DataFrame:
    """Load the most recent parquet file per season partition, concatenated."""
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No files matched: {pattern}")
    # Group by parent directory (the season partition) and take the latest file
    by_dir: dict[str, list[str]] = {}
    for f in files:
        d = os.path.dirname(f)
        by_dir.setdefault(d, []).append(f)
    frames = []
    for d, flist in by_dir.items():
        latest = max(flist)  # ISO timestamps sort correctly
        frames.append(pd.read_parquet(latest))
    return pd.concat(frames, ignore_index=True)


def load_data() -> pd.DataFrame:
    """
    Build the analysis DataFrame by joining OOF predictions with schedules
    (total_line, wind, temp, roof) and silver context (is_dome, wind_speed,
    temperature) and tendencies (pace_roll3 for home/away teams).

    Returns
    -------
    pd.DataFrame
        One row per OOF game with all features needed for the three questions.
    """
    # --- OOF predictions ---
    oof = pd.read_parquet(OOF_PATH)
    assert set(["game_id", "season", "actual", "meta_oof_pred"]).issubset(oof.columns), (
        "OOF parquet missing expected columns"
    )
    oof = oof[oof["season"].isin(OOF_SEASONS)].copy()

    # --- Bronze schedules: total_line, wind, temp, roof ---
    sched = _load_latest_per_partition(SCHED_GLOB)
    sched_sub = sched[sched["season"].isin(OOF_SEASONS)][
        ["game_id", "season", "week", "home_team", "away_team", "total_line", "wind", "temp", "roof"]
    ].copy()
    # Keep only regular season games that appear in OOF
    sched_sub = sched_sub[sched_sub["game_id"].isin(oof["game_id"])]

    # --- Silver game_context: is_dome, wind_speed, temperature (deduplicated per game) ---
    ctx = _load_latest_per_partition(CTX_GLOB)
    ctx_deduped = (
        ctx[ctx["season"].isin(OOF_SEASONS)]
        .drop_duplicates(subset=["game_id"])[["game_id", "is_dome", "wind_speed", "temperature"]]
    )

    # --- Silver tendencies: pace_roll3 (LAGGED — col is trailing 3-week avg by construction) ---
    tend = _load_latest_per_partition(TEND_GLOB)
    tend_sub = tend[tend["season"].isin(OOF_SEASONS)][["team", "season", "week", "pace_roll3"]].copy()

    # Join home and away pace_roll3 via schedule
    home_pace = tend_sub.rename(columns={"team": "home_team", "pace_roll3": "home_pace_roll3"})
    away_pace = tend_sub.rename(columns={"team": "away_team", "pace_roll3": "away_pace_roll3"})
    sched_sub = sched_sub.merge(home_pace, on=["home_team", "season", "week"], how="left")
    sched_sub = sched_sub.merge(away_pace, on=["away_team", "season", "week"], how="left")

    # --- Merge everything onto OOF ---
    df = oof.merge(sched_sub.drop(columns=["season"]), on="game_id", how="left")
    df = df.merge(ctx_deduped, on="game_id", how="left")

    # Derived columns
    df["actual_total"] = df["actual"].astype(float)
    df["resid"] = df["actual_total"] - df["total_line"]
    df["over_actual"] = (df["actual_total"] > df["total_line"]).astype(int)  # 1=over, 0=under

    # Both-teams-top-quartile pace (lagged)
    pace_q75 = df[["home_pace_roll3", "away_pace_roll3"]].stack().quantile(0.75)
    df["both_high_pace"] = (df["home_pace_roll3"] >= pace_q75) & (df["away_pace_roll3"] >= pace_q75)

    # High-wind × under interaction: "high wind" = outdoor wind_speed ≥ 15 mph
    df["high_wind_outdoor"] = (~df["is_dome"]) & (df["wind_speed"] >= 15)
    # "Always under in high wind" hit rate: under means actual_total < total_line
    df["under_actual"] = (df["actual_total"] < df["total_line"]).astype(int)

    # Cold game: temperature ≤ 25F and outdoor
    df["cold_outdoor"] = (~df["is_dome"]) & (df["temperature"] <= 25)

    return df


# ---------------------------------------------------------------------------
# OLS helper (manual, no statsmodels)
# ---------------------------------------------------------------------------

def ols_2var(y: np.ndarray, x1: np.ndarray, x2: np.ndarray) -> dict:
    """
    Fit OLS y = b0 + b1*x1 + b2*x2 and return coefficients, t-stats, p-values.

    Computes HC0 (robust) standard errors to guard against heteroscedasticity.

    Parameters
    ----------
    y : np.ndarray  — dependent variable (n,)
    x1, x2 : np.ndarray — predictors (n,)

    Returns
    -------
    dict with keys: b0, b1, b2, t0, t1, t2, p0, p1, p2, r2, n
    """
    X = np.column_stack([np.ones(len(y)), x1, x2])
    n, k = X.shape
    # Closed-form OLS
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    y_hat = X @ b
    resid = y - y_hat
    # HC0 robust variance
    meat = (X * resid[:, None]).T @ (X * resid[:, None])
    V = XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.diag(V))
    t = b / se
    p = 2 * stats.t.sf(np.abs(t), df=n - k)
    ss_tot = np.sum((y - y.mean()) ** 2)
    ss_res = np.sum(resid ** 2)
    r2 = 1 - ss_res / ss_tot
    return dict(b0=b[0], b1=b[1], b2=b[2],
                t0=t[0], t1=t[1], t2=t[2],
                p0=p[0], p1=p[1], p2=p[2],
                se0=se[0], se1=se[1], se2=se[2],
                r2=r2, n=int(n))


def partial_corr(y: np.ndarray, x_focus: np.ndarray, x_control: np.ndarray) -> float:
    """
    Partial correlation of y with x_focus, controlling for x_control.

    Computes residuals of y ~ x_control and x_focus ~ x_control, then
    correlates the two residual vectors.
    """
    def _resid(a, b):
        b_c = np.column_stack([np.ones(len(b)), b])
        coef = np.linalg.lstsq(b_c, a, rcond=None)[0]
        return a - b_c @ coef

    ry = _resid(y, x_control)
    rx = _resid(x_focus, x_control)
    return float(np.corrcoef(ry, rx)[0, 1])


# ---------------------------------------------------------------------------
# Question 1: Signal beyond the line
# ---------------------------------------------------------------------------

def q1_signal_beyond_line(df: pd.DataFrame) -> dict:
    """
    OLS actual_total ~ total_line + meta_oof_pred on the full OOF set.
    Also computes overall O/U accuracy.

    Returns dict of results for printing and writing.
    """
    valid = df[["actual_total", "total_line", "meta_oof_pred", "over_actual"]].dropna()
    y = valid["actual_total"].values
    x1 = valid["total_line"].values
    x2 = valid["meta_oof_pred"].values

    ols = ols_2var(y, x1, x2)
    pc = partial_corr(y, x2, x1)
    ou_acc = valid["over_actual"].mean()
    # Overall O/U: majority vote from meta_oof_pred vs total_line
    pred_over = (valid["meta_oof_pred"] > valid["total_line"]).astype(int)
    ou_model_acc = (pred_over == valid["over_actual"]).mean()

    return {
        "n": ols["n"],
        "b0": ols["b0"], "b1": ols["b1"], "b2": ols["b2"],
        "se0": ols["se0"], "se1": ols["se1"], "se2": ols["se2"],
        "t0": ols["t0"], "t1": ols["t1"], "t2": ols["t2"],
        "p0": ols["p0"], "p1": ols["p1"], "p2": ols["p2"],
        "r2": ols["r2"],
        "partial_corr_oof": pc,
        "ou_overall_rate": float(ou_acc),  # fraction of overs in actuals
        "ou_model_accuracy": float(ou_model_acc),  # model O/U pick accuracy
    }


# ---------------------------------------------------------------------------
# Question 2: Residual subgroup analysis
# ---------------------------------------------------------------------------

def _subgroup_stats(df: pd.DataFrame, mask: pd.Series, label: str, hit_col: str = "under_actual") -> dict:
    """
    Compute subgroup stats for a boolean mask over df.

    Parameters
    ----------
    df : full DataFrame
    mask : boolean Series selecting the subgroup
    label : human-readable subgroup name
    hit_col : column for the naive directional bet hit rate
              'under_actual' for "always under" in high-wind scenarios,
              'over_actual' for e.g., hot-game fast-pace subgroup
    """
    sub = df[mask][["resid", hit_col]].dropna()
    n = len(sub)
    if n < 2:
        return {"label": label, "n": n, "mean_resid": np.nan, "std_resid": np.nan,
                "t_stat": np.nan, "p_val": np.nan, "hit_rate": np.nan, "hit_col": hit_col}
    mean_r = sub["resid"].mean()
    std_r = sub["resid"].std(ddof=1)
    se = std_r / np.sqrt(n)
    t_stat = mean_r / se
    p_val = 2 * stats.t.sf(abs(t_stat), df=n - 1)
    hit_rate = sub[hit_col].mean()
    return {
        "label": label,
        "n": n,
        "mean_resid": round(mean_r, 3),
        "std_resid": round(std_r, 3),
        "t_stat": round(t_stat, 3),
        "p_val": round(p_val, 4),
        "hit_rate": round(hit_rate, 4),
        "hit_col": hit_col,
    }


def q2_residual_edges(df: pd.DataFrame) -> list[dict]:
    """
    Five pre-specified subgroup tests on resid = actual_total - total_line.

    Subgroups:
    1. High wind (outdoor): wind_speed >= 15 mph, not dome
    2. Cold game (outdoor): temperature <= 25F, not dome
    3. Dome games: is_dome == True
    4. Both-teams-top-quartile lagged pace (pace_roll3)
    5. High-wind x under interaction (same as #1 but focus on under hit rate)
    """
    results = []

    # 1. High wind outdoor — hypothesis: under (scoring suppressed)
    #    Hit rate = "always bet under" accuracy
    mask1 = df["high_wind_outdoor"].fillna(False)
    results.append(_subgroup_stats(df, mask1, "High wind outdoor (wind_speed ≥ 15 mph)", hit_col="under_actual"))

    # 2. Cold outdoor — hypothesis: under
    mask2 = df["cold_outdoor"].fillna(False)
    results.append(_subgroup_stats(df, mask2, "Cold outdoor (temp ≤ 25F)", hit_col="under_actual"))

    # 3. Dome games — hypothesis: over (controlled environment, no suppression)
    mask3 = df["is_dome"].fillna(False)
    results.append(_subgroup_stats(df, mask3, "Dome games", hit_col="over_actual"))

    # 4. Both-teams top-quartile lagged pace — hypothesis: over
    mask4 = df["both_high_pace"].fillna(False)
    results.append(_subgroup_stats(df, mask4, "Both teams top-quartile pace_roll3", hit_col="over_actual"))

    # 5. High-wind × under interaction: within high-wind outdoor games, does under win?
    #    (same as mask1 but explicitly framed as the "interaction" test)
    #    Overlap with test 1 acknowledged — pre-specified per plan
    mask5 = df["high_wind_outdoor"].fillna(False)
    results.append(_subgroup_stats(df, mask5, "High-wind × under interaction (same-sample reframe of #1)", hit_col="under_actual"))

    return results


# ---------------------------------------------------------------------------
# Question 3: Verdict
# ---------------------------------------------------------------------------

def q3_verdict(q1: dict, q2: list[dict]) -> dict:
    """
    Apply plan gates:
    - FIX: some subgroup has |t| > 2.5 AND implied O/U accuracy ≥ 52.5% on n ≥ 100
    - KILL otherwise

    Returns dict with verdict, rationale, and passing subgroups.
    """
    passing = []
    for sg in q2:
        t = sg.get("t_stat", np.nan)
        n = sg.get("n", 0)
        hr = sg.get("hit_rate", np.nan)
        if (
            not np.isnan(t)
            and abs(t) > T_THRESHOLD
            and n >= MIN_N_SUBGROUP
            and not np.isnan(hr)
            and hr >= MIN_OU_ACC
        ):
            passing.append(sg)

    if passing:
        verdict = "FIX"
        rationale = (
            f"{len(passing)} subgroup(s) passed all gates "
            f"(|t| > {T_THRESHOLD}, n ≥ {MIN_N_SUBGROUP}, hit rate ≥ {MIN_OU_ACC:.1%})"
        )
    else:
        verdict = "KILL"
        # Detail what fell short
        near_misses = []
        for sg in q2:
            t = sg.get("t_stat", np.nan)
            n = sg.get("n", 0)
            hr = sg.get("hit_rate", np.nan)
            if not np.isnan(t) and abs(t) > 2.0:  # report near-misses for context
                near_misses.append(f"{sg['label']}: t={t:.2f}, n={n}, hit={hr:.3%}")
        rationale = (
            "No subgroup met all three gates simultaneously "
            f"(|t| > {T_THRESHOLD}, n ≥ {MIN_N_SUBGROUP}, hit ≥ {MIN_OU_ACC:.1%}). "
        )
        if near_misses:
            rationale += "Near-misses (|t| > 2.0 but did not pass all gates): " + "; ".join(near_misses)
        else:
            rationale += "No subgroup showed |t| > 2.0."

    return {"verdict": verdict, "rationale": rationale, "passing_subgroups": passing}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt_pval(p: float) -> str:
    if p < 0.001:
        return "<0.001"
    return f"{p:.4f}"


def build_report(df: pd.DataFrame, q1: dict, q2: list[dict], verdict: dict) -> str:
    """Build the full markdown report text."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    lines.append("# TOTALS_VERDICT.md — Phase 1.2 Diagnosis")
    lines.append(f"\n*Generated {ts} by `scripts/diagnose_totals_edge.py`*\n")
    lines.append("---\n")

    # -----------------------------------------------------------------------
    lines.append("## Executive Summary\n")
    verdict_str = verdict["verdict"]
    lines.append(f"**VERDICT: {verdict_str}**\n")
    lines.append(textwrap.fill(verdict["rationale"], width=90) + "\n")
    if verdict_str == "KILL":
        lines.append(
            "> Action: Remove the game-totals betting surface from production. "
            "Keep `predicted_total` as website content labeled **market tracking** "
            "(useful context; not a bet recommendation). No further totals modeling work "
            "until a new information source (e.g., The Odds API opener data per Phase 1.4) "
            "makes the hypothesis re-testable.\n"
        )
    else:
        lines.append(
            "> Action: Proceed to build a deviation model "
            "(`actual_total − total_line` target, ≤ 10 features from passing subgroups).\n"
        )

    lines.append("---\n")

    # -----------------------------------------------------------------------
    lines.append("## Q1: Signal Beyond the Line\n")
    lines.append(f"**OLS**: `actual_total ~ total_line + meta_oof_pred`  (n={q1['n']})\n")
    lines.append("| Predictor | Coef | SE | t-stat | p-value |")
    lines.append("|-----------|-----:|---:|-------:|--------:|")
    lines.append(f"| Intercept | {q1['b0']:.3f} | {q1['se0']:.3f} | {q1['t0']:.2f} | {_fmt_pval(q1['p0'])} |")
    lines.append(f"| total_line | {q1['b1']:.3f} | {q1['se1']:.3f} | {q1['t1']:.2f} | {_fmt_pval(q1['p1'])} |")
    lines.append(f"| meta_oof_pred | {q1['b2']:.3f} | {q1['se2']:.3f} | {q1['t2']:.2f} | {_fmt_pval(q1['p2'])} |")
    lines.append("")
    lines.append(f"- **R²**: {q1['r2']:.4f}")
    lines.append(f"- **Partial correlation** of `meta_oof_pred` controlling for `total_line`: {q1['partial_corr_oof']:.4f}")
    lines.append(f"- **Overall O/U (% overs in actuals)**: {q1['ou_overall_rate']:.2%}")
    lines.append(f"- **Model O/U accuracy** (meta_oof_pred > total_line → pick over): {q1['ou_model_accuracy']:.2%}")
    lines.append("")

    if abs(q1["t2"]) > T_THRESHOLD:
        lines.append(
            f"> meta_oof_pred coefficient t={q1['t2']:.2f} exceeds threshold {T_THRESHOLD}. "
            "The ML ensemble carries some independent signal beyond the closing line."
        )
    else:
        lines.append(
            f"> meta_oof_pred coefficient t={q1['t2']:.2f}, below threshold {T_THRESHOLD}. "
            "The ML ensemble carries **no statistically reliable signal beyond the closing line**."
        )

    lines.append("\n---\n")

    # -----------------------------------------------------------------------
    lines.append("## Q2: Residual Subgroup Analysis\n")
    lines.append(
        f"`resid = actual_total − total_line` (positive = over, negative = under). "
        f"Multiple-testing threshold: |t| > {T_THRESHOLD}.\n"
    )
    lines.append(
        "| # | Subgroup | n | mean_resid | std | t-stat | p-value | Naive hit rate | Real? |"
    )
    lines.append(
        "|---|----------|--:|----------:|----:|-------:|--------:|:--------------:|:-----:|"
    )
    for i, sg in enumerate(q2, start=1):
        real = "YES" if (not np.isnan(sg["t_stat"]) and abs(sg["t_stat"]) > T_THRESHOLD) else "no"
        hit_label = "under" if sg["hit_col"] == "under_actual" else "over"
        lines.append(
            f"| {i} | {sg['label']} "
            f"| {sg['n']} "
            f"| {sg['mean_resid']:+.2f} "
            f"| {sg['std_resid']:.2f} "
            f"| {sg['t_stat']:.2f} "
            f"| {_fmt_pval(sg['p_val'])} "
            f"| {sg['hit_rate']:.3%} ({hit_label}) "
            f"| {real} |"
        )
    lines.append("")
    lines.append(
        "> Subgroup 5 (high-wind × under interaction) is the same game sample as Subgroup 1 "
        "reframed around the under-betting hypothesis; its t-stat is identical by construction."
    )

    lines.append("\n---\n")

    # -----------------------------------------------------------------------
    lines.append("## Q3: Verdict Details\n")
    lines.append(f"**Gates applied:**")
    lines.append(f"- Subgroup |t| > {T_THRESHOLD}")
    lines.append(f"- Subgroup n ≥ {MIN_N_SUBGROUP}")
    lines.append(f"- Naive hit rate ≥ {MIN_OU_ACC:.1%} (implied O/U accuracy)\n")

    if verdict["passing_subgroups"]:
        lines.append("**Passing subgroups:**")
        for sg in verdict["passing_subgroups"]:
            lines.append(f"- {sg['label']}: n={sg['n']}, t={sg['t_stat']:.2f}, hit={sg['hit_rate']:.1%}")
    else:
        lines.append("**No subgroup passed all three gates.**")

    lines.append("")
    lines.append(f"**Verdict: {verdict['verdict']}**")
    lines.append("")
    lines.append(textwrap.fill(verdict["rationale"], width=90))

    lines.append("\n---\n")

    # -----------------------------------------------------------------------
    lines.append("## Data Coverage Notes\n")
    total_n = len(df)
    dome_n = df["is_dome"].sum()
    high_wind_n = df["high_wind_outdoor"].sum()
    cold_n = df["cold_outdoor"].sum()
    pace_n = df["both_high_pace"].sum()
    total_line_null = df["total_line"].isna().sum()
    wind_null = df["wind_speed"].isna().sum()
    temp_null = df["temperature"].isna().sum()
    pace_null = (df["home_pace_roll3"].isna() | df["away_pace_roll3"].isna()).sum()

    lines.append(f"- OOF games: {total_n} (seasons 2019–2024)")
    lines.append(f"- total_line missing: {total_line_null}")
    lines.append(f"- wind_speed missing: {wind_null} ({wind_null/total_n:.1%}) — dome/closed-roof games have wind=0")
    lines.append(f"- temperature missing: {temp_null} ({temp_null/total_n:.1%}) — dome/closed-roof games have temp=72")
    lines.append(f"- pace_roll3 missing (either team): {pace_null} ({pace_null/total_n:.1%}) — typically early-season games")
    lines.append(f"- Dome games in OOF: {dome_n} ({dome_n/total_n:.1%})")
    lines.append(f"- High-wind outdoor games (wind ≥ 15 mph): {high_wind_n} ({high_wind_n/total_n:.1%})")
    lines.append(f"- Cold outdoor games (temp ≤ 25F): {cold_n} ({cold_n/total_n:.1%})")
    lines.append(f"- Both-teams top-quartile pace: {pace_n} ({pace_n/total_n:.1%})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("Phase 1.2 — Game Totals Kill-or-Fix Diagnosis")
    print("=" * 70)

    print("\nLoading data...")
    df = load_data()
    print(f"  OOF games loaded: {len(df)}")
    print(f"  Seasons: {sorted(df['season'].unique())}")

    # Q1
    print("\n--- Q1: Signal Beyond the Line ---")
    q1 = q1_signal_beyond_line(df)
    print(f"  n = {q1['n']}")
    print(f"  OLS: actual_total ~ total_line + meta_oof_pred")
    print(f"    Intercept:      coef={q1['b0']:.3f}, t={q1['t0']:.2f}, p={_fmt_pval(q1['p0'])}")
    print(f"    total_line:     coef={q1['b1']:.3f}, t={q1['t1']:.2f}, p={_fmt_pval(q1['p1'])}")
    print(f"    meta_oof_pred:  coef={q1['b2']:.3f}, t={q1['t2']:.2f}, p={_fmt_pval(q1['p2'])}")
    print(f"  R²: {q1['r2']:.4f}")
    print(f"  Partial corr (meta_oof_pred | total_line): {q1['partial_corr_oof']:.4f}")
    print(f"  Overall O/U rate (fraction overs): {q1['ou_overall_rate']:.2%}")
    print(f"  Model O/U accuracy: {q1['ou_model_accuracy']:.2%}")

    # Q2
    print("\n--- Q2: Residual Subgroup Analysis ---")
    q2 = q2_residual_edges(df)
    header = f"  {'Subgroup':<50} {'n':>5} {'mean_r':>7} {'std':>6} {'t':>6} {'p':>7} {'hit%':>6} {'real?':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for sg in q2:
        real_flag = "YES" if (not np.isnan(sg["t_stat"]) and abs(sg["t_stat"]) > T_THRESHOLD) else "no"
        label_short = sg["label"][:50]
        print(
            f"  {label_short:<50} {sg['n']:>5} {sg['mean_resid']:>+7.2f} {sg['std_resid']:>6.2f} "
            f"{sg['t_stat']:>6.2f} {sg['p_val']:>7.4f} {sg['hit_rate']:>8.3%} {real_flag:>6}"
        )

    # Q3
    print("\n--- Q3: Verdict ---")
    verdict = q3_verdict(q1, q2)
    print(f"  VERDICT: {verdict['verdict']}")
    print(f"  {textwrap.fill(verdict['rationale'], width=66, subsequent_indent='  ')}")

    # Write markdown report
    report_text = build_report(df, q1, q2, verdict)
    VERDICT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VERDICT_PATH.write_text(report_text, encoding="utf-8")
    print(f"\nVerdict written to: {VERDICT_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
