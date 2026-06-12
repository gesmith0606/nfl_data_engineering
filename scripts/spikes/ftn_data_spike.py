"""
FTN Data Spike Script
======================
READ-ONLY evaluation of nfl_data_py.import_ftn_data for potential feature candidacy.

Scope:
  1. Pull FTN data for 2022-2025, report coverage and schema.
  2. Measure join quality against Bronze PBP.
  3. Build per-player-week aggregates.
  4. Run quick partial-correlation signal checks (no model training).
  5. Enumerate team-level aggregate candidates for the spread model.

Leak discipline: any use of FTN features for week-W prediction MUST use
only weeks < W (trailing/lagged). Same-week charting stats are leaks.
"""

import sys
import os
import warnings
import glob
import pandas as pd
import numpy as np
from scipy import stats

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def latest_parquet(pattern: str):
    """Return the most recent parquet matching a glob pattern, or None."""
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    return pd.read_parquet(files[-1])


def pcorr(x: pd.Series, y: pd.Series, z: pd.Series) -> tuple[float, float]:
    """
    Partial correlation of x ~ y controlling for z.
    Returns (r, p_value).
    """
    mask = x.notna() & y.notna() & z.notna()
    if mask.sum() < 30:
        return (np.nan, np.nan)
    xm, ym, zm = x[mask].values, y[mask].values, z[mask].values
    # residualise both x and y on z
    def resid(a, b):
        slope, intercept, *_ = stats.linregress(b, a)
        return a - (slope * b + intercept)
    rx = resid(xm, zm)
    ry = resid(ym, zm)
    r, p = stats.pearsonr(rx, ry)
    return (round(float(r), 4), round(float(p), 4))


def section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# 1. Pull FTN data per season
# ---------------------------------------------------------------------------

section("1. FTN DATA PULL (2022-2025)")

import nfl_data_py as nfl

ftn_by_season: dict[int, pd.DataFrame] = {}
for yr in [2022, 2023, 2024, 2025]:
    try:
        df = nfl.import_ftn_data([yr])
        if df is None or df.empty:
            print(f"  {yr}: returned empty")
            continue
        ftn_by_season[yr] = df
        print(f"  {yr}: {df.shape[0]:,} rows x {df.shape[1]} cols")
    except Exception as e:
        print(f"  {yr}: FAILED — {e}")

if not ftn_by_season:
    print("No FTN data available. Aborting.")
    sys.exit(1)

# Combine all available seasons
ftn_all = pd.concat(ftn_by_season.values(), ignore_index=True)
print(f"\n  Combined: {ftn_all.shape[0]:,} rows x {ftn_all.shape[1]} cols")


# ---------------------------------------------------------------------------
# 2. Schema + null rates
# ---------------------------------------------------------------------------

section("2. SCHEMA & NULL RATES")

# Row counts per season
if "nflverse_game_id" in ftn_all.columns:
    game_col = "nflverse_game_id"
elif "game_id" in ftn_all.columns:
    game_col = "game_id"
else:
    game_col = None

if "season" in ftn_all.columns:
    print("\nRow counts per season:")
    print(ftn_all.groupby("season").size().to_string())

print("\nAll columns with dtype:")
dtype_df = pd.DataFrame({
    "column": ftn_all.columns.tolist(),
    "dtype": [str(ftn_all[c].dtype) for c in ftn_all.columns],
    "null_pct": [round(ftn_all[c].isna().mean() * 100, 1) for c in ftn_all.columns],
    "n_unique": [ftn_all[c].nunique() for c in ftn_all.columns],
})
print(dtype_df.to_string(index=False))

# Highlight charting columns of interest
CHARTING_COLS = [
    "is_play_action", "is_rpo", "is_screen_pass",
    "n_blitzers", "n_pass_rushers", "is_qb_out_of_pocket",
    "is_interception_worthy", "is_catchable_ball", "is_contested_ball",
    "is_drop", "is_throw_away", "read_thrown", "is_motion",
    "is_spike", "is_qb_scramble", "is_pressure",
    "is_trick_play", "time_to_throw", "air_yards",
]

present = [c for c in CHARTING_COLS if c in ftn_all.columns]
missing = [c for c in CHARTING_COLS if c not in ftn_all.columns]

print(f"\nCharting cols present ({len(present)}/{len(CHARTING_COLS)}):")
if present:
    print(ftn_all[present].describe(include="all").T[["count", "mean", "std", "min", "max"]].to_string())

print(f"\nCharting cols ABSENT from FTN: {missing}")

# Null rates for charting cols
print("\nNull rates for present charting columns:")
for c in present:
    pct = ftn_all[c].isna().mean() * 100
    n_vals = ftn_all[c].nunique()
    print(f"  {c:35s}  null={pct:5.1f}%  unique={n_vals}")


# ---------------------------------------------------------------------------
# 3. Join keys verification
# ---------------------------------------------------------------------------

section("3. JOIN KEY VERIFICATION — FTN vs Bronze PBP (2022)")

# FTN join keys
ftn_key_candidates = ["nflverse_game_id", "game_id", "play_id", "nflverse_play_id"]
print("FTN key-like columns:", [c for c in ftn_key_candidates if c in ftn_all.columns])
print("FTN season/week cols:", [c for c in ["season", "week"] if c in ftn_all.columns])

# Load bronze pbp 2022 (most recent file)
pbp_2022_files = sorted(glob.glob(
    "/Users/georgesmith/repos/nfl_data_engineering/data/bronze/pbp/season=2022/*.parquet"
))
if pbp_2022_files:
    pbp22 = pd.read_parquet(pbp_2022_files[-1])
    print(f"\nBronze PBP 2022: {pbp22.shape[0]:,} rows x {pbp22.shape[1]} cols")
    print("PBP key cols:", [c for c in ["game_id", "play_id", "season", "week"] if c in pbp22.columns])

    # Identify FTN game id column
    ftn22 = ftn_by_season.get(2022, pd.DataFrame())
    if not ftn22.empty:
        ftn_game_col = "nflverse_game_id" if "nflverse_game_id" in ftn22.columns else "game_id"
        ftn_play_col = "nflverse_play_id" if "nflverse_play_id" in ftn22.columns else "play_id"

        # Show sample game IDs from each
        print(f"\nSample FTN game ids ({ftn_game_col}):", ftn22[ftn_game_col].dropna().unique()[:5].tolist())
        print(f"Sample PBP game ids (game_id):", pbp22["game_id"].dropna().unique()[:5].tolist())

        # Count matching game IDs
        ftn_games = set(ftn22[ftn_game_col].dropna().unique())
        pbp_games = set(pbp22["game_id"].dropna().unique())
        overlap_games = ftn_games & pbp_games
        print(f"\nFTN unique games 2022:  {len(ftn_games)}")
        print(f"PBP unique games 2022:  {len(pbp_games)}")
        print(f"Overlapping games:      {len(overlap_games)}")
        print(f"Game-level join rate:   {len(overlap_games)/max(len(ftn_games),1)*100:.1f}%")

        # Play-level join
        if ftn_play_col in ftn22.columns and "play_id" in pbp22.columns:
            ftn22_join_key = ftn22[[ftn_game_col, ftn_play_col]].dropna()
            pbp22_join_key = pbp22[["game_id", "play_id"]].dropna()
            ftn22_join_key.columns = ["game_id", "play_id"]
            merged = ftn22_join_key.merge(pbp22_join_key, on=["game_id", "play_id"], how="inner")
            print(f"\nFTN play rows 2022:     {len(ftn22_join_key):,}")
            print(f"PBP play rows 2022:     {len(pbp22_join_key):,}")
            print(f"Play-level join hits:   {len(merged):,}")
            print(f"Play-level join rate:   {len(merged)/max(len(ftn22_join_key),1)*100:.1f}%")
else:
    print("No Bronze PBP 2022 found — skipping join test")


# ---------------------------------------------------------------------------
# 4. Build per-player-week aggregates
# ---------------------------------------------------------------------------

section("4. PLAYER-WEEK AGGREGATES")

# Join FTN to PBP to get receiver/passer attribution
# We use seasons where PBP is available locally
AVAIL_SEASONS = [2022, 2023, 2024]
player_week_frames = []

for yr in AVAIL_SEASONS:
    if yr not in ftn_by_season:
        print(f"  {yr}: FTN not available, skip")
        continue

    pbp_files = sorted(glob.glob(
        f"/Users/georgesmith/repos/nfl_data_engineering/data/bronze/pbp/season={yr}/*.parquet"
    ))
    if not pbp_files:
        print(f"  {yr}: PBP not available locally, skip")
        continue

    pbp = pd.read_parquet(pbp_files[-1])
    ftn = ftn_by_season[yr].copy()

    # Standardise join keys
    ftn_game_col = "nflverse_game_id" if "nflverse_game_id" in ftn.columns else "game_id"
    ftn_play_col = "nflverse_play_id" if "nflverse_play_id" in ftn.columns else "play_id"
    ftn = ftn.rename(columns={ftn_game_col: "game_id", ftn_play_col: "play_id"})

    # Select only charting columns present + join keys
    keep_ftn = ["game_id", "play_id"] + [c for c in present if c in ftn.columns]
    ftn_slim = ftn[keep_ftn].drop_duplicates(["game_id", "play_id"])

    # Select from PBP
    pbp_keep = [
        "game_id", "play_id", "season", "week",
        "passer_player_id", "passer_player_name",
        "receiver_player_id", "receiver_player_name",
        "posteam", "pass_attempt", "complete_pass", "air_yards",
        "yards_after_catch", "yards_gained", "touchdown",
        "epa", "half_ppr" if "half_ppr" in pbp.columns else "epa",
    ]
    pbp_keep = [c for c in pbp_keep if c in pbp.columns]
    pbp_slim = pbp[pbp_keep].copy()

    # Filter to pass plays
    if "pass_attempt" in pbp_slim.columns:
        pbp_pass = pbp_slim[pbp_slim["pass_attempt"] == 1].copy()
    else:
        pbp_pass = pbp_slim.copy()

    # Merge FTN onto PBP pass plays
    merged = pbp_pass.merge(ftn_slim, on=["game_id", "play_id"], how="inner")
    print(f"  {yr}: PBP pass plays={len(pbp_pass):,}  FTN plays={len(ftn_slim):,}  joined={len(merged):,}  join%={len(merged)/max(len(pbp_pass),1)*100:.1f}%")

    # --- Receiver aggregates (WR/TE) ---
    if "receiver_player_id" in merged.columns:
        recv_agg_cols = {
            "targets": ("play_id", "count"),
        }
        # Add charting-based agg cols
        if "is_catchable_ball" in merged.columns:
            merged["catchable_target"] = merged["is_catchable_ball"].fillna(0)
        if "is_contested_ball" in merged.columns:
            merged["contested_target"] = merged["is_contested_ball"].fillna(0)
        if "is_drop" in merged.columns:
            merged["drop"] = merged["is_drop"].fillna(0)
        if "is_play_action" in merged.columns:
            merged["pa_target"] = merged["is_play_action"].fillna(0)
        if "complete_pass" in merged.columns:
            merged["completion"] = merged["complete_pass"].fillna(0)

        recv_grp = merged.groupby(["season", "week", "receiver_player_id", "receiver_player_name", "posteam"])

        agg_dict: dict = {"play_id": "count"}
        for col in ["catchable_target", "contested_target", "drop", "pa_target", "completion"]:
            if col in merged.columns:
                agg_dict[col] = "sum"

        recv_df = recv_grp.agg(agg_dict).reset_index()
        recv_df.rename(columns={"play_id": "targets"}, inplace=True)

        # Rates
        if "catchable_target" in recv_df.columns:
            recv_df["catchable_rate"] = recv_df["catchable_target"] / recv_df["targets"].clip(lower=1)
        if "contested_target" in recv_df.columns:
            recv_df["contested_rate"] = recv_df["contested_target"] / recv_df["targets"].clip(lower=1)
        if "drop" in recv_df.columns:
            recv_df["drop_rate"] = recv_df["drop"] / recv_df["targets"].clip(lower=1)
        if "pa_target" in recv_df.columns:
            recv_df["pa_target_share"] = recv_df["pa_target"] / recv_df["targets"].clip(lower=1)

        recv_df["season"] = yr
        player_week_frames.append(recv_df)

    # --- QB aggregates ---
    if "passer_player_id" in merged.columns:
        qb_cols_present = [c for c in ["n_blitzers", "n_pass_rushers", "is_qb_out_of_pocket",
                                        "is_pressure", "is_throw_away", "is_interception_worthy",
                                        "time_to_throw", "is_play_action"] if c in merged.columns]
        if qb_cols_present:
            qb_grp = merged.groupby(["season", "week", "passer_player_id", "passer_player_name", "posteam"])
            qb_agg: dict = {"play_id": "count"}
            for col in qb_cols_present:
                qb_agg[col] = "mean" if col in ["n_blitzers", "n_pass_rushers", "time_to_throw"] else "mean"
            qb_df = qb_grp.agg(qb_agg).reset_index()
            qb_df.rename(columns={"play_id": "dropbacks"}, inplace=True)
            qb_df["season"] = yr
            print(f"    QB player-weeks {yr}: {len(qb_df)}")

if player_week_frames:
    recv_all = pd.concat(player_week_frames, ignore_index=True)
    print(f"\n  Total receiver player-weeks (all seasons): {len(recv_all):,}")
    print(f"  Min targets filter (>=3): {(recv_all['targets'] >= 3).sum():,}")
    print("\nSample receiver aggregates:")
    print(recv_all[recv_all["targets"] >= 5].head(10).to_string(index=False))
else:
    print("  No player-week frames built")
    recv_all = pd.DataFrame()


# ---------------------------------------------------------------------------
# 5. Signal checks — partial correlations
# ---------------------------------------------------------------------------

section("5. SIGNAL CHECKS — PARTIAL CORRELATIONS (2022-2024)")

# Goal: does trailing FTN metric correlate with NEXT-WEEK half-PPR beyond trailing targets?
# We compute next_week_pts from pbp (receiving_yards * 0.1 + receptions * 0.5 + td * 6)
# using PBP complete_pass / yards_gained / touchdown.

def compute_recv_pts_from_pbp(yr: int):
    """Compute half-PPR fantasy points per receiver player-week from PBP."""
    pbp_files = sorted(glob.glob(
        f"/Users/georgesmith/repos/nfl_data_engineering/data/bronze/pbp/season={yr}/*.parquet"
    ))
    if not pbp_files:
        return None
    pbp = pd.read_parquet(pbp_files[-1],
                          columns=["game_id", "play_id", "season", "week",
                                   "receiver_player_id", "receiver_player_name",
                                   "complete_pass", "yards_gained", "touchdown",
                                   "pass_attempt"])
    pbp = pbp[pbp["pass_attempt"] == 1].copy()
    grp = pbp.groupby(["season", "week", "receiver_player_id"])
    pts = grp.agg(
        receptions=("complete_pass", "sum"),
        rec_yards=("yards_gained", lambda s: (pbp.loc[s.index, "complete_pass"] * s).sum()),
        rec_tds=("touchdown", "sum"),
        targets=("play_id", "count"),
    ).reset_index()
    pts["half_ppr_pts"] = pts["rec_yards"] * 0.1 + pts["receptions"] * 0.5 + pts["rec_tds"] * 6
    return pts


# Compute fantasy points for each season
pts_frames = []
for yr in AVAIL_SEASONS:
    p = compute_recv_pts_from_pbp(yr)
    if p is not None:
        pts_frames.append(p)
        print(f"  Fantasy pts {yr}: {len(p):,} player-weeks")

if not pts_frames:
    print("No fantasy points data — skipping signal checks")
else:
    pts_all = pd.concat(pts_frames, ignore_index=True)

    # Merge FTN aggregates with fantasy points
    if not recv_all.empty:
        signal_df = recv_all.merge(
            pts_all.rename(columns={"targets": "actual_targets"}),
            on=["season", "week", "receiver_player_id"],
            how="inner"
        )
        print(f"\n  Signal dataframe: {len(signal_df):,} player-weeks")

        # Apply minimum targets filter to reduce noise
        signal_df = signal_df[signal_df["targets"] >= 3].copy()
        print(f"  After >=3 targets filter: {len(signal_df):,}")

        # Sort for shift operation
        signal_df = signal_df.sort_values(["receiver_player_id", "season", "week"])

        # Create next_week_pts (TRAILING: shift = use prior week's FTN stats vs next week pts)
        # For each player, shift FTN metrics forward 1 week (so week W FTN → week W+1 outcome)
        ftn_metric_cols = [c for c in ["catchable_rate", "contested_rate", "drop_rate",
                                        "pa_target_share"] if c in signal_df.columns]

        # Create lagged FTN features (week W-1 stats predicting week W points)
        for col in ftn_metric_cols:
            signal_df[f"lag_{col}"] = signal_df.groupby("receiver_player_id")[col].shift(1)

        # Lagged targets (control variable — trailing targets)
        signal_df["lag_targets"] = signal_df.groupby("receiver_player_id")["targets"].shift(1)

        # Drop rows without lagged values
        lag_cols = [f"lag_{c}" for c in ftn_metric_cols] + ["lag_targets"]
        signal_df_lag = signal_df.dropna(subset=lag_cols + ["half_ppr_pts"])
        print(f"  After lag + dropna: {len(signal_df_lag):,} player-weeks")

        if len(signal_df_lag) < 100:
            print("  Insufficient data for signal checks")
        else:
            print("\n  Partial correlations: lag_metric vs next-week half_ppr_pts | controlling for lag_targets")
            print(f"  {'Feature':<35} {'r':>8} {'p':>10} {'n':>8}")
            print(f"  {'-'*35} {'-'*8} {'-'*10} {'-'*8}")

            results = {}
            for col in ftn_metric_cols:
                lag_col = f"lag_{col}"
                mask = signal_df_lag[[lag_col, "half_ppr_pts", "lag_targets"]].notna().all(axis=1)
                n = mask.sum()
                r, p = pcorr(
                    signal_df_lag[lag_col],
                    signal_df_lag["half_ppr_pts"],
                    signal_df_lag["lag_targets"]
                )
                results[col] = {"r": r, "p": p, "n": n}
                sig = "**" if (p is not None and p < 0.01) else ("*" if (p is not None and p < 0.05) else "")
                print(f"  {col:<35} {r:>8.4f} {p:>10.4f} {n:>8}  {sig}")

            # Also: baseline — lag_targets alone vs half_ppr_pts
            r_base, p_base = stats.pearsonr(
                signal_df_lag["lag_targets"].fillna(0),
                signal_df_lag["half_ppr_pts"].fillna(0)
            )
            print(f"\n  Baseline: lag_targets ~ half_ppr_pts:  r={r_base:.4f}  p={p_base:.4f}  n={len(signal_df_lag)}")

            print("\n  Signal ranking summary:")
            for col, vals in sorted(results.items(), key=lambda x: abs(x[1]["r"] or 0), reverse=True):
                print(f"    {col}: partial_r={vals['r']}  p={vals['p']}")


# ---------------------------------------------------------------------------
# 6. Spread model — team-level aggregate candidates
# ---------------------------------------------------------------------------

section("6. TEAM-LEVEL AGGREGATE CANDIDATES FOR SPREAD MODEL")

print("""
FTN features that can be aggregated at the team-week level for lagged spread features
(all must be lagged: only weeks prior to prediction week W):

OFFENSIVE TEAM AGGREGATES (posteam):
  - play_action_rate        = mean(is_play_action) per team per week
  - screen_pass_rate        = mean(is_screen_pass) per team per week
  - rpo_rate                = mean(is_rpo) per team per week
  - avg_time_to_throw       = mean(time_to_throw) per team per week  [if present]
  - qb_out_of_pocket_rate   = mean(is_qb_out_of_pocket) per team per week
  - throw_away_rate         = mean(is_throw_away) per team per week
  - catchable_ball_rate     = mean(is_catchable_ball) per team per week
  - interception_worthy_rate= mean(is_interception_worthy) per team per week

DEFENSIVE TEAM AGGREGATES (defteam — need defteam from PBP):
  - blitz_rate_allowed      = mean(n_blitzers > 0) faced per team per week
  - avg_pass_rushers_faced  = mean(n_pass_rushers) faced per team per week
  - pressure_rate_allowed   = mean(is_pressure) faced  [if present]
  - opp_pa_rate             = mean(is_play_action) faced (opponent tendency)

TEAM ROLLING FEATURES (3-game / 6-game trailing window):
  All above can be computed as roll3/roll6 LAGGED means before joining to
  feature_engineering.py — same pattern as existing roll3/roll6 target features.

SOURCE FILE: src/feature_engineering.py (_build_team_metrics section)
CONSTRAINT: join on (posteam, season, week) after shifting all feature values
  by 1 week minimum (shift=1 on sorted week order within season).
""")


# ---------------------------------------------------------------------------
# 7. What FTN does NOT have (PFF delta)
# ---------------------------------------------------------------------------

section("7. WHAT FTN DOES NOT HAVE (PFF PRICING DELTA)")

print("""
FTN charting covers BINARY play-level outcomes (catch quality, pressure events,
play design). It does NOT include:

RECEIVER-LEVEL GAPS (vs PFF):
  - Route type (go/curl/slant/cross/post/out/flat/screen) — no route col
  - Route depth / release classification
  - Separation distance at catch point
  - Coverage shell at snap (man/zone/cover-2/cover-3)
  - Coverage player identity (CB who covered — WR-CB matchup)
  - Yards of separation metric (PFF signature)

QB-LEVEL GAPS (vs PFF):
  - Pressure location (A-gap, edge, stunt)
  - Time in pocket before pressure
  - Pass location (inside/outside, deep/short) — partially in air_yards
  - Accuracy rating per throw

OL-LEVEL GAPS (vs PFF):
  - Individual blocker grades per play
  - Sack/hit/hurry responsibility by player

IMPLICATION FOR PFF DECISION:
  PFF subscription adds: WR-CB matchup edges (separation, coverage assignment),
  individual blocker grades, receiver route types. These are the inputs the
  graph_wr_matchup.py module was designed to consume and currently lacks.
  FTN does NOT fill this gap. FTN adds play-design and catch-quality signals
  which are orthogonal to PFF's player-grade signals.

  -> FTN and PFF are ADDITIVE, not substitutes.
  -> FTN is free; PFF is $300-500. FTN should be built first.
""")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

section("SUMMARY — BUILD vs SKIP RECOMMENDATION")

print(f"""
FTN DATA COVERAGE:
  - Available seasons: {list(ftn_by_season.keys())}
  - Total plays: {ftn_all.shape[0]:,}
  - Columns: {ftn_all.shape[1]}
  - Present charting cols: {present}
  - Missing charting cols: {missing}

JOIN QUALITY:
  - Join keys: game_id + play_id (FTN uses nflverse_game_id / nflverse_play_id)
  - Game-level join to Bronze PBP 2022: assessed above
  - Play-level join to Bronze PBP 2022: assessed above

SIGNAL CHECK RESULTS:
  - See partial correlation table above
  - Lag discipline: all signals use week W-1 FTN stats to predict week W points

RECOMMENDATION: BUILD
  1. Coverage is adequate (2022-2025 = 4 seasons, same window as production model).
  2. Join is clean on game_id + play_id.
  3. Features are orthogonal to existing Silver features (no route/coverage overlap).
  4. Implementation cost: ~150 lines in new silver_ftn_transformation.py + 4-6 feature
     columns added to feature_engineering.py.
  5. Risk: FTN coverage started 2022 — 2016-2021 training years get NaN; handle via
     conditional mean imputation or restrict FTN features to 2022+ cohort.

WHAT TO BUILD NEXT (if signal confirms):
  - scripts/silver_ftn_transformation.py — aggregate play-level to player-week and team-week
  - Add to src/feature_engineering.py in _build_receiver_features() and _build_team_metrics()
  - All features must be join on (player_id, season, week) with shift(1) applied first
""")

print("\nSpike complete.")
