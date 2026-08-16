#!/usr/bin/env python3
"""Train span/recency experiment variants of the residual hybrid models.

Does NOT modify src/hybrid_projection.py or src/player_feature_engineering.py.
Recency weighting is implemented by monkeypatching
`player_feature_engineering.assemble_multiyear_player_features` at call time
(row duplication proportional to an exponential-decay weight) -- the local
`from player_feature_engineering import assemble_multiyear_player_features`
inside `train_and_save_residual_models` re-resolves the module attribute at
call time, so this affects only this process, not the shared module file.

Variants (see .planning/SPAN_RECENCY_EXPERIMENTS_2026_08_16.md):
    baseline     -- 2016-2024, same hyperparameters as shipped, same session
    more_years   -- 2012-2024
    recency_hl3  -- 2016-2024, exponential decay half-life=3 seasons
    recency_hl6  -- 2016-2024, exponential decay half-life=6 seasons
    combo        -- 2012-2024 + best half-life (only run if both gates win)

Shipped config (models/residual/*_meta.json, confirmed 2026-08-16):
    QB, RB: model_type=lgb, shap_feature_count=20
    WR, TE: model_type=ridge, shap_feature_count=60
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import player_feature_engineering as pfe  # noqa: E402
from hybrid_projection import train_and_save_residual_models  # noqa: E402

OUT_ROOT = os.path.join("models", "span_experiments_2026_08_16")

LGB_POSITIONS = ["QB", "RB"]
RIDGE_POSITIONS = ["WR", "TE"]

BASELINE_SEASONS = list(range(2016, 2025))  # 2016-2024
MORE_YEARS_SEASONS = list(range(2012, 2025))  # 2012-2024
REF_SEASON = 2024  # most-recent training season (recency anchor)
MAX_DUP = 12  # sanity cap on row-duplication multiplier


def make_weighted_assembler(half_life: float, ref_season: int = REF_SEASON):
    """Return a drop-in replacement for assemble_multiyear_player_features
    that duplicates rows by round(weight / min_weight), where
    weight = 0.5 ** (age / half_life) and age = ref_season - season.
    Integer row duplication == exact sample_weight for squared-error losses
    (Ridge, LightGBM default L2 objective).
    """
    _original = pfe.assemble_multiyear_player_features

    def _weighted(seasons):
        df = _original(seasons)
        if df.empty:
            return df
        age = (ref_season - df["season"]).clip(lower=0)
        weight = 0.5 ** (age / half_life)
        counts = np.round(weight / weight.min()).astype(int).clip(lower=1, upper=MAX_DUP)
        dup_df = df.loc[df.index.repeat(counts.values)].reset_index(drop=True)
        print(
            f"    [recency hl={half_life}] {len(df):,} rows -> {len(dup_df):,} "
            f"rows after duplication (multiplier range "
            f"{counts.min()}-{counts.max()})"
        )
        return dup_df

    return _weighted


def train_variant(variant: str) -> None:
    out_dir = os.path.join(OUT_ROOT, variant)
    os.makedirs(out_dir, exist_ok=True)

    if variant == "baseline":
        seasons = BASELINE_SEASONS
    elif variant == "more_years":
        seasons = MORE_YEARS_SEASONS
    elif variant == "recency_hl3":
        seasons = BASELINE_SEASONS
        pfe.assemble_multiyear_player_features = make_weighted_assembler(3.0)
    elif variant == "recency_hl6":
        seasons = BASELINE_SEASONS
        pfe.assemble_multiyear_player_features = make_weighted_assembler(6.0)
    elif variant == "combo":
        # 2012-2024 span + half-life=3 recency weighting (best of exp 2,
        # only invoked if both individual gates pass -- see driver logic)
        seasons = MORE_YEARS_SEASONS
        pfe.assemble_multiyear_player_features = make_weighted_assembler(3.0)
    else:
        raise ValueError(f"Unknown variant {variant}")

    print(f"\n{'=' * 70}\nTraining variant={variant} seasons={seasons[0]}-{seasons[-1]} "
          f"-> {out_dir}\n{'=' * 70}")

    results_lgb = train_and_save_residual_models(
        positions=LGB_POSITIONS,
        output_dir=out_dir,
        model_type="lgb",
        shap_feature_count=20,
        training_seasons=seasons,
    )
    results_ridge = train_and_save_residual_models(
        positions=RIDGE_POSITIONS,
        output_dir=out_dir,
        model_type="ridge",
        shap_feature_count=60,
        training_seasons=seasons,
    )

    # Restore the original (un-patched) assembler for the next variant in
    # this process, in case more than one variant runs in one invocation.
    pfe.assemble_multiyear_player_features = pfe.__dict__.get(
        "_original_assemble_multiyear_player_features",
        pfe.assemble_multiyear_player_features,
    )

    for pos, info in {**results_lgb, **results_ridge}.items():
        print(f"  {pos}: n_train={info['n_train']} train_mae={info['mae']:.3f} "
              f"n_features={info['n_features']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["baseline", "more_years", "recency_hl3", "recency_hl6"],
        choices=["baseline", "more_years", "recency_hl3", "recency_hl6", "combo"],
    )
    args = parser.parse_args()

    # Keep a true-original reference so repeated monkeypatching across
    # variants in one process always starts from the real function.
    pfe.__dict__["_original_assemble_multiyear_player_features"] = (
        pfe.assemble_multiyear_player_features
    )

    for variant in args.variants:
        # Always start each variant from the true original assembler.
        pfe.assemble_multiyear_player_features = pfe.__dict__[
            "_original_assemble_multiyear_player_features"
        ]
        train_variant(variant)

    return 0


if __name__ == "__main__":
    sys.exit(main())
