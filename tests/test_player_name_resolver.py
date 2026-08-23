"""Tests for PlayerNameResolver's index construction and source-priority sort.

Covers the regression where `_build_index` sorted the combined depth_chart /
roster / player_weekly rows by season using the default (unstable) quicksort,
which can reorder same-season rows across sources and break the documented
source-priority ordering (depth_charts > rosters > player_weekly) that
`drop_duplicates(keep="first")` relies on.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from player_name_resolver import PlayerNameResolver, _normalise


def _write_parquet(path, df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)


@pytest.fixture
def bronze_root(tmp_path):
    """Build a minimal Bronze layer with the SAME player_id/season present
    in all three sources but with conflicting `team` values, so we can tell
    which source's row won the de-dup.
    """
    root = tmp_path / "bronze"

    depth_charts = pd.DataFrame(
        {
            "player_id": ["00-0099999"],
            "full_name": ["Test Player"],
            "football_name": ["Test"],
            "team": ["AAA"],
            "position": ["WR"],
            "season": [2024],
        }
    )
    rosters = pd.DataFrame(
        {
            "player_id": ["00-0099999"],
            "full_name": ["Test Player"],
            "football_name": ["Test"],
            "team": ["BBB"],
            "position": ["WR"],
            "season": [2024],
        }
    )
    player_weekly = pd.DataFrame(
        {
            "player_id": ["00-0099999"],
            "full_name": ["Test Player"],
            "football_name": ["Test"],
            "team": ["CCC"],
            "position": ["WR"],
            "season": [2024],
        }
    )

    _write_parquet(
        root / "depth_charts" / "season=2024" / "depth_charts_20240101.parquet",
        depth_charts,
    )
    _write_parquet(
        root / "players" / "rosters" / "season=2024" / "rosters_20240101.parquet",
        rosters,
    )
    _write_parquet(
        root / "players" / "weekly" / "season=2024" / "player_weekly_20240101.parquet",
        player_weekly,
    )
    return root


class TestSourcePriorityOrdering:
    """depth_charts must win over rosters/player_weekly for same-season ties."""

    def test_depth_chart_wins_same_season_conflict(self, bronze_root):
        resolver = PlayerNameResolver(bronze_root=bronze_root)
        entries = [e for e in resolver.index if e.player_id == "00-0099999"]
        assert len(entries) == 1, "de-dup should keep exactly one entry per player_id"
        assert entries[0].team == "AAA", (
            "depth_charts (highest priority source) should win the "
            "same-season conflict, but got team=%r" % entries[0].team
        )

    def test_sort_values_uses_stable_kind(self, bronze_root, monkeypatch):
        """Regression test pinned to the root cause: the season sort in
        _build_index must request a stable sort, not the default (unstable)
        quicksort, since ties in season carry meaningful source-priority
        ordering from the pre-sort concat order.
        """
        captured_kinds = []
        real_sort_values = pd.DataFrame.sort_values

        def spy_sort_values(self, *args, **kwargs):
            by = kwargs.get("by", args[0] if args else None)
            if by == "season":
                captured_kinds.append(kwargs.get("kind", "quicksort"))
            return real_sort_values(self, *args, **kwargs)

        monkeypatch.setattr(pd.DataFrame, "sort_values", spy_sort_values)

        PlayerNameResolver(bronze_root=bronze_root)

        assert captured_kinds, "expected a sort_values(by='season', ...) call"
        assert all(k == "stable" for k in captured_kinds), (
            f"season sort must use kind='stable' to preserve source-priority "
            f"ordering on ties; got kind values {captured_kinds}"
        )


# ---------------------------------------------------------------------------
# Regression: two pre-existing resolver bugs found via the live ECR bridge's
# ~3.6% WR non-match rate (2026-08-21 session) --
# knowledge-vault/concepts/player-name-resolver-dot-stripping-nickname-bug.md
# ---------------------------------------------------------------------------


@pytest.fixture
def nickname_bronze_root(tmp_path):
    """A minimal roster index containing the three players whose
    _NICKNAME_MAP entries were dead ("aj brown", "dj moore", "dj chark"),
    plus a player with an apostrophe in their roster name (for the
    apostrophe-stripping regression)."""
    root = tmp_path / "bronze"
    rosters = pd.DataFrame(
        {
            "player_id": ["00-1111111", "00-2222222", "00-3333333", "00-4444444"],
            "full_name": ["A.J. Brown", "D.J. Moore", "D.J. Chark", "Tre Harris"],
            "football_name": ["A.J. Brown", "D.J. Moore", "D.J. Chark", "Tre Harris"],
            "team": ["PHI", "CHI", "CAR", "LAC"],
            "position": ["WR", "WR", "WR", "WR"],
            "season": [2024, 2024, 2024, 2024],
        }
    )
    _write_parquet(
        root / "players" / "rosters" / "season=2024" / "rosters_20240101.parquet",
        rosters,
    )
    return root


class TestNormaliseApostrophes:
    """_normalise() must strip apostrophes, not just dots -- a name typed
    with an apostrophe (e.g. scraped RSS text "Tre' Harris") must normalise
    identically to the index's apostrophe-free roster spelling ("Tre
    Harris")."""

    def test_straight_apostrophe_stripped(self):
        assert _normalise("Ja'Marr Chase") == "jamarr chase"

    def test_curly_apostrophe_stripped(self):
        assert _normalise("Ja’Marr Chase") == "jamarr chase"

    def test_trailing_apostrophe_matches_no_apostrophe_variant(self):
        # The exact bug from the forward-gate bridge session: "Tre' Harris"
        # (apostrophe typo/variant) must normalise the same as "Tre Harris".
        assert _normalise("Tre' Harris") == _normalise("Tre Harris")


class TestNicknameMapDeadEntries:
    """_NICKNAME_MAP entries whose VALUE contains punctuation (periods) were
    dead: _normalise() strips periods from index keys, but the raw mapped
    value was used as the lookup key unnormalised, so it could never match
    any index key. Fixed by re-normalising the mapped value."""

    @pytest.mark.parametrize(
        "queried_name,expected_pid",
        [
            ("AJ Brown", "00-1111111"),
            ("aj brown", "00-1111111"),
            ("DJ Moore", "00-2222222"),
            ("DJ Chark", "00-3333333"),
        ],
    )
    def test_nickname_resolves_to_dotted_full_name_entry(
        self, nickname_bronze_root, queried_name, expected_pid
    ):
        resolver = PlayerNameResolver(bronze_root=nickname_bronze_root)
        assert resolver.resolve(queried_name) == expected_pid

    def test_nickname_map_values_normalise_to_existing_index_keys(self):
        """Sanity check on the map itself: every mapped value, once
        normalised, should be a plausible (non-empty, dot-free) key -- this
        would have caught the dead entries directly."""
        from player_name_resolver import _NICKNAME_MAP

        for key, value in _NICKNAME_MAP.items():
            normalised_value = _normalise(value)
            assert normalised_value, f"{key!r} maps to an empty normalised value"
            assert "." not in normalised_value, (
                f"{key!r} -> {value!r} still contains a period after "
                f"re-normalisation ({normalised_value!r}) -- would never match "
                "an index key"
            )


class TestApostropheResolutionEndToEnd:
    def test_apostrophe_variant_resolves_against_apostrophe_free_roster(
        self, nickname_bronze_root
    ):
        resolver = PlayerNameResolver(bronze_root=nickname_bronze_root)
        assert resolver.resolve("Tre' Harris") == "00-4444444"
