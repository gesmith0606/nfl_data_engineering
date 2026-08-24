#!/usr/bin/env python3
"""Back-test the doctrine's bust/breakout signals on real seasons (2021-2025).

For each season with a Sept-1 ADP snapshot (``data/adp/history/adp_ffc_half_ppr_<yr>.csv``)
and Silver weekly usage for that season and the one before, this script:

1. Prices every drafted player by positional ADP rank.
2. Scores the season: half-PPR points from Silver usage -> positional finish.
3. Labels outcomes the way the industry validates them (docs/DRAFT_DOCTRINE.md §28):
   BUST  = finished >= 10 positional spots below ADP rank (or played <= 8 games),
   BEAT  = finished >= 10 positional spots above ADP rank.
4. Computes each doctrine signal from information available BEFORE the season
   (prior-year usage, age on Sept 1, ADP tier) and reports bust/beat rates for
   flagged vs unflagged players, per signal, pooled across seasons.

Signals tested: §20 RB age >= 27, §21 prior top-5 finish, §22 prior TD share > 35 %,
§34 prior >= 50 targets & < 5 TDs (WR/TE), ADP tier base rates (§15 dead zone).

    python scripts/backtest_draft_flags.py [--seasons 2021 2022 2023 2024 2025] [--max-adp 150]
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import List, Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.draft_optimizer import name_key  # noqa: E402
from src.draft_value import (  # noqa: E402
    RB_AGE_CLIFF,
    TD_SHARE_MAX,
    XTD_OVER_GAP,
    load_prior_xtd,
    load_registry_features,
)

_USAGE = os.path.join("data", "silver", "players", "usage", "season={season}", "*.parquet")
_ADP = os.path.join("data", "adp", "history", "adp_ffc_half_ppr_{season}.csv")
POS = ["QB", "RB", "WR", "TE"]


def season_totals(season: int) -> Optional[pd.DataFrame]:
    files = sorted(glob.glob(_USAGE.format(season=season)))
    if not files:
        return None
    df = pd.read_parquet(files[-1])
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    df = df[df["position"].isin(POS)].copy()
    df["half_ppr"] = df["fantasy_points"].fillna(0) + 0.5 * df["receptions"].fillna(0)
    df["tds"] = df.get("rushing_tds", 0).fillna(0) + df.get("receiving_tds", 0).fillna(0) + df.get("passing_tds", 0).fillna(0)
    name_col = "player_display_name" if "player_display_name" in df.columns else "player_name"
    tot = (
        df.groupby(["player_id", "position"])
        .agg(name=(name_col, "first"), games=("week", "nunique"), points=("half_ppr", "sum"),
             targets=("targets", "sum"), tds=("tds", "sum"))
        .reset_index()
    )
    tot["_name_key"] = tot["name"].map(name_key)
    tot["pos_rank"] = tot.groupby("position")["points"].rank(ascending=False, method="first").astype(int)
    return tot


def load_adp(season: int) -> Optional[pd.DataFrame]:
    path = _ADP.format(season=season)
    if not os.path.exists(path):
        return None
    adp = pd.read_csv(path)
    adp = adp[adp["position"].isin(POS)].copy()
    adp["_name_key"] = adp["player_name"].map(name_key)
    adp["adp_pos_rank"] = adp.groupby("position")["adp"].rank(method="first").astype(int)
    return adp[["_name_key", "position", "adp", "adp_pos_rank"]]


def build_season(season: int, max_adp: float) -> Optional[pd.DataFrame]:
    adp, cur, prior = load_adp(season), season_totals(season), season_totals(season - 1)
    if adp is None or cur is None or prior is None:
        return None
    df = adp[adp["adp"] <= max_adp].merge(cur, on=["_name_key", "position"], how="left")
    df = df.merge(
        prior[["_name_key", "position", "points", "pos_rank", "targets", "tds", "games"]].rename(
            columns={"points": "prior_points", "pos_rank": "prior_pos_rank", "targets": "prior_targets",
                     "tds": "prior_tds", "games": "prior_games"}),
        on=["_name_key", "position"], how="left",
    )
    reg = load_registry_features(season)
    if not reg.empty:
        df = df.merge(reg[["_name_key", "position", "age"]], on=["_name_key", "position"], how="left")
    else:
        df["age"] = float("nan")
    xtd = load_prior_xtd(season)
    if not xtd.empty and "player_id" in df.columns:
        df = df.merge(xtd, on="player_id", how="left")
    if "prior_xtd_gap" not in df.columns:
        df["prior_xtd_gap"] = float("nan")
    df["season"] = season
    # Unmatched actuals = did not play (or a name we can't join) -> treat as bust only
    # when games are known; drop unjoinable rows to keep the test honest.
    df = df.dropna(subset=["pos_rank"])
    df["bust"] = (df["pos_rank"] - df["adp_pos_rank"] >= 10) | (df["games"] <= 8)
    df["beat"] = df["adp_pos_rank"] - df["pos_rank"] >= 10
    df["prior_td_share"] = (6 * df["prior_tds"]) / df["prior_points"].replace(0, float("nan"))
    df["adp_round"] = ((df["adp"] - 1) // 12 + 1).astype(int)
    return df


def rate_table(df: pd.DataFrame, signals: dict) -> pd.DataFrame:
    rows = []
    for label, (mask, scope) in signals.items():
        pool = df[scope] if scope is not None else df
        flagged = pool[mask.reindex(pool.index).fillna(False).astype(bool)]
        rest = pool.drop(flagged.index)
        if flagged.empty:
            continue
        rows.append(
            {
                "signal": label,
                "n_flagged": len(flagged),
                "bust_rate_flagged": round(flagged["bust"].mean(), 3),
                "bust_rate_rest": round(rest["bust"].mean(), 3) if not rest.empty else float("nan"),
                "beat_rate_flagged": round(flagged["beat"].mean(), 3),
                "beat_rate_rest": round(rest["beat"].mean(), 3) if not rest.empty else float("nan"),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["bust_lift"] = (out["bust_rate_flagged"] / out["bust_rate_rest"]).round(2)
        out["beat_lift"] = (out["beat_rate_flagged"] / out["beat_rate_rest"]).round(2)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Back-test doctrine bust/breakout signals on past seasons")
    p.add_argument("--seasons", type=int, nargs="+", default=[2021, 2022, 2023, 2024, 2025])
    p.add_argument("--max-adp", type=float, default=150)
    args = p.parse_args(argv)

    frames = [f for s in args.seasons if (f := build_season(s, args.max_adp)) is not None]
    if not frames:
        print("ERROR: no season had ADP history + usage for both the season and the prior season.")
        return 1
    df = pd.concat(frames, ignore_index=True)
    print(f"Seasons: {sorted(df['season'].unique().tolist())} | drafted players (ADP <= {args.max_adp:.0f}) with actuals: {len(df)}")
    print(f"Base rates: bust {df['bust'].mean():.1%} | beat {df['beat'].mean():.1%}  (bust = >=10 positional spots below ADP or <=8 games)")

    is_rb, is_wrte = df["position"] == "RB", df["position"].isin(["WR", "TE"])
    signals = {
        "§20 RB age >= 27 (vs other RBs)": (is_rb & (df["age"] >= RB_AGE_CLIFF), is_rb),
        "§20 RB age >= 28 (vs other RBs)": (is_rb & (df["age"] >= RB_AGE_CLIFF + 1), is_rb),
        "§21 prior top-5 positional finish": (df["prior_pos_rank"] <= 5, None),
        "§21 prior top-5 RB only": (is_rb & (df["prior_pos_rank"] <= 5), is_rb),
        f"§22 prior TD share > {int(TD_SHARE_MAX*100)}%": (df["prior_td_share"] > TD_SHARE_MAX, None),
        "§34 WR/TE >=50 tgt & <5 TD prior (positive regression)": (is_wrte & (df["prior_targets"] >= 50) & (df["prior_tds"] < 5), is_wrte),
        f"§22 real xTD: prior TDs >= +{XTD_OVER_GAP} over expected": (df["prior_xtd_gap"] >= XTD_OVER_GAP, None),
        "§15 RB drafted rounds 3-7 (dead zone, vs other RBs)": (is_rb & df["adp_round"].between(3, 7), is_rb),
        "WR drafted rounds 3-7 (vs other WRs)": ((df["position"] == "WR") & df["adp_round"].between(3, 7), df["position"] == "WR"),
    }
    print("\nSIGNAL HIT RATES (flagged vs the rest of the same pool; lift > 1 = signal works)")
    pd.set_option("display.width", 200)
    print(rate_table(df, signals).to_string(index=False))

    print("\nBUST / BEAT RATE BY ADP ROUND (all positions)")
    by_round = df.groupby("adp_round").agg(n=("bust", "size"), bust=("bust", "mean"), beat=("beat", "mean")).round(3)
    print(by_round.head(12).to_string())
    print("\nBUST RATE BY POSITION x ADP ROUND (rounds 1-8)")
    pivot = df[df["adp_round"] <= 8].pivot_table(index="position", columns="adp_round", values="bust", aggfunc="mean").round(2)
    print(pivot.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
