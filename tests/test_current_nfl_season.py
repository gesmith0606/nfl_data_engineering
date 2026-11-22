"""January: the NFL season is not the calendar year (weeks 17-18 + playoffs)."""

from datetime import datetime, timezone

import pytest

from web.api import config
from web.api.services import projection_service


def _at(y, m, d):
    return datetime(y, m, d, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "when, expected",
    [
        (_at(2026, 11, 21), 2026),
        (_at(2027, 1, 5), 2026),
        (_at(2027, 2, 28), 2026),
        (_at(2027, 3, 1), 2027),
        (_at(2026, 8, 10), 2026),
    ],
)
def test_current_nfl_season(when, expected):
    assert config.current_nfl_season(when) == expected


def test_fallback_protection_stays_on_for_the_season_being_played_in_january(
    monkeypatch,
):
    # 2027-01-05: season 2026 is in week 18. It must still count as current,
    # otherwise the stale-weekly-file / not-published handling switches off.
    monkeypatch.setattr(projection_service, "current_nfl_season", lambda: 2026)
    assert projection_service._should_apply_fallback(2026) is True
    assert projection_service._should_apply_fallback(2027) is True
    assert projection_service._should_apply_fallback(2025) is False


def test_sleeper_default_season_is_the_nfl_season(monkeypatch):
    from web.api.routers import sleeper_user

    monkeypatch.setattr(config, "current_nfl_season", lambda now=None: 2026)
    assert sleeper_user._current_year() == 2026


def test_yahoo_leagues_default_season_is_the_nfl_season(monkeypatch):
    from web.api.routers import yahoo

    seen = {}
    monkeypatch.setattr(config, "current_nfl_season", lambda now=None: 2026)
    monkeypatch.setattr(yahoo, "_require_connected", lambda: object())
    monkeypatch.setattr(
        yahoo,
        "_user_league_candidates",
        lambda season, oauth: seen.setdefault("season", season) and [],
    )
    assert yahoo.yahoo_leagues(season=None) == []
    assert seen["season"] == "2026"
