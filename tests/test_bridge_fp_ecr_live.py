"""Tests for scripts/bridge_fp_ecr_live.py — live FantasyPros -> Silver FP-ECR bridge.

No live network access. Schedule-window lookups are monkeypatched so week
mapping is tested against controlled fixtures rather than the real 2026
Bronze schedules file (which is still being ingested week-by-week).
"""

import gzip
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts import bridge_fp_ecr_live as bridge  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Mirrors the real 2026 Bronze schedules windows (verified 2026-08-21):
# week 1 = 2026-09-09..2026-09-14.
WINDOWS_2026 = {
    1: (date(2026, 9, 9), date(2026, 9, 14)),
    2: (date(2026, 9, 17), date(2026, 9, 21)),
}


class _FakeResolver:
    """Stand-in for PlayerNameResolver with a controllable tiered lookup."""

    def __init__(self, exact: Dict, position_only: Optional[Dict] = None, name_only: Optional[Dict] = None):
        self.exact = exact  # (name, team, position) -> gsis_id
        self.position_only = position_only or {}  # (name, position) -> gsis_id
        self.name_only = name_only or {}  # name -> gsis_id
        self.calls = []

    def resolve(self, name, team=None, position=None):
        self.calls.append((name, team, position))
        if team and position and (name, team, position) in self.exact:
            return self.exact[(name, team, position)]
        if position and (name, position) in self.position_only:
            return self.position_only[(name, position)]
        if name in self.name_only:
            return self.name_only[name]
        return None


def _player(name, position, team, rank):
    return {"player_name": name, "position": position, "team": team, "rank": rank, "external_rank": rank}


# ---------------------------------------------------------------------------
# capture_to_position_ranked_rows
# ---------------------------------------------------------------------------


class TestCaptureToPositionRankedRows:
    def test_derives_pos_rank_within_position(self):
        players = [
            _player("Ja'Marr Chase", "WR", "CIN", 1),
            _player("Bijan Robinson", "RB", "ATL", 2),
            _player("Justin Jefferson", "WR", "MIN", 4),
            _player("Nico Collins", "WR", "HOU", 9),
        ]
        out = bridge.capture_to_position_ranked_rows(players)
        wr = out[out["position"] == "WR"].sort_values("pos_rank")
        assert wr["player_name"].tolist() == ["Ja'Marr Chase", "Justin Jefferson", "Nico Collins"]
        assert wr["pos_rank"].tolist() == [1, 2, 3]

    def test_drops_non_fantasy_positions(self):
        players = [
            _player("Justin Tucker", "K", "BAL", 200),
            _player("Some Kicker", "K", "SF", 205),
            _player("Ja'Marr Chase", "WR", "CIN", 1),
        ]
        out = bridge.capture_to_position_ranked_rows(players)
        assert set(out["position"]) == {"WR"}

    def test_empty_input_returns_empty_with_columns(self):
        out = bridge.capture_to_position_ranked_rows([])
        assert out.empty
        assert list(out.columns) == ["player_name", "position", "team", "pos_rank"]

    def test_tied_overall_rank_gets_min_pos_rank(self):
        # Two WRs sharing the same overall rank (edge case in a truncated board).
        players = [
            _player("Player A", "WR", "AAA", 5),
            _player("Player B", "WR", "BBB", 5),
            _player("Player C", "WR", "CCC", 7),
        ]
        out = bridge.capture_to_position_ranked_rows(players)
        ranks = dict(zip(out["player_name"], out["pos_rank"]))
        assert ranks["Player A"] == 1
        assert ranks["Player B"] == 1
        assert ranks["Player C"] == 3


# ---------------------------------------------------------------------------
# resolve_gsis_ids — fallback tiers + team-code normalization
# ---------------------------------------------------------------------------


class TestResolveGsisIds:
    def test_tier1_exact_team_position_match(self):
        df = pd.DataFrame([{"player_name": "Ja'Marr Chase", "team": "CIN", "position": "WR", "pos_rank": 1}])
        resolver = _FakeResolver(exact={("Ja'Marr Chase", "CIN", "WR"): "00-0037744"})
        out = bridge.resolve_gsis_ids(df, resolver)
        assert out["gsis_id"].iloc[0] == "00-0037744"

    def test_falls_back_to_position_only_on_team_mismatch(self):
        # Simulates a mid-season trade: our capture's team no longer matches
        # the resolver's index (or FP's stale team tag).
        df = pd.DataFrame([{"player_name": "Traded Guy", "team": "OLD", "position": "WR", "pos_rank": 5}])
        resolver = _FakeResolver(exact={}, position_only={("Traded Guy", "WR"): "00-0011111"})
        out = bridge.resolve_gsis_ids(df, resolver)
        assert out["gsis_id"].iloc[0] == "00-0011111"

    def test_falls_back_to_name_only_as_last_resort(self):
        df = pd.DataFrame([{"player_name": "Ambiguous Guy", "team": "ZZZ", "position": "QQ", "pos_rank": 9}])
        resolver = _FakeResolver(exact={}, position_only={}, name_only={"Ambiguous Guy": "00-0022222"})
        out = bridge.resolve_gsis_ids(df, resolver)
        assert out["gsis_id"].iloc[0] == "00-0022222"

    def test_unresolvable_row_returns_none(self):
        df = pd.DataFrame([{"player_name": "Nobody", "team": "ZZZ", "position": "WR", "pos_rank": 99}])
        resolver = _FakeResolver(exact={}, position_only={}, name_only={})
        out = bridge.resolve_gsis_ids(df, resolver)
        assert out["gsis_id"].iloc[0] is None

    def test_team_code_normalized_before_lookup(self):
        # FP tags Jacksonville "JAC"; the Bronze index convention is "JAX".
        df = pd.DataFrame([{"player_name": "Some Jag", "team": "JAC", "position": "WR", "pos_rank": 20}])
        resolver = _FakeResolver(exact={("Some Jag", "JAX", "WR"): "00-0033333"})
        out = bridge.resolve_gsis_ids(df, resolver)
        assert out["gsis_id"].iloc[0] == "00-0033333"

    def test_cache_avoids_redundant_resolver_calls(self):
        df = pd.DataFrame(
            [
                {"player_name": "Repeat Guy", "team": "CIN", "position": "WR", "pos_rank": 1},
                {"player_name": "Repeat Guy", "team": "CIN", "position": "WR", "pos_rank": 1},
            ]
        )
        resolver = _FakeResolver(exact={("Repeat Guy", "CIN", "WR"): "00-0099999"})
        cache = {}
        bridge.resolve_gsis_ids(df, resolver, cache=cache)
        assert len(resolver.calls) == 1  # second row served from cache

    def test_empty_frame_gets_gsis_id_column(self):
        df = pd.DataFrame(columns=["player_name", "team", "position", "pos_rank"])
        out = bridge.resolve_gsis_ids(df, _FakeResolver(exact={}))
        assert "gsis_id" in out.columns
        assert out.empty


# ---------------------------------------------------------------------------
# build_silver_rows — week mapping, scoring label, fail-loud match rate
# ---------------------------------------------------------------------------


class TestBuildSilverRows:
    def _patch_windows(self, monkeypatch, windows=WINDOWS_2026):
        monkeypatch.setattr(bridge.fpecr_ingest, "load_schedule_reg_windows", lambda season: windows)

    def test_preseason_date_maps_to_week_1(self, monkeypatch):
        self._patch_windows(monkeypatch)
        capture = bridge.Capture(
            scrape_date=date(2026, 8, 18),
            players=[_player("Ja'Marr Chase", "WR", "CIN", 1)],
        )
        resolver = _FakeResolver(exact={("Ja'Marr Chase", "CIN", "WR"): "00-0037744"})
        out = bridge.build_silver_rows(capture, resolver, cache={})
        assert (out["week"] == 1).all()
        assert (out["season"] == 2026).all()
        assert (out["scrape_date"] == date(2026, 8, 18)).all()

    def test_scoring_label_is_honest_half_ppr(self, monkeypatch):
        self._patch_windows(monkeypatch)
        capture = bridge.Capture(scrape_date=date(2026, 8, 18), players=[_player("X Y", "WR", "CIN", 1)])
        resolver = _FakeResolver(exact={("X Y", "CIN", "WR"): "00-0000001"})
        out = bridge.build_silver_rows(capture, resolver, cache={})
        assert (out["scoring"] == "half_ppr").all()

    def test_nulls_fields_our_capture_does_not_have(self, monkeypatch):
        self._patch_windows(monkeypatch)
        capture = bridge.Capture(scrape_date=date(2026, 8, 18), players=[_player("X Y", "WR", "CIN", 1)])
        resolver = _FakeResolver(exact={("X Y", "CIN", "WR"): "00-0000001"})
        out = bridge.build_silver_rows(capture, resolver, cache={})
        row = out.iloc[0]
        assert pd.isna(row["fantasypros_id"])
        assert pd.isna(row["sd"])
        assert pd.isna(row["best"])
        assert pd.isna(row["worst"])
        assert pd.isna(row["ecr"])

    def test_no_week_mapping_drops_capture(self, monkeypatch):
        # Date after every known week's max_gameday -> unmapped, same rule
        # as ingest_fp_ecr_history's post-season handling.
        self._patch_windows(monkeypatch, windows={1: (date(2026, 9, 9), date(2026, 9, 14))})
        capture = bridge.Capture(scrape_date=date(2027, 6, 1), players=[_player("X Y", "WR", "CIN", 1)])
        resolver = _FakeResolver(exact={})
        out = bridge.build_silver_rows(capture, resolver, cache={})
        assert out.empty

    def test_wr_match_rate_below_90pct_fails_loud(self, monkeypatch):
        self._patch_windows(monkeypatch)
        # 10 WR rows, only 8 resolvable -> 80% < 90% floor.
        players = [_player(f"Resolvable {i}", "WR", "CIN", i) for i in range(8)]
        players += [_player(f"Unresolvable {i}", "WR", "CIN", 8 + i) for i in range(2)]
        capture = bridge.Capture(scrape_date=date(2026, 8, 18), players=players)
        exact = {(f"Resolvable {i}", "CIN", "WR"): f"00-000000{i}" for i in range(8)}
        resolver = _FakeResolver(exact=exact)
        with pytest.raises(RuntimeError, match="below the 90% floor"):
            bridge.build_silver_rows(capture, resolver, cache={})

    def test_wr_match_rate_at_90pct_passes(self, monkeypatch):
        self._patch_windows(monkeypatch)
        players = [_player(f"Resolvable {i}", "WR", "CIN", i) for i in range(9)]
        players += [_player("Unresolvable", "WR", "CIN", 9)]
        capture = bridge.Capture(scrape_date=date(2026, 8, 18), players=players)
        exact = {(f"Resolvable {i}", "CIN", "WR"): f"00-000000{i}" for i in range(9)}
        resolver = _FakeResolver(exact=exact)
        out = bridge.build_silver_rows(capture, resolver, cache={})
        assert len(out) == 10


# ---------------------------------------------------------------------------
# Schema-match against a real historical Silver file
# ---------------------------------------------------------------------------


class TestSchemaMatchesHistoricalArchive:
    HISTORICAL_FILE = os.path.join(
        os.path.dirname(__file__), "..", "data", "silver", "fp_ecr", "season=2024", "fp_ecr_2024.parquet"
    )

    @pytest.mark.skipif(
        not os.path.exists(HISTORICAL_FILE),
        reason="Local-only historical FP-ECR archive not present in this checkout",
    )
    def test_columns_match_column_for_column(self, monkeypatch):
        historical = pd.read_parquet(self.HISTORICAL_FILE)
        monkeypatch.setattr(
            bridge.fpecr_ingest, "load_schedule_reg_windows", lambda season: WINDOWS_2026
        )
        capture = bridge.Capture(scrape_date=date(2026, 8, 18), players=[_player("X Y", "WR", "CIN", 1)])
        resolver = _FakeResolver(exact={("X Y", "CIN", "WR"): "00-0000001"})
        bridged = bridge.build_silver_rows(capture, resolver, cache={})

        assert list(bridged.columns) == list(historical.columns) == bridge.SILVER_COLUMNS

        # dtype *kind* (numeric/object) must match; nullable-vs-plain numeric
        # dtypes differ where the bridge legitimately has to null fields the
        # historical archive always had populated (fantasypros_id/sd/best/
        # worst/ecr) -- see module docstring finding #2.
        for col in bridged.columns:
            assert bridged[col].dtype.kind == historical[col].dtype.kind or (
                bridged[col].dtype.kind in "iuf" and historical[col].dtype.kind in "iuf"
            ), f"column {col}: {bridged[col].dtype} vs {historical[col].dtype}"


# ---------------------------------------------------------------------------
# Idempotent upsert
# ---------------------------------------------------------------------------


class TestUpsertSilverSeason:
    def _rows(self, scrape_date, n=2, season=2026, week=1):
        return pd.DataFrame(
            {
                "season": [season] * n,
                "week": [week] * n,
                "scrape_date": [scrape_date] * n,
                "scoring": ["half_ppr"] * n,
                "position": ["WR"] * n,
                "player_name": [f"Player {i}" for i in range(n)],
                "fantasypros_id": pd.array([pd.NA] * n, dtype="Int64"),
                "gsis_id": [f"00-000000{i}" for i in range(n)],
                "sleeper_id": pd.array([pd.NA] * n, dtype="Float64"),
                "ecr": pd.array([pd.NA] * n, dtype="Float64"),
                "pos_rank": list(range(1, n + 1)),
                "sd": pd.array([pd.NA] * n, dtype="Float64"),
                "best": pd.array([pd.NA] * n, dtype="Int64"),
                "worst": pd.array([pd.NA] * n, dtype="Int64"),
            }
        )[bridge.SILVER_COLUMNS]

    def test_rerun_same_date_replaces_not_duplicates(self, tmp_path):
        silver_dir = str(tmp_path / "fp_ecr")
        rows_v1 = self._rows(date(2026, 8, 18), n=2)
        bridge.upsert_silver_season(rows_v1, season=2026, silver_dir=silver_dir)
        rows_v2 = self._rows(date(2026, 8, 18), n=3)  # a rerun with different content
        out_path = bridge.upsert_silver_season(rows_v2, season=2026, silver_dir=silver_dir)

        result = pd.read_parquet(out_path)
        assert len(result) == 3  # replaced, not appended (would be 5 if duplicated)

    def test_different_dates_accumulate(self, tmp_path):
        silver_dir = str(tmp_path / "fp_ecr")
        bridge.upsert_silver_season(self._rows(date(2026, 8, 17), n=2), season=2026, silver_dir=silver_dir)
        out_path = bridge.upsert_silver_season(
            self._rows(date(2026, 8, 18), n=2), season=2026, silver_dir=silver_dir
        )
        result = pd.read_parquet(out_path)
        assert len(result) == 4
        assert set(result["scrape_date"]) == {date(2026, 8, 17), date(2026, 8, 18)}

    def test_written_sorted_scrape_date_descending(self, tmp_path):
        silver_dir = str(tmp_path / "fp_ecr")
        bridge.upsert_silver_season(self._rows(date(2026, 8, 17), n=1), season=2026, silver_dir=silver_dir)
        out_path = bridge.upsert_silver_season(
            self._rows(date(2026, 8, 18), n=1), season=2026, silver_dir=silver_dir
        )
        result = pd.read_parquet(out_path)
        assert result["scrape_date"].tolist() == [date(2026, 8, 18), date(2026, 8, 17)]


# ---------------------------------------------------------------------------
# Capture loading (archive folder parsing + live-file dedup)
# ---------------------------------------------------------------------------


class TestLoadCaptures:
    def _write_archive_day(self, archive_dir, day, players):
        day_dir = os.path.join(archive_dir, day)
        os.makedirs(day_dir, exist_ok=True)
        envelope = {"source": "fantasypros", "fetched_at": f"{day}T12:00:00+00:00", "players": players}
        with gzip.open(os.path.join(day_dir, "fantasypros_rankings.json.gz"), "wt", encoding="utf-8") as f:
            f.write(json.dumps(envelope))

    def test_archive_folder_name_is_scrape_date(self, tmp_path):
        archive_dir = str(tmp_path / "archive")
        self._write_archive_day(archive_dir, "2026-08-17", [_player("A", "WR", "CIN", 1)])
        captures = bridge.load_archive_captures(archive_dir=archive_dir)
        assert len(captures) == 1
        assert captures[0].scrape_date == date(2026, 8, 17)

    def test_live_file_included_when_date_not_already_archived(self, tmp_path):
        external_dir = tmp_path / "external"
        archive_dir = str(external_dir / "archive")
        self._write_archive_day(archive_dir, "2026-08-17", [_player("A", "WR", "CIN", 1)])
        live_file = str(external_dir / "fantasypros_rankings.json")
        os.makedirs(external_dir, exist_ok=True)
        with open(live_file, "w", encoding="utf-8") as f:
            json.dump(
                {"source": "fantasypros", "fetched_at": "2026-08-18T12:00:00+00:00", "players": [_player("B", "WR", "MIA", 1)]},
                f,
            )
        captures = bridge.load_all_captures(archive_dir=archive_dir, live_file=live_file)
        assert {c.scrape_date for c in captures} == {date(2026, 8, 17), date(2026, 8, 18)}

    def test_live_file_skipped_when_date_already_archived(self, tmp_path):
        external_dir = tmp_path / "external"
        archive_dir = str(external_dir / "archive")
        self._write_archive_day(archive_dir, "2026-08-18", [_player("A", "WR", "CIN", 1)])
        live_file = str(external_dir / "fantasypros_rankings.json")
        os.makedirs(external_dir, exist_ok=True)
        with open(live_file, "w", encoding="utf-8") as f:
            json.dump(
                {"source": "fantasypros", "fetched_at": "2026-08-18T12:00:00+00:00", "players": [_player("B", "WR", "MIA", 1)]},
                f,
            )
        captures = bridge.load_all_captures(archive_dir=archive_dir, live_file=live_file)
        assert len(captures) == 1  # not duplicated

    def test_missing_archive_dir_returns_empty(self, tmp_path):
        assert bridge.load_archive_captures(archive_dir=str(tmp_path / "nope")) == []

    def test_non_date_folder_names_ignored(self, tmp_path):
        archive_dir = tmp_path / "archive"
        os.makedirs(archive_dir / "not-a-date", exist_ok=True)
        assert bridge.load_archive_captures(archive_dir=str(archive_dir)) == []


# ---------------------------------------------------------------------------
# Weekly-position preference (2026-08-22 amendment): a true weekly-position
# capture, when present for a scrape_date, wins over the draft-board
# capture for that same date.
# ---------------------------------------------------------------------------


def _weekly_player(name, position, team, pos_rank, ecr=None, sd=None, best=None, worst=None, fp_id=None):
    return {
        "player_name": name,
        "position": position,
        "team": team,
        "pos_rank": pos_rank,
        "ecr": ecr,
        "sd": sd,
        "best": best,
        "worst": worst,
        "fantasypros_id": fp_id,
    }


class TestWeeklyCaptureToPositionRows:
    def test_uses_pos_rank_and_dispersion_verbatim(self):
        players = [
            _weekly_player("Ja'Marr Chase", "WR", "CIN", 1, ecr=1.3, sd=0.46, best=1, worst=2, fp_id=19788),
        ]
        out = bridge.weekly_capture_to_position_rows(players)
        row = out.iloc[0]
        assert row["pos_rank"] == 1
        assert row["ecr"] == 1.3
        assert row["sd"] == 0.46
        assert row["fantasypros_id"] == 19788

    def test_drops_non_fantasy_positions(self):
        players = [
            _weekly_player("Kicker Guy", "K", "BAL", 1),
            _weekly_player("Ja'Marr Chase", "WR", "CIN", 1),
        ]
        out = bridge.weekly_capture_to_position_rows(players)
        assert set(out["position"]) == {"WR"}

    def test_empty_input_returns_empty_with_columns(self):
        out = bridge.weekly_capture_to_position_rows([])
        assert out.empty
        assert list(out.columns) == bridge._WEEKLY_ROW_COLS


class TestLoadAllCapturesWeeklyPreference:
    def _write_gz(self, archive_dir, day, source_name, players):
        day_dir = os.path.join(archive_dir, day)
        os.makedirs(day_dir, exist_ok=True)
        envelope = {"source": source_name, "fetched_at": f"{day}T12:00:00+00:00", "players": players}
        import gzip as _gzip
        with _gzip.open(os.path.join(day_dir, f"{source_name}_rankings.json.gz"), "wt", encoding="utf-8") as f:
            f.write(json.dumps(envelope))

    def test_weekly_wins_over_draft_board_same_date(self, tmp_path):
        archive_dir = str(tmp_path / "archive")
        self._write_gz(archive_dir, "2026-08-22", "fantasypros", [_player("Draft Board Guy", "WR", "CIN", 1)])
        self._write_gz(
            archive_dir, "2026-08-22", "fantasypros_weekly",
            [_weekly_player("Weekly Guy", "WR", "CIN", 1, ecr=1.3)],
        )
        captures = bridge.load_all_captures(archive_dir=archive_dir, live_file=str(tmp_path / "nope.json"))
        assert len(captures) == 1
        assert captures[0].kind == "weekly_position"
        assert captures[0].players[0]["player_name"] == "Weekly Guy"

    def test_draft_board_used_when_no_weekly_capture_for_date(self, tmp_path):
        archive_dir = str(tmp_path / "archive")
        self._write_gz(archive_dir, "2026-08-17", "fantasypros", [_player("Draft Board Guy", "WR", "CIN", 1)])
        captures = bridge.load_all_captures(archive_dir=archive_dir, live_file=str(tmp_path / "nope.json"))
        assert len(captures) == 1
        assert captures[0].kind == "draft_board"

    def test_both_present_different_dates_both_kept(self, tmp_path):
        archive_dir = str(tmp_path / "archive")
        self._write_gz(archive_dir, "2026-08-17", "fantasypros", [_player("A", "WR", "CIN", 1)])
        self._write_gz(archive_dir, "2026-08-18", "fantasypros_weekly", [_weekly_player("B", "WR", "CIN", 1)])
        captures = bridge.load_all_captures(archive_dir=archive_dir, live_file=str(tmp_path / "nope.json"))
        kinds = {c.scrape_date: c.kind for c in captures}
        assert kinds[__import__("datetime").date(2026, 8, 17)] == "draft_board"
        assert kinds[__import__("datetime").date(2026, 8, 18)] == "weekly_position"


class TestBuildSilverRowsWeeklySource:
    def _patch_windows(self, monkeypatch, windows=WINDOWS_2026):
        monkeypatch.setattr(bridge.fpecr_ingest, "load_schedule_reg_windows", lambda season: windows)

    def test_weekly_capture_populates_dispersion_fields(self, monkeypatch):
        self._patch_windows(monkeypatch)
        capture = bridge.Capture(
            scrape_date=date(2026, 8, 18),
            players=[_weekly_player("X Y", "WR", "CIN", 3, ecr=5.2, sd=1.1, best=2, worst=9, fp_id=42)],
            kind="weekly_position",
        )
        resolver = _FakeResolver(exact={("X Y", "CIN", "WR"): "00-0000001"})
        out = bridge.build_silver_rows(capture, resolver, cache={})
        row = out.iloc[0]
        assert row["pos_rank"] == 3
        assert row["ecr"] == 5.2
        assert row["sd"] == 1.1
        assert row["best"] == 2
        assert row["worst"] == 9
        assert row["fantasypros_id"] == 42

    def test_draft_board_kind_still_nulls_dispersion_fields(self, monkeypatch):
        """Explicit kind="draft_board" (the default) must be unaffected --
        no regression to the pre-amendment behavior."""
        self._patch_windows(monkeypatch)
        capture = bridge.Capture(
            scrape_date=date(2026, 8, 18),
            players=[_player("X Y", "WR", "CIN", 1)],
            kind="draft_board",
        )
        resolver = _FakeResolver(exact={("X Y", "CIN", "WR"): "00-0000001"})
        out = bridge.build_silver_rows(capture, resolver, cache={})
        row = out.iloc[0]
        assert pd.isna(row["ecr"])
        assert pd.isna(row["sd"])
        assert pd.isna(row["fantasypros_id"])
