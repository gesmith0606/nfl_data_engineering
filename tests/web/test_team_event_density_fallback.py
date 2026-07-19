"""Team event density — offseason trailing-window fallback (bucket-starvation fix).

July 2026 bug: articles straddle season partition dirs (July stories filed
under season=2025 week=18 while the frontend queries season=2026 week=01),
so the strictly week-bucketed density view rendered a nearly empty grid.
The service now falls back to the trailing 30-day cross-bucket window when
the requested bucket has fewer than 10 records.
"""

from unittest.mock import patch

from web.api.services import news_service


def _windowed_records():
    return [
        {
            "doc_id": "d1",
            "player_id": "P100",
            "events": {"is_ruled_out": True},
            "published_at": "2026-07-18T12:00:00+00:00",
        },
        {
            "doc_id": "d2",
            "player_id": "P100",
            "events": {"is_returning": True},
            "published_at": "2026-07-17T12:00:00+00:00",
        },
        {
            # Direct team attribution via Phase 72 team_abbr — no player_id.
            "doc_id": "d3",
            "player_id": "",
            "team_abbr": "PHI",
            "events": {"is_coaching_change": True},
            "published_at": "2026-07-16T12:00:00+00:00",
        },
        {
            # Unattributable — must be dropped, not crash.
            "doc_id": "d4",
            "player_id": "",
            "events": {"is_traded": True},
            "published_at": "2026-07-15T12:00:00+00:00",
        },
    ]


def test_fallback_fires_when_bucket_starved():
    with (
        patch.object(news_service, "_load_bronze_records", return_value=[]),
        patch.object(news_service, "_find_bronze_files_for_season", return_value=[]),
        patch.object(news_service, "_find_silver_files", return_value=[]),
        patch.object(news_service, "_load_silver_records", return_value=[]),
        patch.object(
            news_service, "_load_recent_signal_records", return_value=_windowed_records()
        ),
        patch.object(
            news_service, "_player_id_team_map", return_value={"P100": "DET"}
        ),
    ):
        rows = news_service.get_team_event_density(season=2026, week=1)

    assert len(rows) == 32
    by_team = {r["team"]: r for r in rows}
    assert by_team["DET"]["total_articles"] == 2
    assert by_team["PHI"]["total_articles"] == 1
    attributed = sum(r["total_articles"] for r in rows)
    assert attributed == 3  # d4 dropped — unattributable


def test_fallback_skipped_when_bucket_is_rich():
    rich_bucket = [
        {"doc_id": f"d{i}", "player_id": "P200", "events": {"is_signed": True}}
        for i in range(12)
    ]
    with (
        patch.object(news_service, "_load_bronze_records", return_value=[]),
        patch.object(news_service, "_find_bronze_files_for_season", return_value=[]),
        patch.object(news_service, "_find_silver_files", return_value=[]),
        patch.object(news_service, "_load_silver_records", return_value=rich_bucket),
        patch.object(
            news_service, "_build_player_id_to_team", return_value={"P200": "KC"}
        ),
        patch.object(news_service, "_load_recent_signal_records") as windowed,
    ):
        rows = news_service.get_team_event_density(season=2026, week=1)

    windowed.assert_not_called()
    by_team = {r["team"]: r for r in rows}
    assert by_team["KC"]["total_articles"] == 12
