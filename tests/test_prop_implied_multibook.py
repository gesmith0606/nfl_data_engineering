"""
Unit tests for the multi-book props read path (.planning/PROPS_MULTIBOOK_2026_08_16.md).

Covers ``discover_props_sources`` / ``load_multibook_props`` /
``summarize_book_coverage`` in ``src/prop_implied.py``: gathering the latest
Odds API flat capture (season-only partition) PLUS the latest
week-partitioned DK/FanDuel direct captures
(``scripts/bronze_weekly_props_ingestion.py``), which the original
single-glob ``--props-blend`` read never saw.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from prop_implied import (  # noqa: E402
    compute_prop_implied_points,
    discover_props_sources,
    load_multibook_props,
    summarize_book_coverage,
)


def _prop_row(player, market, line, over, under, book, ts="2026-09-13T12:00:00Z"):
    return {
        "snapshot_ts": ts,
        "event_id": "ev1",
        "commence_time": "2026-09-13T17:00:00Z",
        "home_team": "Chiefs",
        "away_team": "Bills",
        "home_team_nfl": "KC",
        "away_team_nfl": "BUF",
        "bookmaker": book,
        "market": market,
        "player_name": player,
        "line": line,
        "price_over": over,
        "price_under": under,
        "season": 2026,
    }


def _props_dir(project_root, season, week=None):
    base = os.path.join(project_root, "data", "bronze", "odds_api", "props", f"season={season}")
    if week is not None:
        base = os.path.join(base, f"week={week}")
    os.makedirs(base, exist_ok=True)
    return base


def _write(path, rows):
    pd.DataFrame(rows).to_parquet(path, index=False)


class TestDiscoverPropsSources:
    def test_missing_week_fails_open(self, tmp_path):
        # Nothing written at all for this (season, week) -> empty dict.
        assert discover_props_sources(2026, 1, str(tmp_path)) == {}

    def test_odds_api_only(self, tmp_path):
        d = _props_dir(tmp_path, 2026)
        path = os.path.join(d, "props_20260913_120000.parquet")
        _write(path, [_prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "draftkings")])

        sources = discover_props_sources(2026, 1, str(tmp_path))
        assert set(sources) == {"odds_api"}
        assert sources["odds_api"] == path

    def test_odds_api_excludes_archive_files(self, tmp_path):
        d = _props_dir(tmp_path, 2026)
        _write(
            os.path.join(d, "props_archive_2026.parquet"),
            [_prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "fanduel")],
        )
        assert discover_props_sources(2026, 1, str(tmp_path)) == {}

    def test_odds_api_latest_file_wins(self, tmp_path):
        d = _props_dir(tmp_path, 2026)
        older = os.path.join(d, "props_20260910_090000.parquet")
        newer = os.path.join(d, "props_20260913_120000.parquet")
        _write(older, [_prop_row("A Back", "player_rush_yds", 70.5, -110, -110, "draftkings")])
        _write(newer, [_prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "draftkings")])

        sources = discover_props_sources(2026, 1, str(tmp_path))
        assert sources["odds_api"] == newer

    def test_dk_and_fd_are_week_scoped(self, tmp_path):
        week_dir = _props_dir(tmp_path, 2026, week=1)
        dk_path = os.path.join(week_dir, "props_dk_20260913_120000.parquet")
        fd_path = os.path.join(week_dir, "props_fd_20260913_120000.parquet")
        _write(dk_path, [_prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "draftkings")])
        _write(fd_path, [_prop_row("A Back", "player_rush_yds", 81.5, -110, -110, "fanduel")])

        # Week 1 sees both DK/FD; week 2 (no files there) sees neither.
        sources_wk1 = discover_props_sources(2026, 1, str(tmp_path))
        assert sources_wk1["dk_direct"] == dk_path
        assert sources_wk1["fd_direct"] == fd_path

        sources_wk2 = discover_props_sources(2026, 2, str(tmp_path))
        assert "dk_direct" not in sources_wk2
        assert "fd_direct" not in sources_wk2

    def test_all_three_sources_found(self, tmp_path):
        season_dir = _props_dir(tmp_path, 2026)
        week_dir = _props_dir(tmp_path, 2026, week=1)
        _write(
            os.path.join(season_dir, "props_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "betmgm")],
        )
        _write(
            os.path.join(week_dir, "props_dk_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 81.5, -110, -110, "draftkings")],
        )
        _write(
            os.path.join(week_dir, "props_fd_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 79.5, -110, -110, "fanduel")],
        )

        sources = discover_props_sources(2026, 1, str(tmp_path))
        assert set(sources) == {"odds_api", "dk_direct", "fd_direct"}


class TestLoadMultibookProps:
    def test_missing_week_fails_open_empty_frame(self, tmp_path):
        out = load_multibook_props(2026, 1, str(tmp_path))
        assert out.empty

    def test_single_book_passthrough(self, tmp_path):
        d = _props_dir(tmp_path, 2026)
        path = os.path.join(d, "props_20260913_120000.parquet")
        rows = [_prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "draftkings")]
        _write(path, rows)

        out = load_multibook_props(2026, 1, str(tmp_path))
        assert len(out) == 1
        assert out.iloc[0]["capture_source"] == "odds_api"
        assert out.iloc[0]["bookmaker"] == "draftkings"

    def test_multibook_concatenates_and_tags_source(self, tmp_path):
        season_dir = _props_dir(tmp_path, 2026)
        week_dir = _props_dir(tmp_path, 2026, week=1)
        _write(
            os.path.join(season_dir, "props_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "betmgm")],
        )
        _write(
            os.path.join(week_dir, "props_dk_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 84.5, -110, -110, "draftkings")],
        )
        _write(
            os.path.join(week_dir, "props_fd_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 88.5, -110, -110, "fanduel")],
        )

        out = load_multibook_props(2026, 1, str(tmp_path))
        assert len(out) == 3
        assert set(out["capture_source"]) == {"odds_api", "dk_direct", "fd_direct"}
        assert set(out["bookmaker"]) == {"betmgm", "draftkings", "fanduel"}

    def test_multibook_median_of_implied_points(self, tmp_path):
        # Mirrors src/season_prop_implied.py's documented cross-book rule:
        # median of implied points where dual/triple-quoted. Balanced juice
        # on all three books -> implied mean == line, so the median rushing
        # yard across books (80.5 / 84.5 / 88.5) should be 84.5.
        season_dir = _props_dir(tmp_path, 2026)
        week_dir = _props_dir(tmp_path, 2026, week=1)
        _write(
            os.path.join(season_dir, "props_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "betmgm")],
        )
        _write(
            os.path.join(week_dir, "props_dk_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 84.5, -110, -110, "draftkings")],
        )
        _write(
            os.path.join(week_dir, "props_fd_20260913_120000.parquet"),
            [_prop_row("A Back", "player_rush_yds", 88.5, -110, -110, "fanduel")],
        )

        combined = load_multibook_props(2026, 1, str(tmp_path))
        implied = compute_prop_implied_points(combined)
        assert len(implied) == 1
        assert implied.iloc[0]["rushing_yards"] == pytest.approx(84.5, abs=0.01)
        assert implied.iloc[0]["prop_market_count"] == 1

    def test_byte_identical_when_only_odds_api_present(self, tmp_path):
        # Backward compatibility: when only the Odds API source exists, the
        # multi-book path must produce implied points identical to reading
        # that single file directly (today's behavior).
        d = _props_dir(tmp_path, 2026)
        path = os.path.join(d, "props_20260913_120000.parquet")
        rows = [
            _prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "draftkings"),
            _prop_row("A Back", "player_receptions", 3.5, -120, 100, "fanduel"),
            _prop_row("Another Guy", "player_reception_yds", 45.5, -110, -110, "draftkings"),
        ]
        _write(path, rows)

        legacy = compute_prop_implied_points(pd.read_parquet(path))
        multibook = compute_prop_implied_points(load_multibook_props(2026, 1, str(tmp_path)))

        pd.testing.assert_frame_equal(
            legacy.reset_index(drop=True), multibook.reset_index(drop=True)
        )


class TestSummarizeBookCoverage:
    def test_empty_input(self):
        out = summarize_book_coverage(pd.DataFrame())
        assert out.empty

    def test_counts_distinct_books_per_market(self):
        df = pd.DataFrame(
            [
                _prop_row("A Back", "player_rush_yds", 80.5, -110, -110, "draftkings"),
                _prop_row("A Back", "player_rush_yds", 84.5, -110, -110, "fanduel"),
                _prop_row("A Back", "player_receptions", 3.5, -110, -110, "draftkings"),
            ]
        )
        out = summarize_book_coverage(df)
        assert out.loc["player_rush_yds", "book_count"] == 2
        assert set(out.loc["player_rush_yds", "books"]) == {"draftkings", "fanduel"}
        assert out.loc["player_receptions", "book_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
