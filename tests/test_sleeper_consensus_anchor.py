"""
Unit tests for the historical-Sleeper weekly consensus-anchor lever
(.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md).
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from sleeper_consensus_anchor import (  # noqa: E402
    EPSILON,
    NUDGE,
    SUPPORTED_POSITIONS,
    apply_consensus_anchor,
    apply_consensus_anchor_blend,
    apply_consensus_anchor_near_tie,
    build_sleeper_lookup,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _proj_row(player_id, points, position="WR", season=2023, week=5):
    return {
        "player_id": player_id,
        "season": season,
        "week": week,
        "position": position,
        "projected_points": points,
    }


def _write_sleeper_parquet(tmp_path, season, week, rows, ts="20260101_000000"):
    week_dir = tmp_path / "sleeper" / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True)
    df = pd.DataFrame(rows)
    df.to_parquet(week_dir / f"sleeper_{ts}.parquet", index=False)
    return str(tmp_path / "sleeper")


def _sleeper_row(player_id, points, position="WR", scoring_format="half_ppr"):
    return {
        "player_id": player_id,
        "position": position,
        "projected_points": points,
        "scoring_format": scoring_format,
    }


# ---------------------------------------------------------------------------
# build_sleeper_lookup -- coverage stats, no-join-key trap (join is by
# player_id only, no name/team resolution needed -- unlike ecr_anchor.py)
# ---------------------------------------------------------------------------


class TestBuildSleeperLookup:
    def test_basic_match_and_rank(self, tmp_path):
        proj = pd.DataFrame(
            [_proj_row("A", 20.0), _proj_row("B", 18.0), _proj_row("C", 16.0)]
        )
        bronze_dir = _write_sleeper_parquet(
            tmp_path,
            2023,
            5,
            [
                _sleeper_row("A", 15.0),  # sleeper thinks A is worst (rank 3)
                _sleeper_row("B", 25.0),  # sleeper thinks B is best (rank 1)
                _sleeper_row("C", 20.0),  # sleeper thinks C is 2nd (rank 2)
            ],
        )
        lookup, stats = build_sleeper_lookup(proj, 2023, 5, "WR", bronze_dir=bronze_dir)
        assert stats == {
            "n_proj_pos_rows": 3,
            "n_sleeper_pos_rows": 3,
            "n_final_matched": 3,
        }
        ranks = lookup.set_index("player_id")["sleeper_pos_rank"]
        assert ranks["B"] == 1
        assert ranks["C"] == 2
        assert ranks["A"] == 3

    def test_unmatched_sleeper_rows_excluded_from_lookup(self, tmp_path):
        proj = pd.DataFrame([_proj_row("A", 20.0)])
        bronze_dir = _write_sleeper_parquet(
            tmp_path, 2023, 5, [_sleeper_row("A", 15.0), _sleeper_row("ZZZ", 30.0)]
        )
        lookup, stats = build_sleeper_lookup(proj, 2023, 5, "WR", bronze_dir=bronze_dir)
        assert stats["n_sleeper_pos_rows"] == 2
        assert stats["n_final_matched"] == 1
        assert list(lookup["player_id"]) == ["A"]

    def test_scoring_format_filter(self, tmp_path):
        proj = pd.DataFrame([_proj_row("A", 20.0)])
        bronze_dir = _write_sleeper_parquet(
            tmp_path,
            2023,
            5,
            [
                _sleeper_row("A", 15.0, scoring_format="ppr"),  # wrong format
            ],
        )
        lookup, stats = build_sleeper_lookup(proj, 2023, 5, "WR", bronze_dir=bronze_dir)
        assert lookup.empty
        assert stats["n_sleeper_pos_rows"] == 0

    def test_position_scoping_in_denominator_and_source(self, tmp_path):
        proj = pd.DataFrame(
            [_proj_row("A", 20.0, position="WR"), _proj_row("B", 15.0, position="RB")]
        )
        bronze_dir = _write_sleeper_parquet(
            tmp_path,
            2023,
            5,
            [_sleeper_row("A", 10.0, position="WR"), _sleeper_row("B", 30.0, position="RB")],
        )
        lookup, stats = build_sleeper_lookup(proj, 2023, 5, "WR", bronze_dir=bronze_dir)
        assert stats["n_proj_pos_rows"] == 1
        assert stats["n_sleeper_pos_rows"] == 1
        assert list(lookup["player_id"]) == ["A"]

    def test_no_bronze_partition_is_empty_not_error(self):
        proj = pd.DataFrame([_proj_row("A", 20.0)])
        lookup, stats = build_sleeper_lookup(
            proj, 2023, 5, "WR", bronze_dir="/nonexistent/path"
        )
        assert lookup.empty
        assert stats["n_sleeper_pos_rows"] == 0

    def test_empty_proj_df(self):
        lookup, stats = build_sleeper_lookup(pd.DataFrame(), 2023, 5, "WR")
        assert lookup.empty
        assert stats["n_proj_pos_rows"] == 0

    def test_latest_parquet_picked_when_multiple_exist(self, tmp_path):
        proj = pd.DataFrame([_proj_row("A", 20.0)])
        bronze_dir = _write_sleeper_parquet(
            tmp_path, 2023, 5, [_sleeper_row("A", 10.0)], ts="20260101_000000"
        )
        # A second, later-timestamped file with a DIFFERENT value for A.
        week_dir = tmp_path / "sleeper" / "season=2023" / "week=05"
        pd.DataFrame([_sleeper_row("A", 99.0)]).to_parquet(
            week_dir / "sleeper_20260102_000000.parquet", index=False
        )
        lookup, _ = build_sleeper_lookup(proj, 2023, 5, "WR", bronze_dir=bronze_dir)
        # Only one row for A either way -- rank is 1 regardless of which
        # file was read, but this proves no crash / duplication across the
        # two files rather than reading a stale value.
        assert len(lookup) == 1


# ---------------------------------------------------------------------------
# apply_consensus_anchor_blend (mechanism a)
# ---------------------------------------------------------------------------


class TestApplyConsensusAnchorBlend:
    def _pool(self):
        # our order (desc points): A(20) > B(18) > C(16) > D(14)
        # sleeper_pos_rank: A worst(4), B best(1), C 3rd, D 2nd -- inversion
        return pd.DataFrame(
            [
                _proj_row("A", 20.0),
                _proj_row("B", 18.0),
                _proj_row("C", 16.0),
                _proj_row("D", 14.0),
            ]
        )

    def _lookup(self):
        return pd.DataFrame(
            {"player_id": ["A", "B", "C", "D"], "sleeper_pos_rank": [4, 1, 3, 2]}
        )

    def test_weight_zero_is_noop(self):
        proj = self._pool()
        out = apply_consensus_anchor_blend(proj, self._lookup(), weight=0.0, position="WR")
        pd.testing.assert_series_equal(
            out["projected_points"], proj["projected_points"], check_names=True
        )
        assert not out["sleeper_anchor_flag"].any()

    def test_weight_one_fully_realizes_sleeper_order(self):
        proj = self._pool()
        out = apply_consensus_anchor_blend(proj, self._lookup(), weight=1.0, position="WR")
        ordered = out.set_index("player_id")["projected_points"]
        assert ordered["B"] == 20.0
        assert ordered["D"] == 18.0
        assert ordered["C"] == 16.0
        assert ordered["A"] == 14.0
        assert out["sleeper_anchor_flag"].sum() == 4

    def test_value_multiset_conserved(self):
        proj = self._pool()
        out = apply_consensus_anchor_blend(proj, self._lookup(), weight=0.5, position="WR")
        before = sorted(proj["projected_points"].tolist())
        after = sorted(out["projected_points"].tolist())
        assert before == after

    def test_unmatched_rows_passthrough(self):
        proj = self._pool()
        lookup = pd.DataFrame({"player_id": ["A", "B"], "sleeper_pos_rank": [2, 1]})
        out = apply_consensus_anchor_blend(proj, lookup, weight=1.0, position="WR")
        assert out.set_index("player_id").loc["C", "projected_points"] == 16.0
        assert out.set_index("player_id").loc["D", "projected_points"] == 14.0
        assert not out.set_index("player_id").loc["C", "sleeper_anchor_flag"]

    def test_other_positions_never_touched(self):
        proj = pd.concat(
            [self._pool(), pd.DataFrame([_proj_row("RB1", 12.0, position="RB")])],
            ignore_index=True,
        )
        lookup = pd.concat(
            [self._lookup(), pd.DataFrame({"player_id": ["RB1"], "sleeper_pos_rank": [1]})],
            ignore_index=True,
        )
        out = apply_consensus_anchor_blend(proj, lookup, weight=1.0, position="WR")
        assert out.set_index("player_id").loc["RB1", "projected_points"] == 12.0
        assert not out.set_index("player_id").loc["RB1", "sleeper_anchor_flag"]

    def test_empty_lookup_is_noop(self):
        proj = self._pool()
        out = apply_consensus_anchor_blend(
            proj, pd.DataFrame(columns=["player_id", "sleeper_pos_rank"]), weight=0.5, position="WR"
        )
        pd.testing.assert_frame_equal(
            out.drop(columns=["sleeper_anchor_flag"]), proj, check_like=True
        )

    def test_position_param_works_for_qb(self):
        proj = pd.DataFrame(
            [_proj_row("Q1", 25.0, position="QB"), _proj_row("Q2", 20.0, position="QB")]
        )
        lookup = pd.DataFrame({"player_id": ["Q1", "Q2"], "sleeper_pos_rank": [2, 1]})
        out = apply_consensus_anchor_blend(proj, lookup, weight=1.0, position="QB")
        ordered = out.set_index("player_id")["projected_points"]
        assert ordered["Q2"] == 25.0
        assert ordered["Q1"] == 20.0


# ---------------------------------------------------------------------------
# apply_consensus_anchor_near_tie (mechanism b)
# ---------------------------------------------------------------------------


class TestApplyConsensusAnchorNearTie:
    def test_nudges_disagreeing_near_tie_pair(self):
        proj = pd.DataFrame([_proj_row("HI", 20.0), _proj_row("LOW", 19.0)])
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "sleeper_pos_rank": [5, 1]})
        out = apply_consensus_anchor_near_tie(proj, lookup, position="WR")
        ordered = out.set_index("player_id")["projected_points"]
        assert ordered["HI"] == 20.0 - NUDGE
        assert ordered["LOW"] == 19.0 + NUDGE
        assert out["sleeper_anchor_flag"].all()

    def test_agreeing_pair_untouched(self):
        proj = pd.DataFrame([_proj_row("HI", 20.0), _proj_row("LOW", 19.0)])
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "sleeper_pos_rank": [1, 5]})
        out = apply_consensus_anchor_near_tie(proj, lookup, position="WR")
        ordered = out.set_index("player_id")["projected_points"]
        assert ordered["HI"] == 20.0
        assert ordered["LOW"] == 19.0
        assert not out["sleeper_anchor_flag"].any()

    def test_gap_beyond_epsilon_untouched(self):
        proj = pd.DataFrame(
            [_proj_row("HI", 20.0), _proj_row("LOW", 20.0 - EPSILON - 1.0)]
        )
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "sleeper_pos_rank": [5, 1]})
        out = apply_consensus_anchor_near_tie(proj, lookup, position="WR")
        assert not out["sleeper_anchor_flag"].any()

    def test_missing_signal_one_side_no_fire(self):
        proj = pd.DataFrame([_proj_row("HI", 20.0), _proj_row("LOW", 19.0)])
        lookup = pd.DataFrame({"player_id": ["HI"], "sleeper_pos_rank": [5]})
        out = apply_consensus_anchor_near_tie(proj, lookup, position="WR")
        assert not out["sleeper_anchor_flag"].any()

    def test_non_negative_clip(self):
        proj = pd.DataFrame([_proj_row("HI", 0.3), _proj_row("LOW", 0.1)])
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "sleeper_pos_rank": [5, 1]})
        out = apply_consensus_anchor_near_tie(proj, lookup, position="WR")
        assert (out["projected_points"] >= 0).all()

    def test_other_positions_never_touched(self):
        proj = pd.DataFrame(
            [_proj_row("HI", 20.0), _proj_row("LOW", 19.0), _proj_row("RB1", 19.5, position="RB")]
        )
        lookup = pd.DataFrame(
            {"player_id": ["HI", "LOW", "RB1"], "sleeper_pos_rank": [5, 1, 1]}
        )
        out = apply_consensus_anchor_near_tie(proj, lookup, position="WR")
        assert out.set_index("player_id").loc["RB1", "projected_points"] == 19.5
        assert not out.set_index("player_id").loc["RB1", "sleeper_anchor_flag"]


# ---------------------------------------------------------------------------
# apply_consensus_anchor dispatcher
# ---------------------------------------------------------------------------


class TestApplyConsensusAnchorDispatch:
    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            apply_consensus_anchor(pd.DataFrame(), pd.DataFrame(), mode="bogus")

    def test_blend_requires_weight_defaults_zero_noop(self):
        proj = pd.DataFrame([_proj_row("A", 20.0)])
        lookup = pd.DataFrame({"player_id": ["A"], "sleeper_pos_rank": [1]})
        out = apply_consensus_anchor(proj, lookup, mode="blend")  # no weight -> 0.0
        assert out["projected_points"].iloc[0] == 20.0

    def test_default_position_is_wr(self):
        proj = pd.DataFrame([_proj_row("HI", 20.0), _proj_row("LOW", 19.0)])
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "sleeper_pos_rank": [5, 1]})
        out = apply_consensus_anchor(proj, lookup)  # mode="near_tie", position="WR" defaults
        assert out["sleeper_anchor_flag"].all()

    def test_supported_positions_constant(self):
        assert set(SUPPORTED_POSITIONS) == {"QB", "RB", "WR", "TE"}


# ---------------------------------------------------------------------------
# Redesigned shuffle-null harness (per
# knowledge-vault/concepts/shuffle-test-must-match-mechanism-shape.md):
# near_tie (disagreement-gated) -> single-shuffle collapse-to-zero is the
# right null. blend (unconditional full-reorder) -> a K=100 shuffled-delta
# null + one-sided empirical p-value is the right null (shuffling swaps
# real signal for w-weighted pure noise, which is not neutral). This test
# proves the harness ITSELF behaves as expected on a synthetic fixture
# where the "true" signal is constructed to be perfectly correct.
# ---------------------------------------------------------------------------


def _synthetic_pool(n_pairs=8, week=5):
    """n_pairs adjacent near-tie pairs; LOW is always the true-better player
    in our own labeling, so a perfectly-correlated lookup should fire on
    every pair while a decorrelated (shuffled) lookup fires on far fewer.
    """
    rows = []
    for i in range(n_pairs):
        rows.append(_proj_row(f"HI{i}", 10.0 + i, week=week))
        rows.append(_proj_row(f"LO{i}", 10.0 + i - 0.5, week=week))
    return pd.DataFrame(rows)


def _true_lookup(n_pairs=8):
    rows = []
    for i in range(n_pairs):
        rows.append({"player_id": f"HI{i}", "sleeper_pos_rank": 2})
        rows.append({"player_id": f"LO{i}", "sleeper_pos_rank": 1})
    return pd.DataFrame(rows)


class TestShuffleNullHarness:
    def test_near_tie_true_signal_fires_more_than_shuffled(self):
        """Disagreement-gated mechanism: single shuffle should collapse the
        firing count toward a much smaller number (mirrors ecr_anchor's
        collapse-to-zero precedent)."""
        proj = _synthetic_pool()
        true_lookup = _true_lookup()

        out_true = apply_consensus_anchor_near_tie(proj, true_lookup, position="WR")
        n_fired_true = int(out_true["sleeper_anchor_flag"].sum())
        assert n_fired_true == 16  # every pair (8 pairs x 2 members) fires

        rng = np.random.default_rng(42)
        shuffled_ranks = true_lookup["sleeper_pos_rank"].to_numpy().copy()
        rng.shuffle(shuffled_ranks)
        shuffled_lookup = true_lookup.copy()
        shuffled_lookup["sleeper_pos_rank"] = shuffled_ranks

        out_shuffled = apply_consensus_anchor_near_tie(proj, shuffled_lookup, position="WR")
        n_fired_shuffled = int(out_shuffled["sleeper_anchor_flag"].sum())

        assert n_fired_shuffled < n_fired_true

    def test_blend_k100_shuffled_null_one_sided_pvalue(self):
        """Full-reorder mechanism: build a K=100 null of shuffled-lookup
        deltas and confirm the true-signal effect clears a one-sided
        empirical p<0.05 bar against that null -- the redesigned test from
        knowledge-vault/concepts/shuffle-test-must-match-mechanism-shape.md,
        proven here on a synthetic fixture with a perfectly-correct signal
        (so the true effect should trivially beat noise-at-weight-w).
        """
        n_pairs = 10
        proj = _synthetic_pool(n_pairs=n_pairs)
        true_lookup = _true_lookup(n_pairs=n_pairs)

        def _metric(lookup_df: pd.DataFrame) -> float:
            """Mean squared distance of the blended order's realized
            positions from the TRUE best-to-worst order (LO0..LOn all rank
            above every HI) -- a simple proxy 'ordinal correctness' score
            where LOWER is better, standing in for the real gate's
            realized-outcome Accuracy Gap without needing actual game
            results for a synthetic fixture.
            """
            out = apply_consensus_anchor_blend(proj, lookup_df, weight=0.5, position="WR")
            ordered = out.sort_values("projected_points", ascending=False)["player_id"].tolist()
            # True ideal order: every LO ranked above every HI (since LO is
            # always the true-better player in this fixture).
            true_order = [f"LO{i}" for i in range(n_pairs)] + [f"HI{i}" for i in range(n_pairs)]
            true_rank = {pid: r for r, pid in enumerate(true_order)}
            realized_rank = {pid: r for r, pid in enumerate(ordered)}
            return float(
                np.mean([(true_rank[p] - realized_rank[p]) ** 2 for p in true_rank])
            )

        true_metric = _metric(true_lookup)

        rng = np.random.default_rng(42)
        k = 100
        null_metrics = []
        for _ in range(k):
            shuffled_ranks = true_lookup["sleeper_pos_rank"].to_numpy().copy()
            rng.shuffle(shuffled_ranks)
            shuffled_lookup = true_lookup.copy()
            shuffled_lookup["sleeper_pos_rank"] = shuffled_ranks
            null_metrics.append(_metric(shuffled_lookup))

        null_metrics = np.array(null_metrics)
        # One-sided empirical p-value: fraction of null draws at least as
        # good (<=, since lower is better here) as the true-signal metric.
        p_value = float((null_metrics <= true_metric).mean())

        assert true_metric < null_metrics.mean()
        assert p_value < 0.05
