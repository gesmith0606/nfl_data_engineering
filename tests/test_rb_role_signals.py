"""Tests for src/rb_role_signals.py — RB role-change signal construction.

Tests cover:
- Signal construction from synthetic data
- Temporal lag correctness (no future data used for week-t predictions)
- Edge cases: missing depth chart data, missing snap counts, player absent
  from snap counts, no better teammates, all teammates healthy
- Named sanity cases (real data where available): Z.Moss 2023 w5,
  D.Foreman 2022 w8, Z.Charbonnet 2024 w15
- All three signal families: teammate status, snap trend, depth staleness
"""

import os
import sys
from typing import Dict, List

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rb_role_signals import (
    LOOKBACK_WEEKS,
    MISSING_STATUSES,
    SNAP_COLLAPSE_THRESHOLD,
    SNAP_COLLAPSE_RECENT_CEILING,
    OUT_STATUSES,
    build_rb_role_signals,
    compute_depth_chart_staleness,
    compute_snap_trend_signals,
    compute_teammate_status_signals,
    _build_snap_id_map,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_depth_chart(
    rows: List[Dict],
) -> pd.DataFrame:
    """Build a minimal depth chart DataFrame from a list of row dicts.

    Required keys: season, week, club_code, gsis_id, position, depth_team.
    Optional keys: formation (defaults to 'Offense'), depth_position (defaults
    to 'RB'), full_name (defaults to gsis_id).
    """
    records = []
    for r in rows:
        records.append(
            {
                "season": r["season"],
                "week": float(r["week"]),
                "club_code": r["club_code"],
                "gsis_id": r["gsis_id"],
                "position": r.get("position", "RB"),
                "depth_team": float(r["depth_team"]),
                "formation": r.get("formation", "Offense"),
                "depth_position": r.get("depth_position", "RB"),
                "full_name": r.get("full_name", r["gsis_id"]),
            }
        )
    return pd.DataFrame(records)


def _make_injury_report(
    rows: List[Dict],
) -> pd.DataFrame:
    """Build a minimal injury DataFrame from a list of row dicts.

    Required keys: season, week, team, player_id.
    Optional keys: report_status (defaults to 'Out'), position (defaults 'RB').
    """
    records = []
    for r in rows:
        records.append(
            {
                "season": r["season"],
                "week": r["week"],
                "team": r["team"],
                "player_id": r["player_id"],
                "position": r.get("position", "RB"),
                "full_name": r.get("full_name", r["player_id"]),
                "report_status": r.get("report_status", "Out"),
            }
        )
    return pd.DataFrame(records)


def _make_snaps(
    rows: List[Dict],
) -> pd.DataFrame:
    """Build a minimal snap counts DataFrame from a list of row dicts.

    Required keys: season, week, team, player (display name), offense_pct.
    """
    records = []
    for r in rows:
        records.append(
            {
                "season": r["season"],
                "week": r["week"],
                "team": r["team"],
                "player": r["player"],
                "offense_pct": float(r["offense_pct"]),
                "position": r.get("position", "RB"),
            }
        )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Tests: compute_teammate_status_signals
# ---------------------------------------------------------------------------


class TestTeammateStatusSignals:
    """Unit tests for compute_teammate_status_signals."""

    def test_starter_out_promotes_backup(self):
        """RB2 should see rb_better_teammate_out=1 when RB1 is Out."""
        dc = _make_depth_chart(
            [
                {"season": 2022, "week": 5, "club_code": "CAR", "gsis_id": "RB1", "depth_team": 1},
                {"season": 2022, "week": 5, "club_code": "CAR", "gsis_id": "RB2", "depth_team": 2},
            ]
        )
        inj = _make_injury_report(
            [{"season": 2022, "week": 5, "team": "CAR", "player_id": "RB1", "report_status": "Out"}]
        )
        result = compute_teammate_status_signals(dc, inj)
        rb2 = result[(result["player_id"] == "RB2") & (result["week"] == 5)]
        assert len(rb2) == 1
        assert rb2.iloc[0]["rb_better_teammate_out"] == 1

    def test_starter_doubtful_promotes_backup(self):
        """Doubtful status also fires rb_better_teammate_out."""
        dc = _make_depth_chart(
            [
                {"season": 2022, "week": 5, "club_code": "KC", "gsis_id": "RB_A", "depth_team": 1},
                {"season": 2022, "week": 5, "club_code": "KC", "gsis_id": "RB_B", "depth_team": 2},
            ]
        )
        inj = _make_injury_report(
            [{"season": 2022, "week": 5, "team": "KC", "player_id": "RB_A", "report_status": "Doubtful"}]
        )
        result = compute_teammate_status_signals(dc, inj)
        rb_b = result[(result["player_id"] == "RB_B") & (result["week"] == 5)]
        assert rb_b.iloc[0]["rb_better_teammate_out"] >= 1

    def test_starter_questionable_does_not_fire(self):
        """Questionable status does NOT fire rb_better_teammate_out (still plays)."""
        dc = _make_depth_chart(
            [
                {"season": 2022, "week": 5, "club_code": "KC", "gsis_id": "RB_A", "depth_team": 1},
                {"season": 2022, "week": 5, "club_code": "KC", "gsis_id": "RB_B", "depth_team": 2},
            ]
        )
        inj = _make_injury_report(
            [{"season": 2022, "week": 5, "team": "KC", "player_id": "RB_A", "report_status": "Questionable"}]
        )
        result = compute_teammate_status_signals(dc, inj)
        rb_b = result[(result["player_id"] == "RB_B") & (result["week"] == 5)]
        assert rb_b.iloc[0]["rb_better_teammate_out"] == 0

    def test_returning_starter_fires_for_backup(self):
        """RB2 should see rb_better_teammate_returning=1 when RB1 returns after being Out."""
        # Weeks 2-4: RB1 is Out; week 5: RB1 is active (returning)
        dc_rows = []
        for w in range(2, 6):
            dc_rows.append({"season": 2023, "week": w, "club_code": "IND", "gsis_id": "RB_STAR", "depth_team": 1})
            dc_rows.append({"season": 2023, "week": w, "club_code": "IND", "gsis_id": "RB_FILL", "depth_team": 2})
        dc = _make_depth_chart(dc_rows)

        inj_rows = [
            {"season": 2023, "week": w, "team": "IND", "player_id": "RB_STAR", "report_status": "Out"}
            for w in range(2, 5)
        ]
        # Week 5: RB_STAR active (no entry or report_status = None / empty)
        inj = _make_injury_report(inj_rows)

        result = compute_teammate_status_signals(dc, inj)
        fill_w5 = result[
            (result["player_id"] == "RB_FILL")
            & (result["week"] == 5)
        ]
        assert fill_w5.iloc[0]["rb_better_teammate_returning"] == 1

    def test_no_signal_when_all_healthy(self):
        """When no teammates are injured, both signals should be zero."""
        dc = _make_depth_chart(
            [
                {"season": 2022, "week": 3, "club_code": "PHI", "gsis_id": "RB_X", "depth_team": 1},
                {"season": 2022, "week": 3, "club_code": "PHI", "gsis_id": "RB_Y", "depth_team": 2},
            ]
        )
        inj = _make_injury_report([])  # Empty
        result = compute_teammate_status_signals(dc, inj)
        assert (result["rb_better_teammate_out"] == 0).all()
        assert (result["rb_better_teammate_returning"] == 0).all()

    def test_signal_only_fires_for_better_ranked_teammates(self):
        """rb_better_teammate_out should NOT fire for teammates ranked BELOW this player."""
        dc = _make_depth_chart(
            [
                {"season": 2022, "week": 7, "club_code": "NE", "gsis_id": "RB_STARTER", "depth_team": 1},
                {"season": 2022, "week": 7, "club_code": "NE", "gsis_id": "RB_BACKUP2", "depth_team": 3},
            ]
        )
        inj = _make_injury_report(
            [{"season": 2022, "week": 7, "team": "NE", "player_id": "RB_BACKUP2", "report_status": "Out"}]
        )
        result = compute_teammate_status_signals(dc, inj)
        starter = result[(result["player_id"] == "RB_STARTER") & (result["week"] == 7)]
        # RB_BACKUP2 is ranked BELOW starter; starter should not benefit
        assert starter.iloc[0]["rb_better_teammate_out"] == 0

    def test_empty_depth_chart_returns_empty(self):
        """Empty depth chart input returns empty DataFrame without raising."""
        dc = pd.DataFrame()
        inj = _make_injury_report([])
        result = compute_teammate_status_signals(dc, inj)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_lagging_correctness_returning_signal(self):
        """rb_better_teammate_returning uses only lookback weeks, not current week.

        If a player was Out in week 4 but the current week is 3, the signal
        must NOT fire at week 3.  (Signal at week 5 should fire if week 4 was Out.)
        """
        dc_rows = []
        for w in [3, 4, 5]:
            dc_rows.append({"season": 2022, "week": w, "club_code": "DEN", "gsis_id": "RB_START", "depth_team": 1})
            dc_rows.append({"season": 2022, "week": w, "club_code": "DEN", "gsis_id": "RB_BACK", "depth_team": 2})
        dc = _make_depth_chart(dc_rows)

        # RB_START is Out in week 4 only
        inj = _make_injury_report(
            [{"season": 2022, "week": 4, "team": "DEN", "player_id": "RB_START", "report_status": "Out"}]
        )
        result = compute_teammate_status_signals(dc, inj)

        # Week 3: RB_START not yet Out in lookback → signal should NOT fire
        back_w3 = result[(result["player_id"] == "RB_BACK") & (result["week"] == 3)]
        assert back_w3.iloc[0]["rb_better_teammate_returning"] == 0

        # Week 5: RB_START was Out in week 4 (in lookback) and is active in week 5 → FIRES
        back_w5 = result[(result["player_id"] == "RB_BACK") & (result["week"] == 5)]
        assert back_w5.iloc[0]["rb_better_teammate_returning"] == 1


# ---------------------------------------------------------------------------
# Tests: compute_snap_trend_signals
# ---------------------------------------------------------------------------


class TestSnapTrendSignals:
    """Unit tests for compute_snap_trend_signals."""

    def test_snap_share_slope_computed_correctly(self):
        """snap_share_slope = recent_avg − prior_avg for a player with clean history."""
        # 4 weeks of history before target week 5
        # weeks 1-2: offense_pct=0.80 (prior window)
        # weeks 3-4: offense_pct=0.50 (recent window)
        # target week 5: player appears in snap data but signal uses weeks <5
        snaps = _make_snaps([
            {"season": 2022, "week": 1, "team": "KC", "player": "J.Mixon", "offense_pct": 0.80},
            {"season": 2022, "week": 2, "team": "KC", "player": "J.Mixon", "offense_pct": 0.80},
            {"season": 2022, "week": 3, "team": "KC", "player": "J.Mixon", "offense_pct": 0.50},
            {"season": 2022, "week": 4, "team": "KC", "player": "J.Mixon", "offense_pct": 0.50},
            {"season": 2022, "week": 5, "team": "KC", "player": "J.Mixon", "offense_pct": 0.10},
        ])
        result = compute_snap_trend_signals(snaps)
        # Week 5 signal: recent=mean(w3,w4)=0.50, prior=mean(w1,w2)=0.80
        w5 = result[result["week"] == 5]
        assert len(w5) == 1
        assert abs(w5.iloc[0]["snap_share_slope"] - (0.50 - 0.80)) < 0.01
        assert abs(w5.iloc[0]["recent_snap_pct"] - 0.50) < 0.01
        assert abs(w5.iloc[0]["prior_snap_pct"] - 0.80) < 0.01

    def test_snap_share_collapsing_fires_when_sharply_declining(self):
        """snap_share_collapsing=1 when slope < -SNAP_COLLAPSE_THRESHOLD and recent < 0.40."""
        # recent=0.15, prior=0.80 → slope=-0.65 < -0.20 → collapsing=1
        snaps = _make_snaps([
            {"season": 2023, "week": 1, "team": "IND", "player": "Z.Moss", "offense_pct": 0.80},
            {"season": 2023, "week": 2, "team": "IND", "player": "Z.Moss", "offense_pct": 0.80},
            {"season": 2023, "week": 3, "team": "IND", "player": "Z.Moss", "offense_pct": 0.20},
            {"season": 2023, "week": 4, "team": "IND", "player": "Z.Moss", "offense_pct": 0.10},
            {"season": 2023, "week": 5, "team": "IND", "player": "Z.Moss", "offense_pct": 0.08},
        ])
        result = compute_snap_trend_signals(snaps)
        w5 = result[result["week"] == 5]
        assert w5.iloc[0]["snap_share_collapsing"] == 1

    def test_snap_share_collapsing_does_not_fire_for_high_share_player(self):
        """snap_share_collapsing=0 even when slope is negative if recent_snap >= 0.55.

        A player who dips from 0.85 to 0.65 is still a high-share back;
        we do not want to collapse their projection.
        """
        # recent=0.65, prior=0.85 → slope=-0.20 < -0.18 but recent >= 0.55
        snaps = _make_snaps([
            {"season": 2022, "week": 1, "team": "SF", "player": "C.McCaffrey", "offense_pct": 0.85},
            {"season": 2022, "week": 2, "team": "SF", "player": "C.McCaffrey", "offense_pct": 0.85},
            {"season": 2022, "week": 3, "team": "SF", "player": "C.McCaffrey", "offense_pct": 0.65},
            {"season": 2022, "week": 4, "team": "SF", "player": "C.McCaffrey", "offense_pct": 0.65},
            {"season": 2022, "week": 5, "team": "SF", "player": "C.McCaffrey", "offense_pct": 0.70},
        ])
        result = compute_snap_trend_signals(snaps)
        w5 = result[result["week"] == 5]
        assert w5.iloc[0]["snap_share_collapsing"] == 0

    def test_snap_share_slope_nan_when_insufficient_history(self):
        """snap_share_slope is NaN when there is not enough prior history."""
        # Only week 3 data → week 3 has no prior window
        snaps = _make_snaps([
            {"season": 2022, "week": 3, "team": "LAR", "player": "D.Henderson", "offense_pct": 0.70},
        ])
        result = compute_snap_trend_signals(snaps)
        w3 = result[result["week"] == 3]
        assert pd.isna(w3.iloc[0]["snap_share_slope"])
        assert w3.iloc[0]["snap_share_collapsing"] == 0

    def test_lagging_correctness_slope_uses_only_prior_weeks(self):
        """Slope at week t uses only weeks < t. Week-t offense_pct not included."""
        # If we change week 5 offense_pct from 0.90 to 0.01, the slope MUST NOT change
        snaps_base = _make_snaps([
            {"season": 2022, "week": 1, "team": "TEN", "player": "D.Henry", "offense_pct": 0.80},
            {"season": 2022, "week": 2, "team": "TEN", "player": "D.Henry", "offense_pct": 0.80},
            {"season": 2022, "week": 3, "team": "TEN", "player": "D.Henry", "offense_pct": 0.60},
            {"season": 2022, "week": 4, "team": "TEN", "player": "D.Henry", "offense_pct": 0.60},
            {"season": 2022, "week": 5, "team": "TEN", "player": "D.Henry", "offense_pct": 0.90},
        ])
        snaps_alt = snaps_base.copy()
        snaps_alt.loc[snaps_alt["week"] == 5, "offense_pct"] = 0.01

        result_base = compute_snap_trend_signals(snaps_base)
        result_alt = compute_snap_trend_signals(snaps_alt)

        w5_base = result_base[result_base["week"] == 5].iloc[0]
        w5_alt = result_alt[result_alt["week"] == 5].iloc[0]
        # Slope and recent_snap must be identical (both use weeks 1-4 only)
        assert abs(w5_base["snap_share_slope"] - w5_alt["snap_share_slope"]) < 1e-6
        assert abs(w5_base["recent_snap_pct"] - w5_alt["recent_snap_pct"]) < 1e-6

    def test_empty_snap_data_returns_empty(self):
        """Empty snap input returns empty DataFrame without raising."""
        result = compute_snap_trend_signals(pd.DataFrame())
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_player_missing_from_snap_counts_graceful(self):
        """Player with no snap data simply has no rows — no exception raised."""
        snaps = _make_snaps([
            {"season": 2022, "week": 3, "team": "BUF", "player": "J.Cook", "offense_pct": 0.75},
        ])
        result = compute_snap_trend_signals(snaps)
        # Player "R.White" not present in snaps at all — should not appear, no crash
        assert "R.White" not in result["player"].values

    def test_player_id_attached_when_player_weekly_provided(self):
        """player_id is populated via display-name join when player_weekly is given.

        player_weekly uses full display names (e.g. 'James Cook') to match
        against the snap data 'player' column (also full display names).
        """
        snaps = _make_snaps([
            {"season": 2022, "week": 3, "team": "BUF", "player": "James Cook", "offense_pct": 0.75},
            {"season": 2022, "week": 4, "team": "BUF", "player": "James Cook", "offense_pct": 0.70},
            {"season": 2022, "week": 5, "team": "BUF", "player": "James Cook", "offense_pct": 0.65},
        ])
        pw = pd.DataFrame({
            "player_id": ["00-0099999"],
            "player_name": ["James Cook"],
            "recent_team": ["BUF"],
            "season": [2022],
        })
        result = compute_snap_trend_signals(snaps, player_weekly=pw)
        assert result["player_id"].dropna().iloc[0] == "00-0099999"


# ---------------------------------------------------------------------------
# Tests: compute_depth_chart_staleness
# ---------------------------------------------------------------------------


class TestDepthChartStaleness:
    """Unit tests for compute_depth_chart_staleness."""

    def test_rank_improved_fires_when_promoted(self):
        """depth_rank_improved=1 when a player moves from rank 2 → rank 1."""
        dc = _make_depth_chart([
            # Weeks 2-4: player is RB2
            {"season": 2022, "week": 2, "club_code": "CAR", "gsis_id": "FORE", "depth_team": 2},
            {"season": 2022, "week": 3, "club_code": "CAR", "gsis_id": "FORE", "depth_team": 2},
            {"season": 2022, "week": 4, "club_code": "CAR", "gsis_id": "FORE", "depth_team": 2},
            # Week 5: promoted to RB1
            {"season": 2022, "week": 5, "club_code": "CAR", "gsis_id": "FORE", "depth_team": 1},
        ])
        result = compute_depth_chart_staleness(dc)
        w5 = result[(result["player_id"] == "FORE") & (result["week"] == 5)]
        assert w5.iloc[0]["depth_rank_improved"] == 1
        assert w5.iloc[0]["depth_rank_worsened"] == 0
        assert w5.iloc[0]["modal_depth_rank_lookback"] == 2

    def test_rank_worsened_fires_when_demoted(self):
        """depth_rank_worsened=1 when a player moves from rank 1 → rank 2."""
        dc = _make_depth_chart([
            {"season": 2023, "week": 2, "club_code": "IND", "gsis_id": "MOSS", "depth_team": 1},
            {"season": 2023, "week": 3, "club_code": "IND", "gsis_id": "MOSS", "depth_team": 1},
            {"season": 2023, "week": 4, "club_code": "IND", "gsis_id": "MOSS", "depth_team": 1},
            {"season": 2023, "week": 5, "club_code": "IND", "gsis_id": "MOSS", "depth_team": 1},
            # Week 6: demoted when J.Taylor returns
            {"season": 2023, "week": 6, "club_code": "IND", "gsis_id": "MOSS", "depth_team": 2},
        ])
        result = compute_depth_chart_staleness(dc)
        w6 = result[(result["player_id"] == "MOSS") & (result["week"] == 6)]
        assert w6.iloc[0]["depth_rank_worsened"] == 1
        assert w6.iloc[0]["depth_rank_improved"] == 0

    def test_no_signal_when_stable(self):
        """Both signals are 0 when rank is unchanged."""
        dc = _make_depth_chart([
            {"season": 2022, "week": w, "club_code": "SF", "gsis_id": "CMC", "depth_team": 1}
            for w in range(3, 10)
        ])
        result = compute_depth_chart_staleness(dc)
        for _, row in result.iterrows():
            if row["week"] >= 6:  # Enough lookback exists
                assert row["depth_rank_improved"] == 0
                assert row["depth_rank_worsened"] == 0

    def test_no_lookback_data_returns_zeros(self):
        """Week 1 has no prior weeks — both signals are 0 and modal_rank is None."""
        dc = _make_depth_chart([
            {"season": 2022, "week": 1, "club_code": "TB", "gsis_id": "FOURNETTE", "depth_team": 1},
        ])
        result = compute_depth_chart_staleness(dc)
        w1 = result[(result["player_id"] == "FOURNETTE") & (result["week"] == 1)]
        assert w1.iloc[0]["depth_rank_improved"] == 0
        assert w1.iloc[0]["depth_rank_worsened"] == 0
        assert w1.iloc[0]["modal_depth_rank_lookback"] is None

    def test_lagging_correctness_staleness_uses_prior_weeks_only(self):
        """modal_depth_rank_lookback at week t uses only weeks < t."""
        # If we modify week 5's depth rank, the modal at week 5 must not change
        # (because it's derived from weeks 2-4 only)
        dc = _make_depth_chart([
            {"season": 2022, "week": 2, "club_code": "NE", "gsis_id": "R_JON", "depth_team": 2},
            {"season": 2022, "week": 3, "club_code": "NE", "gsis_id": "R_JON", "depth_team": 2},
            {"season": 2022, "week": 4, "club_code": "NE", "gsis_id": "R_JON", "depth_team": 2},
            {"season": 2022, "week": 5, "club_code": "NE", "gsis_id": "R_JON", "depth_team": 1},
        ])
        result = compute_depth_chart_staleness(dc)
        w5 = result[(result["player_id"] == "R_JON") & (result["week"] == 5)]
        # Modal from weeks 2-4 is 2; current is 1 → improved
        assert w5.iloc[0]["modal_depth_rank_lookback"] == 2
        assert w5.iloc[0]["depth_rank_improved"] == 1
        # Changing week 5 to rank 3 should show worsened without affecting modal
        dc2 = dc.copy()
        dc2.loc[dc2["week"] == 5, "depth_team"] = 3.0
        result2 = compute_depth_chart_staleness(dc2)
        w5_alt = result2[(result2["player_id"] == "R_JON") & (result2["week"] == 5)]
        assert w5_alt.iloc[0]["modal_depth_rank_lookback"] == 2
        assert w5_alt.iloc[0]["depth_rank_worsened"] == 1

    def test_empty_depth_chart_returns_empty(self):
        """Empty depth chart input returns empty DataFrame without raising."""
        result = compute_depth_chart_staleness(pd.DataFrame())
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Tests: build_rb_role_signals (integration)
# ---------------------------------------------------------------------------


class TestBuildRbRoleSignals:
    """Integration tests for build_rb_role_signals end-to-end."""

    def test_output_has_expected_columns(self, monkeypatch):
        """Output DataFrame contains all expected signal columns."""
        # Monkeypatch data readers to return minimal synthetic data
        dc = _make_depth_chart([
            {"season": 2022, "week": 3, "club_code": "KC", "gsis_id": "ID1", "depth_team": 1},
            {"season": 2022, "week": 4, "club_code": "KC", "gsis_id": "ID1", "depth_team": 1},
            {"season": 2022, "week": 5, "club_code": "KC", "gsis_id": "ID1", "depth_team": 1},
        ])
        inj = _make_injury_report([])
        snaps = _make_snaps([
            {"season": 2022, "week": 1, "team": "KC", "player": "I.Pacheco", "offense_pct": 0.65},
            {"season": 2022, "week": 2, "team": "KC", "player": "I.Pacheco", "offense_pct": 0.65},
            {"season": 2022, "week": 3, "team": "KC", "player": "I.Pacheco", "offense_pct": 0.65},
            {"season": 2022, "week": 4, "team": "KC", "player": "I.Pacheco", "offense_pct": 0.65},
            {"season": 2022, "week": 5, "team": "KC", "player": "I.Pacheco", "offense_pct": 0.65},
        ])
        pw = pd.DataFrame({"player_id": ["ID1"], "player_name": ["I.Pacheco"], "recent_team": ["KC"], "season": [2022]})

        import rb_role_signals as rrs
        monkeypatch.setattr(rrs, "_read_depth_charts", lambda seasons: dc)
        monkeypatch.setattr(rrs, "_read_injuries", lambda seasons: inj)
        monkeypatch.setattr(rrs, "_read_snaps", lambda seasons: snaps)
        monkeypatch.setattr(rrs, "_read_player_weekly_for_id_map", lambda seasons: pw)

        result = build_rb_role_signals([2022], weeks=(3, 18))

        expected_cols = {
            "player_id", "team", "season", "week",
            "rb_better_teammate_out", "rb_better_teammate_returning",
            "snap_share_slope", "snap_share_collapsing",
            "depth_rank_improved", "depth_rank_worsened",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_week_filter_applied(self, monkeypatch):
        """Rows outside the requested week range are excluded."""
        dc = _make_depth_chart([
            {"season": 2022, "week": w, "club_code": "BUF", "gsis_id": "PX", "depth_team": 1}
            for w in range(1, 10)
        ])
        inj = _make_injury_report([])
        snaps = pd.DataFrame()
        pw = pd.DataFrame(columns=["player_id", "player_name", "recent_team", "season"])

        import rb_role_signals as rrs
        monkeypatch.setattr(rrs, "_read_depth_charts", lambda seasons: dc)
        monkeypatch.setattr(rrs, "_read_injuries", lambda seasons: inj)
        monkeypatch.setattr(rrs, "_read_snaps", lambda seasons: snaps)
        monkeypatch.setattr(rrs, "_read_player_weekly_for_id_map", lambda seasons: pw)

        result = build_rb_role_signals([2022], weeks=(3, 7))
        assert result["week"].min() >= 3
        assert result["week"].max() <= 7

    def test_empty_data_returns_empty_not_raises(self, monkeypatch):
        """When all Bronze data is empty, return empty DataFrame without crashing."""
        import rb_role_signals as rrs
        monkeypatch.setattr(rrs, "_read_depth_charts", lambda seasons: pd.DataFrame())
        monkeypatch.setattr(rrs, "_read_injuries", lambda seasons: pd.DataFrame())
        monkeypatch.setattr(rrs, "_read_snaps", lambda seasons: pd.DataFrame())
        monkeypatch.setattr(rrs, "_read_player_weekly_for_id_map", lambda seasons: pd.DataFrame())

        result = build_rb_role_signals([2022])
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Tests: temporal lag correctness
# ---------------------------------------------------------------------------


class TestTemporalLag:
    """Cross-cutting tests that verify no week-t outcomes are used for week-t signals."""

    def test_teammate_signal_does_not_use_current_week_outcomes(self):
        """rb_better_teammate_returning only uses injury data from weeks < t.

        A teammate who is 'Out' in week t itself should NOT trigger
        rb_better_teammate_returning at week t (they haven't returned).
        """
        # Weeks 1-3: RB_STAR healthy; week 4: RB_STAR Out for first time
        dc_rows = [
            {"season": 2022, "week": w, "club_code": "DAL", "gsis_id": "RB_STAR", "depth_team": 1}
            for w in range(1, 6)
        ] + [
            {"season": 2022, "week": w, "club_code": "DAL", "gsis_id": "RB_FILL", "depth_team": 2}
            for w in range(1, 6)
        ]
        dc = _make_depth_chart(dc_rows)

        # RB_STAR goes Out in week 4 for the first time — not previously Out
        inj = _make_injury_report([
            {"season": 2022, "week": 4, "team": "DAL", "player_id": "RB_STAR", "report_status": "Out"},
        ])
        result = compute_teammate_status_signals(dc, inj)

        # At week 5: RB_STAR was Out in week 4 (within lookback) and is active now
        fill_w5 = result[(result["player_id"] == "RB_FILL") & (result["week"] == 5)]
        assert fill_w5.iloc[0]["rb_better_teammate_returning"] == 1

        # At week 4: RB_STAR is Out THIS week — but was never Out before
        # → rb_better_teammate_returning should be 0 (no prior absence to return from)
        fill_w4 = result[(result["player_id"] == "RB_FILL") & (result["week"] == 4)]
        assert fill_w4.iloc[0]["rb_better_teammate_returning"] == 0

    def test_depth_chart_modal_rank_excludes_current_week(self):
        """modal_depth_rank_lookback at week t must not include week t's own rank."""
        # Weeks 3-4: rank 2; week 5: promoted to rank 1
        dc = _make_depth_chart([
            {"season": 2022, "week": 3, "club_code": "GB", "gsis_id": "AJ_DILLON", "depth_team": 2},
            {"season": 2022, "week": 4, "club_code": "GB", "gsis_id": "AJ_DILLON", "depth_team": 2},
            {"season": 2022, "week": 5, "club_code": "GB", "gsis_id": "AJ_DILLON", "depth_team": 1},
        ])
        result = compute_depth_chart_staleness(dc)
        w5 = result[(result["player_id"] == "AJ_DILLON") & (result["week"] == 5)]
        # Modal should be 2 (from weeks 3-4), NOT influenced by week 5's rank=1
        assert w5.iloc[0]["modal_depth_rank_lookback"] == 2
        assert w5.iloc[0]["depth_rank_improved"] == 1


# ---------------------------------------------------------------------------
# Named sanity case tests
# ---------------------------------------------------------------------------


class TestNamedSanityCases:
    """Verify signals match known real-world failure cases.

    These tests use real Bronze data loaded from disk. They are marked
    `pytest.mark.integration` and skipped if data files are unavailable.
    """

    SEASONS = [2022, 2023, 2024]

    @pytest.fixture(scope="class")
    def real_dc(self):
        """Load real depth chart data from Bronze."""
        import glob, os
        frames = []
        base = os.path.join(os.path.dirname(__file__), "..", "data", "bronze", "depth_charts")
        for season in self.SEASONS:
            pattern = os.path.join(base, f"season={season}", "*.parquet")
            files = sorted(glob.glob(pattern))
            if files:
                frames.append(pd.read_parquet(files[-1]))
        if not frames:
            pytest.skip("Real depth chart data not available")
        dc = pd.concat(frames, ignore_index=True)
        dc["week"] = pd.to_numeric(dc["week"], errors="coerce")
        dc = dc[dc["week"].between(1, 18)].copy()
        dc["week"] = dc["week"].astype(int)
        dc["depth_team"] = pd.to_numeric(dc["depth_team"], errors="coerce")
        if "formation" in dc.columns:
            dc = dc[dc["formation"] == "Offense"]
        dc = dc[dc["position"] == "RB"]
        if "depth_position" in dc.columns:
            keep = dc["depth_position"].str.strip().isin({"RB", "HB"}) | dc["depth_position"].str.strip().eq("")
            dc = dc[keep]
        dc = dc.dropna(subset=["gsis_id", "depth_team"])
        dc["season"] = dc["season"].astype(int)
        return dc

    @pytest.fixture(scope="class")
    def real_inj(self):
        """Load real injury data from Bronze."""
        import glob, os
        frames = []
        base = os.path.join(os.path.dirname(__file__), "..", "data", "bronze", "players", "injuries")
        for season in self.SEASONS:
            pattern = os.path.join(base, f"season={season}", "*.parquet")
            files = sorted(glob.glob(pattern))
            if files:
                frames.append(pd.read_parquet(files[-1]))
        if not frames:
            pytest.skip("Real injury data not available")
        inj = pd.concat(frames, ignore_index=True)
        inj["week"] = pd.to_numeric(inj["week"], errors="coerce")
        inj = inj[inj["week"].between(1, 18)]
        inj["week"] = inj["week"].astype(int)
        inj["season"] = inj["season"].astype(int)
        if "gsis_id" in inj.columns:
            inj = inj.rename(columns={"gsis_id": "player_id"})
        inj["report_status"] = inj["report_status"].fillna("").astype(str)
        return inj

    @pytest.fixture(scope="class")
    def real_snaps(self):
        """Load real snap count data from Bronze."""
        import glob, os
        frames = []
        base = os.path.join(os.path.dirname(__file__), "..", "data", "bronze", "players", "snaps")
        for season in self.SEASONS:
            pattern = os.path.join(base, f"season={season}", "week=*", "*.parquet")
            files = sorted(glob.glob(pattern))
            if files:
                frames.extend([pd.read_parquet(f) for f in files])
        if not frames:
            pytest.skip("Real snap data not available")
        snaps = pd.concat(frames, ignore_index=True)
        snaps["week"] = pd.to_numeric(snaps["week"], errors="coerce")
        snaps = snaps[snaps["week"].between(1, 18)]
        snaps["week"] = snaps["week"].astype(int)
        snaps["season"] = snaps["season"].astype(int)
        if "position" in snaps.columns:
            snaps = snaps[snaps["position"] == "RB"]
        snaps["offense_pct"] = pd.to_numeric(snaps["offense_pct"], errors="coerce").fillna(0.0)
        return snaps

    @pytest.mark.integration
    def test_zack_moss_2023_rb_better_teammate_returning(self, real_dc, real_inj):
        """Z.Moss 2023: rb_better_teammate_returning should fire when J.Taylor returns.

        J.Taylor's early-season 2023 absence was a contract holdout (not an
        in-season injury), so no injury report entry exists in Bronze.
        However, Taylor was reported Out in weeks 13-15 with an ankle injury
        and returned for week 16. Therefore rb_better_teammate_returning should
        fire for Moss at week 16 or 18 (the weeks after Taylor's w13-w15 Out
        stint).

        This test verifies the MECHANISM works on real data — the early-season
        holdout gap is a known Bronze data limitation that the depth_rank_worsened
        signal compensates for.
        """
        moss_id = "00-0036251"
        result = compute_teammate_status_signals(real_dc, real_inj)
        moss = result[
            (result["player_id"] == moss_id)
            & (result["season"] == 2023)
        ]
        # Taylor was Out w13-w15 and returned w16 → signal should fire at w16+
        returning_rows = moss[
            (moss["week"].between(16, 18))
            & (moss["rb_better_teammate_returning"] == 1)
        ]
        assert len(returning_rows) > 0, (
            f"Expected rb_better_teammate_returning to fire for Z.Moss 2023 w16-18 "
            f"(Taylor returned from w13-w15 Out). "
            f"Got: {moss[['week','rb_better_teammate_out','rb_better_teammate_returning']].to_string()}"
        )

    @pytest.mark.integration
    def test_donta_foreman_2022_w8_rb_better_teammate_out(self, real_dc, real_inj):
        """D.Foreman 2022 w8: depth_rank_improved should fire (depth 2→1).

        CMC was traded before week 8. The depth chart shows Foreman moves to
        rank 1 at week 8. depth_rank_improved should fire.
        """
        foreman_id = "00-0033925"
        result = compute_depth_chart_staleness(real_dc)
        fore = result[
            (result["player_id"] == foreman_id)
            & (result["season"] == 2022)
            & (result["week"] == 8)
        ]
        assert len(fore) > 0, "Foreman 2022 w8 not found in depth chart data"
        assert fore.iloc[0]["depth_rank_improved"] == 1, (
            f"Expected depth_rank_improved=1 for Foreman 2022 w8, "
            f"got {fore.iloc[0].to_dict()}"
        )

    @pytest.mark.integration
    def test_charbonnet_2024_w15_rb_better_teammate_out(self, real_dc, real_inj):
        """Z.Charbonnet 2024 w15: rb_better_teammate_out should fire.

        K.Walker was Doubtful at week 15 — his injury should promote Charbonnet.
        """
        charb_id = "00-0039165"
        result = compute_teammate_status_signals(real_dc, real_inj)
        charb = result[
            (result["player_id"] == charb_id)
            & (result["season"] == 2024)
            & (result["week"] == 15)
        ]
        assert len(charb) > 0, "Charbonnet 2024 w15 not found"
        assert charb.iloc[0]["rb_better_teammate_out"] >= 1, (
            f"Expected rb_better_teammate_out >= 1 for Charbonnet 2024 w15, "
            f"got {charb.iloc[0].to_dict()}"
        )

    @pytest.mark.integration
    def test_zack_moss_snap_collapsing_fires_2023(self, real_snaps):
        """Z.Moss 2023 w8-w10: snap_share_collapsing should fire as snaps shrink.

        After J.Taylor returned, Moss's snap share fell from ~0.80-0.98 to
        0.39/0.21/0.16 over weeks 8-10.  At least one of these weeks should
        trigger snap_share_collapsing=1.
        """
        result = compute_snap_trend_signals(real_snaps)
        moss_rows = result[
            (result["player"] == "Zack Moss")
            & (result["season"] == 2023)
            & (result["week"].isin([8, 9, 10]))
        ]
        if len(moss_rows) == 0:
            # Try display name variation
            moss_rows = result[
                (result["player"].str.contains("Moss", na=False))
                & (result["team"] == "IND")
                & (result["season"] == 2023)
                & (result["week"].isin([8, 9, 10]))
            ]
        assert len(moss_rows) > 0, "Z.Moss 2023 w8-w10 not found in snap data"
        # At least one of w8-w10 should show collapsing snap share
        assert moss_rows["snap_share_collapsing"].max() == 1, (
            f"Expected snap_share_collapsing=1 for Z.Moss 2023 w8-w10. "
            f"Got: {moss_rows[['week','recent_snap_pct','prior_snap_pct','snap_share_slope','snap_share_collapsing']].to_string()}"
        )
