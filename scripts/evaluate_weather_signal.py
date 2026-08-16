"""Weather signal evaluation -- does the shipped model's backtest residual correlate with weather?

Core question (per .planning/WEATHER_DATA_2026_08_16.md mission): Vegas totals
already price in wind/precipitation. If the shipped fantasy model's backtest
errors do NOT correlate with wind/precip after the fact, weather is a dead
lever -- the market beat us to it. If errors DO correlate, weather features
are worth shipping.

Joins output/backtest/backtest_half_ppr_ml_fullfeatures_BASELINE_combined.csv
(2022-2024 sealed backtest, player_id/recent_team/week/season/error/abs_error)
against src/weather_features.compute_weather_features() on (season, week, team).

Usage:
    python scripts/evaluate_weather_signal.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from weather_features import compute_weather_features  # noqa: E402

BACKTEST_PATH = "output/backtest/backtest_half_ppr_ml_fullfeatures_BASELINE_combined.csv"
PASS_CATCHING_POSITIONS = {"QB", "WR", "TE"}


def bucket_wind(w):
    if w < 10:
        return "0-9 mph"
    if w < 15:
        return "10-14 mph"
    if w < 20:
        return "15-19 mph"
    return "20+ mph"


def bucket_precip(p):
    if p <= 0.001:
        return "none"
    if p <= 0.05:
        return "trace (<=0.05in)"
    if p <= 0.25:
        return "light-moderate (0.05-0.25in)"
    return "heavy (>0.25in)"


def main():
    bt = pd.read_csv(BACKTEST_PATH)
    bt = bt.rename(columns={"recent_team": "team"})
    print(f"Backtest rows: {len(bt)}  seasons: {sorted(bt['season'].unique())}")

    weather = compute_weather_features(seasons=sorted(bt["season"].unique().tolist()))
    print(f"Weather feature rows: {len(weather)}")

    merged = bt.merge(weather, on=["season", "week", "team"], how="left")
    n_unmatched = merged["wind_speed_mph"].isna().sum()
    print(f"Unmatched (no weather row): {n_unmatched} / {len(merged)} ({n_unmatched / len(merged):.1%})")
    merged = merged.dropna(subset=["wind_speed_mph", "precip_in"])
    # Left-join upcasts bool -> object (to hold NaN for the few unmatched
    # rows); re-cast after dropna or `~merged["is_dome"]` bitwise-inverts
    # Python bools (~True == -2) instead of logically negating them.
    merged["is_dome"] = merged["is_dome"].astype(bool)

    print("\n=== Lever firing rate (gated-experiment-coverage-check discipline) ===")
    print(f"Rows with weather joined: {len(merged)} / {len(bt)} ({len(merged) / len(bt):.1%})")
    print(f"Rows with is_dome=True: {merged['is_dome'].sum()} ({merged['is_dome'].mean():.1%})")
    print(f"Rows with wind >= 15mph: {(merged['wind_speed_mph'] >= 15).sum()}")
    print(f"Rows with precip > 0: {(merged['precip_in'] > 0).sum()}")
    outdoor = merged[~merged["is_dome"]]
    print(f"Outdoor rows: {len(outdoor)}, wind>=15 among outdoor: {(outdoor['wind_speed_mph'] >= 15).sum()} ({(outdoor['wind_speed_mph'] >= 15).mean():.1%})")

    for label, pos_filter in [
        ("ALL POSITIONS", merged["position"].notna()),
        ("PASS-CATCHING (QB/WR/TE)", merged["position"].isin(PASS_CATCHING_POSITIONS)),
        ("RB", merged["position"] == "RB"),
    ]:
        sub = merged[pos_filter & (~merged["is_dome"])].copy()
        print(f"\n{'=' * 70}\n{label} -- outdoor games only, n={len(sub)}\n{'=' * 70}")

        print("\n-- Wind buckets --")
        sub["wind_bucket"] = sub["wind_speed_mph"].apply(bucket_wind)
        wind_summary = sub.groupby("wind_bucket").agg(
            n=("error", "size"),
            mean_error=("error", "mean"),
            mean_abs_error=("abs_error", "mean"),
            mean_actual=("actual_points", "mean"),
            mean_projected=("projected_points", "mean"),
        ).reindex(["0-9 mph", "10-14 mph", "15-19 mph", "20+ mph"])
        print(wind_summary.round(3).to_string())

        print("\n-- Precip buckets --")
        sub["precip_bucket"] = sub["precip_in"].apply(bucket_precip)
        precip_summary = sub.groupby("precip_bucket").agg(
            n=("error", "size"),
            mean_error=("error", "mean"),
            mean_abs_error=("abs_error", "mean"),
            mean_actual=("actual_points", "mean"),
            mean_projected=("projected_points", "mean"),
        ).reindex(["none", "trace (<=0.05in)", "light-moderate (0.05-0.25in)", "heavy (>0.25in)"])
        print(precip_summary.round(3).to_string())

        if len(sub) >= 10:
            r_wind, p_wind = stats.pearsonr(sub["wind_speed_mph"], sub["error"])
            r_wind_abs, p_wind_abs = stats.pearsonr(sub["wind_speed_mph"], sub["abs_error"])
            r_precip, p_precip = stats.pearsonr(sub["precip_in"], sub["error"])
            r_precip_abs, p_precip_abs = stats.pearsonr(sub["precip_in"], sub["abs_error"])
            print(f"\nPearson r(wind_speed_mph, error) = {r_wind:.4f}  p={p_wind:.4f}")
            print(f"Pearson r(wind_speed_mph, abs_error) = {r_wind_abs:.4f}  p={p_wind_abs:.4f}")
            print(f"Pearson r(precip_in, error) = {r_precip:.4f}  p={p_precip:.4f}")
            print(f"Pearson r(precip_in, abs_error) = {r_precip_abs:.4f}  p={p_precip_abs:.4f}")

            # High-wind vs low-wind t-test (>=15mph vs <15mph), matches
            # game_context.is_high_wind threshold
            hi = sub.loc[sub["wind_speed_mph"] >= 15, "error"]
            lo = sub.loc[sub["wind_speed_mph"] < 15, "error"]
            if len(hi) >= 5 and len(lo) >= 5:
                t, p_t = stats.ttest_ind(hi, lo, equal_var=False)
                print(f"\nt-test error: high-wind(n={len(hi)}, mean={hi.mean():.3f}) vs low-wind(n={len(lo)}, mean={lo.mean():.3f})  t={t:.3f} p={p_t:.4f}")

            hi_abs = sub.loc[sub["wind_speed_mph"] >= 15, "abs_error"]
            lo_abs = sub.loc[sub["wind_speed_mph"] < 15, "abs_error"]
            if len(hi_abs) >= 5 and len(lo_abs) >= 5:
                t2, p_t2 = stats.ttest_ind(hi_abs, lo_abs, equal_var=False)
                print(f"t-test abs_error: high-wind(n={len(hi_abs)}, mean={hi_abs.mean():.3f}) vs low-wind(n={len(lo_abs)}, mean={lo_abs.mean():.3f})  t={t2:.3f} p={p_t2:.4f}")

            wet = sub.loc[sub["precip_in"] > 0.05, "error"]
            dry = sub.loc[sub["precip_in"] <= 0.05, "error"]
            if len(wet) >= 5 and len(dry) >= 5:
                t3, p_t3 = stats.ttest_ind(wet, dry, equal_var=False)
                print(f"\nt-test error: wet>0.05in(n={len(wet)}, mean={wet.mean():.3f}) vs dry(n={len(dry)}, mean={dry.mean():.3f})  t={t3:.3f} p={p_t3:.4f}")

    # Dome vs outdoor sanity check (should show ~no difference if weather join is doing its job)
    print(f"\n{'=' * 70}\nDOME vs OUTDOOR sanity check (all positions)\n{'=' * 70}")
    dome_err = merged.loc[merged["is_dome"], "abs_error"]
    outdoor_err = merged.loc[~merged["is_dome"], "abs_error"]
    print(f"Dome: n={len(dome_err)}, mean abs_error={dome_err.mean():.3f}")
    print(f"Outdoor: n={len(outdoor_err)}, mean abs_error={outdoor_err.mean():.3f}")


if __name__ == "__main__":
    main()
