"""Tests for the five weekly-board defects fixed 2026-10-23.

All five came out of `.planning/MODEL_ASSESSMENT_2026_10_21.md`, and two of
them were checks that could never pass — so these tests care as much about a
check *not* firing spuriously as about it firing when it should.

1. Sleeper anchor coverage was measured over every row of a position, which
   decays with Sleeper's shrinking slate and says nothing about health.
2. Bye-week rows carried projected points, contradicting the documented
   invariant.
3. `projection_source` records the route taken, never whether the residual
   correction actually applied.
4. The team-total coherence check compared summed fantasy points against an
   implied game score — different units, so it fired for every team, weekly.
5. The weekly star check compared consensus full names against our
   abbreviated board names, so it reported every star as missing.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from band_calibration import apply_calibrated_bands, fit_band_offsets  # noqa: E402
from hybrid_projection import (  # noqa: E402
    RESIDUAL_APPLIED_COL,
    _stamp_residual_applied,
)
from ml_projection_router import check_team_total_coherence  # noqa: E402
from projection_engine import _IMPLIED_TO_FANTASY_MULT  # noqa: E402
from sleeper_consensus_anchor import STARTABLE_PTS, build_sleeper_lookup  # noqa: E402

GENERATOR = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "generate_projections.py"
)


def _sleeper_parquet(tmp_path, season, week, rows):
    d = tmp_path / "sleeper" / f"season={season}" / f"week={week:02d}"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / "sleeper_20261023_000000.parquet", index=False)
    return str(tmp_path / "sleeper")


# ---------------------------------------------------------------------------
# 1. Anchor coverage measured over the startable pool
# ---------------------------------------------------------------------------


class TestStartableCoverage:
    def test_startable_cut_matches_the_consensus_population(self):
        from consensus_metrics import CONSENSUS_MIN_PTS

        assert STARTABLE_PTS == CONSENSUS_MIN_PTS

    def test_stats_separate_startable_from_deep_bench(self, tmp_path):
        """The defect in one assertion: raw coverage looks bad while startable
        coverage is perfect, because Sleeper only dropped bench players."""
        ours = pd.DataFrame(
            [
                {"player_id": "S1", "position": "WR", "projected_points": 14.0},
                {"player_id": "S2", "position": "WR", "projected_points": 9.0},
                {"player_id": "S3", "position": "WR", "projected_points": 6.0},
                {"player_id": "B1", "position": "WR", "projected_points": 2.0},
                {"player_id": "B2", "position": "WR", "projected_points": 1.0},
                {"player_id": "B3", "position": "WR", "projected_points": 0.5},
            ]
        )
        # Sleeper publishes only the three startables.
        bronze = _sleeper_parquet(
            tmp_path,
            2026,
            7,
            [
                {"player_id": p, "position": "WR", "projected_points": v}
                for p, v in [("S1", 13.0), ("S2", 8.0), ("S3", 7.0)]
            ],
        )
        _lookup, stats = build_sleeper_lookup(ours, 2026, 7, "WR", bronze_dir=bronze)

        assert stats["n_proj_pos_rows"] == 6
        assert stats["n_final_matched"] == 3  # raw coverage 50% — looks alarming
        assert stats["n_startable_pos_rows"] == 3
        assert stats["n_startable_matched"] == 3  # startable coverage 100%

    def test_a_missing_startable_shows_up(self, tmp_path):
        ours = pd.DataFrame(
            [
                {"player_id": "S1", "position": "RB", "projected_points": 14.0},
                {"player_id": "S2", "position": "RB", "projected_points": 11.0},
            ]
        )
        bronze = _sleeper_parquet(
            tmp_path,
            2026,
            7,
            [{"player_id": "S1", "position": "RB", "projected_points": 13.0}],
        )
        _lookup, stats = build_sleeper_lookup(ours, 2026, 7, "RB", bronze_dir=bronze)
        assert stats["n_startable_pos_rows"] == 2
        assert stats["n_startable_matched"] == 1

    def test_stats_keys_exist_even_on_the_empty_path(self, tmp_path):
        _lookup, stats = build_sleeper_lookup(
            pd.DataFrame(), 2026, 7, "WR", bronze_dir=str(tmp_path)
        )
        for key in ("n_startable_pos_rows", "n_startable_matched"):
            assert key in stats

    def test_generator_guards_on_startable_coverage(self):
        src = open(GENERATOR, encoding="utf-8").read()
        assert "STARTABLE_COVERAGE_MIN" in src
        assert "n_startable_pos_rows" in src
        # and the floor is a meaningful one, not the old 50% catch-all
        assert "STARTABLE_COVERAGE_MIN: float = 0.90" in src


# ---------------------------------------------------------------------------
# 2. Bye-week rows must carry no points
# ---------------------------------------------------------------------------


class TestByeInvariant:
    def test_generator_reasserts_the_bye_invariant(self):
        src = open(GENERATOR, encoding="utf-8").read()
        assert "# --- Bye" in src or "Bye invariant" in src
        assert 'on_bye = projections["is_bye_week"]' in src

    def test_bye_zeroing_runs_after_every_blend_that_can_revive_it(self):
        """Ordering is the whole point: the anchors and the shrink re-derive
        projected_points, so the invariant must come after them."""
        src = open(GENERATOR, encoding="utf-8").read()
        anchor = src.index("projections, sleeper_stats = apply_sleeper_anchors(")
        shrink = src.index("projections, shrink_stats = apply_dispersion_shrink(")
        bye = src.index('on_bye = projections["is_bye_week"]')
        assert anchor < bye and shrink < bye

    def test_bye_zeroing_covers_the_band_not_just_the_points(self):
        src = open(GENERATOR, encoding="utf-8").read()
        block = src[src.index('on_bye = projections["is_bye_week"]') :][:1200]
        assert "projected_floor" in block and "projected_ceiling" in block


# ---------------------------------------------------------------------------
# 3. Residual-correction provenance
# ---------------------------------------------------------------------------


class TestResidualProvenance:
    def test_stamp_marks_applied(self):
        df = pd.DataFrame({"projected_points": [1.0, 2.0]})
        out = _stamp_residual_applied(df, True)
        assert out[RESIDUAL_APPLIED_COL].all()

    def test_stamp_marks_not_applied(self):
        df = pd.DataFrame({"projected_points": [1.0, 2.0]})
        out = _stamp_residual_applied(df, False)
        assert not out[RESIDUAL_APPLIED_COL].any()

    def test_stamp_does_not_mutate_the_caller(self):
        """The fallback paths hand back the caller's own heuristic frame, so
        stamping must copy."""
        df = pd.DataFrame({"projected_points": [1.0]})
        _stamp_residual_applied(df, False)
        assert RESIDUAL_APPLIED_COL not in df.columns

    def test_both_fallback_returns_are_stamped(self):
        """Neither early return may hand back an unstamped frame, or the board
        cannot distinguish 'corrected' from 'fell back'."""
        src = open(
            os.path.join(
                os.path.dirname(__file__), "..", "src", "hybrid_projection.py"
            ),
            encoding="utf-8",
        ).read()
        assert src.count("_stamp_residual_applied(heuristic_projections, False)") == 2
        assert "_stamp_residual_applied(result, True)" in src


# ---------------------------------------------------------------------------
# 4. Team-total coherence must compare like units
# ---------------------------------------------------------------------------


class TestTeamTotalCoherence:
    def _projections(self, team="DET", total=70.0):
        return pd.DataFrame(
            {
                "recent_team": [team] * 4,
                "position": ["QB", "RB", "WR", "TE"],
                "projected_points": [total / 4] * 4,
            }
        )

    def test_a_normal_team_no_longer_warns(self):
        """70 fantasy pts off a 22-pt implied total is ordinary (22 * 3.36 =
        73.9 budget). The old check compared 70 against 22 and fired for every
        team, every week."""
        warns = check_team_total_coherence(
            self._projections(total=70.0), {"DET": 22.0}, scoring_format="half_ppr"
        )
        assert warns == []

    def test_a_genuinely_inflated_team_still_warns(self):
        warns = check_team_total_coherence(
            self._projections(total=140.0), {"DET": 22.0}, scoring_format="half_ppr"
        )
        assert len(warns) == 1
        assert "fantasy budget" in warns[0]

    def test_threshold_is_applied_to_the_converted_budget(self):
        implied = 20.0
        mult = _IMPLIED_TO_FANTASY_MULT["half_ppr"]
        budget = implied * mult
        # just inside 110% of budget -> no warning
        assert (
            check_team_total_coherence(
                self._projections(total=budget * 1.05),
                {"DET": implied},
                scoring_format="half_ppr",
            )
            == []
        )
        # just outside -> warning
        assert (
            len(
                check_team_total_coherence(
                    self._projections(total=budget * 1.15),
                    {"DET": implied},
                    scoring_format="half_ppr",
                )
            )
            == 1
        )

    def test_scoring_format_changes_the_budget(self):
        """PPR generates more fantasy points off the same game script."""
        assert (
            _IMPLIED_TO_FANTASY_MULT["ppr"]
            > _IMPLIED_TO_FANTASY_MULT["half_ppr"]
            > _IMPLIED_TO_FANTASY_MULT["standard"]
        )
        total = 20.0 * _IMPLIED_TO_FANTASY_MULT["ppr"] * 1.05
        assert (
            check_team_total_coherence(
                self._projections(total=total), {"DET": 20.0}, scoring_format="ppr"
            )
            == []
        )
        # the same total is over budget under standard scoring
        assert (
            len(
                check_team_total_coherence(
                    self._projections(total=total),
                    {"DET": 20.0},
                    scoring_format="standard",
                )
            )
            == 1
        )

    def test_unknown_scoring_format_falls_back_to_half_ppr(self):
        warns = check_team_total_coherence(
            self._projections(total=70.0), {"DET": 22.0}, scoring_format="nonsense"
        )
        assert warns == []

    def test_no_implied_totals_is_a_no_op(self):
        assert check_team_total_coherence(self._projections(), None) == []


# ---------------------------------------------------------------------------
# 5. The weekly star check must match abbreviated names
# ---------------------------------------------------------------------------


class TestAbbreviatedNameMatching:
    def test_abbrev_key_collapses_both_spellings(self):
        from sanity_check_projections import _abbrev_key

        assert _abbrev_key("Drake Maye") == _abbrev_key("D.Maye")
        assert _abbrev_key("Lamar Jackson") == _abbrev_key("L.Jackson")
        assert _abbrev_key("Puka Nacua") == _abbrev_key("P.Nacua")

    def test_abbrev_key_keeps_distinct_players_distinct(self):
        from sanity_check_projections import _abbrev_key

        assert _abbrev_key("D.Maye") != _abbrev_key("D.Moore")
        assert _abbrev_key("Jayden Daniels") != _abbrev_key("Lamar Jackson")

    def test_abbrev_key_is_empty_when_no_key_can_be_built(self):
        """Must not collapse to a value that matches everything."""
        from sanity_check_projections import _abbrev_key

        assert _abbrev_key("") == ""
        assert _abbrev_key("Cher") == ""

    def test_suffixes_do_not_break_the_key(self):
        from sanity_check_projections import _abbrev_key

        assert _abbrev_key("Kenneth Walker III") == _abbrev_key("K.Walker")

    def test_star_check_uses_the_fallback(self):
        src = open(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "scripts",
                "sanity_check_projections.py",
            ),
            encoding="utf-8",
        ).read()
        assert '_abbrev"] = our_pos["player_name"].apply(_abbrev_key)' in src


# ---------------------------------------------------------------------------
# Zero-point rows carry no band
# ---------------------------------------------------------------------------


class TestZeroPointBandInvariant:
    def test_zero_point_rows_get_a_zero_band(self):
        """The anchor's rank reassignment can hand a live player a 0-point
        value while its band is left behind (2026 w7: K.Nwangwu 0.0 pts with a
        0.65-1.53 band)."""
        rng = np.random.default_rng(7)
        hist = pd.DataFrame(
            {
                "position": "WR",
                "projected_points": rng.uniform(1, 20, 300),
                "actual_points": rng.uniform(0, 25, 300),
            }
        )
        off = fit_band_offsets(hist)
        board = pd.DataFrame(
            {
                "player_id": ["a", "b", "c"],
                "position": ["WR"] * 3,
                "projected_points": [12.0, 0.0, 0.0],
                "projected_floor": [7.0, 0.65, 0.31],
                "projected_ceiling": [17.0, 1.53, 0.69],
            }
        )
        out, _ = apply_calibrated_bands(board, off)
        zeroed = out[out.projected_points <= 0]
        assert (zeroed.projected_floor == 0).all()
        assert (zeroed.projected_ceiling == 0).all()
        assert (out.projected_floor <= out.projected_points + 1e-6).all()
        assert (out.projected_points <= out.projected_ceiling + 1e-6).all()

    def test_live_rows_are_unaffected_by_the_zero_pass(self):
        rng = np.random.default_rng(8)
        hist = pd.DataFrame(
            {
                "position": "WR",
                "projected_points": rng.uniform(1, 20, 300),
                "actual_points": rng.uniform(0, 25, 300),
            }
        )
        off = fit_band_offsets(hist)
        board = pd.DataFrame(
            {
                "player_id": ["a"],
                "position": ["WR"],
                "projected_points": [12.0],
                "projected_floor": [7.0],
                "projected_ceiling": [17.0],
            }
        )
        out, stats = apply_calibrated_bands(board, off)
        assert out.loc[0, "projected_floor"] > 0
        assert stats and stats[0]["n_rows"] == 1
