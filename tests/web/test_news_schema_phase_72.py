"""Pydantic schema contract tests for Phase 72 NewsItem + TeamEvents extensions."""

from __future__ import annotations

import pytest

from web.api.models.schemas import NewsItem, TeamEvents
from web.api.services.news_service import EVENT_LABELS, _extract_event_flags


class TestNewsItemSchemaPhase72:
    def test_subject_type_defaults_to_player(self):
        item = NewsItem(source="rss_espn")
        assert item.subject_type == "player"

    def test_team_abbr_defaults_to_none(self):
        item = NewsItem(source="rss_espn")
        assert item.team_abbr is None

    def test_subject_type_accepts_coach(self):
        item = NewsItem(source="rotowire", subject_type="coach", team_abbr="KC")
        assert item.subject_type == "coach"
        assert item.team_abbr == "KC"

    def test_subject_type_accepts_team(self):
        item = NewsItem(source="rss_nfl", subject_type="team", team_abbr="DAL")
        assert item.subject_type == "team"

    def test_subject_type_accepts_reporter(self):
        item = NewsItem(source="twitter", subject_type="reporter")
        assert item.subject_type == "reporter"

    def test_subject_type_rejects_invalid_literal(self):
        with pytest.raises((ValueError, Exception)):
            NewsItem(source="rss", subject_type="agent")  # not in Literal

    def test_no_top_level_is_drafted_field(self):
        """Per CONTEXT Phase 72 Schema Note: 7 new flags live ONLY in event_flags list."""
        item = NewsItem(source="rss")
        # New flags must NOT exist as top-level attributes.
        for flag in (
            "is_drafted",
            "is_rumored_destination",
            "is_coaching_change",
            "is_trade_buzz",
            "is_holdout",
            "is_cap_cut",
            "is_rookie_buzz",
        ):
            assert not hasattr(item, flag), (
                f"NewsItem must NOT have {flag} as top-level attribute "
                f"(per CONTEXT Phase 72 Schema Note — flags live in event_flags list)"
            )

    def test_event_flags_carries_new_label_strings(self):
        item = NewsItem(
            source="rss_espn",
            event_flags=["Drafted", "Coaching Change", "Holdout"],
        )
        assert "Drafted" in item.event_flags
        assert "Coaching Change" in item.event_flags
        assert "Holdout" in item.event_flags


class TestTeamEventsSchemaPhase72:
    def test_coach_news_count_defaults_zero(self):
        te = TeamEvents(team="KC")
        assert te.coach_news_count == 0
        assert te.team_news_count == 0
        assert te.staff_news_count == 0

    def test_coach_news_count_accepts_int(self):
        te = TeamEvents(team="KC", coach_news_count=3, team_news_count=2)
        assert te.coach_news_count == 3
        assert te.team_news_count == 2


class TestEventLabelsExtended:
    def test_event_labels_has_19_entries(self):
        """12 existing + 7 new draft-season flags."""
        assert len(EVENT_LABELS) == 19

    def test_all_7_new_flags_have_labels(self):
        new_flags = {
            "is_drafted": "Drafted",
            "is_rumored_destination": "Rumored Destination",
            "is_coaching_change": "Coaching Change",
            "is_trade_buzz": "Trade Buzz",
            "is_holdout": "Holdout",
            "is_cap_cut": "Cap Cut",
            "is_rookie_buzz": "Rookie Buzz",
        }
        for flag, label in new_flags.items():
            assert EVENT_LABELS.get(flag) == label

    def test_extract_event_flags_emits_new_labels(self):
        events = {
            "is_drafted": True,
            "is_coaching_change": True,
            "is_holdout": False,
        }
        labels = _extract_event_flags(events)
        assert "Drafted" in labels
        assert "Coaching Change" in labels
        assert "Holdout" not in labels

    def test_event_labels_appended_after_existing(self):
        """New flags MUST appear after the 12 existing ones (preserves grouping)."""
        keys = list(EVENT_LABELS.keys())
        # Last 7 keys must be the new ones (in declared order)
        new_order = [
            "is_drafted",
            "is_rumored_destination",
            "is_coaching_change",
            "is_trade_buzz",
            "is_holdout",
            "is_cap_cut",
            "is_rookie_buzz",
        ]
        assert keys[-7:] == new_order
