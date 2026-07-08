"""
Tests for the trailing-window sentiment pulse (News tab, 2026-07):
GET /api/news/top-stories and GET /api/news/sentiment-rankings.

Service-level tests use synthetic Silver signal records via monkeypatching
so they are independent of what the live pipeline last ingested; the API
integration tests only assert envelope shape against real local data.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from web.api.main import app  # noqa: E402
from web.api.services import news_service  # noqa: E402

client = TestClient(app)


def _rec(
    name,
    score,
    hours_ago,
    player_id="00-000001",
    doc_id=None,
    confidence=0.8,
    events=None,
):
    published = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "doc_id": doc_id or f"https://example.com/{name.replace(' ', '-')}-{hours_ago}",
        "source": "pft",
        "player_name": name,
        "player_id": player_id,
        "sentiment_score": score,
        "sentiment_confidence": confidence,
        "category": "general",
        "events": events or {},
        "published_at": published.isoformat(),
        "raw_excerpt": f"{name} headline\n\nBody text about {name}.",
    }


def _patch_records(monkeypatch, records):
    def fake_loader(days):
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        out = []
        for rec in records:
            published = news_service._parse_published_at(rec["published_at"])
            if published and published >= cutoff:
                rec = dict(rec)
                rec["_published_dt"] = published
                out.append(rec)
        return out

    monkeypatch.setattr(news_service, "_load_recent_signal_records", fake_loader)


class TestTopStories:
    def test_window_filters_and_ranks(self, monkeypatch):
        _patch_records(
            monkeypatch,
            [
                _rec("Fresh Big", -0.9, hours_ago=2),
                _rec("Stale Big", -0.9, hours_ago=24 * 20),
                _rec("Fresh Small", 0.1, hours_ago=3, confidence=0.4),
            ],
        )
        out = news_service.get_top_stories("week", limit=10)
        titles = [s["title"] for s in out["stories"]]
        assert "Fresh Big headline" in titles[0]
        assert all("Stale Big" not in (t or "") for t in titles)

    def test_event_flag_boosts_story(self, monkeypatch):
        _patch_records(
            monkeypatch,
            [
                _rec("Mild News", 0.2, hours_ago=1),
                _rec(
                    "Ruled Out Guy",
                    -0.2,
                    hours_ago=1,
                    events={"is_ruled_out": True},
                ),
            ],
        )
        out = news_service.get_top_stories("day", limit=2)
        assert out["stories"][0]["title"].startswith("Ruled Out Guy")
        assert "Ruled Out" in out["stories"][0]["event_flags"]

    def test_dedupes_by_doc_id(self, monkeypatch):
        _patch_records(
            monkeypatch,
            [
                _rec("Dup", 0.5, hours_ago=1, doc_id="https://x.com/a"),
                _rec("Dup", 0.9, hours_ago=1, doc_id="https://x.com/a"),
            ],
        )
        out = news_service.get_top_stories("day", limit=10)
        assert out["story_count"] == 1
        assert out["stories"][0]["sentiment"] == 0.9

    def test_url_derived_from_http_doc_id(self, monkeypatch):
        _patch_records(monkeypatch, [_rec("Linky", 0.5, 1, doc_id="https://x.com/b")])
        out = news_service.get_top_stories("day")
        assert out["stories"][0]["url"] == "https://x.com/b"


class TestSentimentRankings:
    def test_risers_and_fallers_split(self, monkeypatch):
        _patch_records(
            monkeypatch,
            [
                _rec("Up Guy", 0.6, 2, player_id="00-1"),
                _rec("Up Guy", 0.4, 5, player_id="00-1"),
                _rec("Down Guy", -0.7, 3, player_id="00-2"),
            ],
        )
        out = news_service.get_sentiment_rankings("week", limit=5)
        assert [r["player_name"] for r in out["risers"]] == ["Up Guy"]
        assert out["risers"][0]["doc_count"] == 2
        assert out["risers"][0]["label"] == "bullish"
        assert [r["player_name"] for r in out["fallers"]] == ["Down Guy"]
        assert out["fallers"][0]["label"] == "bearish"

    def test_unresolved_entities_excluded(self, monkeypatch):
        _patch_records(
            monkeypatch,
            [
                _rec("The Lions", -0.5, 2, player_id=None),
                _rec("Real Player", 0.5, 2, player_id="00-3"),
            ],
        )
        out = news_service.get_sentiment_rankings("week")
        names = [r["player_name"] for r in out["risers"] + out["fallers"]]
        assert "The Lions" not in names
        assert "Real Player" in names

    def test_confidence_weighted_average(self, monkeypatch):
        _patch_records(
            monkeypatch,
            [
                _rec("Weighted", 1.0, 1, player_id="00-4", confidence=0.9),
                _rec("Weighted", 0.0, 1, player_id="00-4", confidence=0.1),
            ],
        )
        out = news_service.get_sentiment_rankings("week")
        assert out["risers"][0]["avg_sentiment"] == 0.9


class TestPulseEndpoints:
    def test_top_stories_envelope(self):
        r = client.get("/api/news/top-stories", params={"window": "month"})
        assert r.status_code == 200
        body = r.json()
        assert body["window"] == "month"
        assert isinstance(body["stories"], list)

    def test_rankings_envelope(self):
        r = client.get("/api/news/sentiment-rankings", params={"window": "month"})
        assert r.status_code == 200
        body = r.json()
        assert "risers" in body and "fallers" in body

    def test_invalid_window_422(self):
        r = client.get("/api/news/top-stories", params={"window": "year"})
        assert r.status_code == 422


class TestTopStoriesEnrichment:
    """Top stories must surface LLM sidecar summaries across season/week
    boundaries — offseason docs are enriched under the prior season's last
    week while the current season is one ahead (2026-07-08 gap: enrichment
    ran daily but every top-story summary served as None)."""

    def test_summary_attached_from_cross_season_sidecar(
        self, monkeypatch, tmp_path
    ):
        import json as _json

        doc_id = "https://x.com/enriched-story"
        _patch_records(
            monkeypatch, [_rec("Enriched Guy", -0.8, hours_ago=2, doc_id=doc_id)]
        )
        # Sidecar lives under LAST season's final week, not the current one.
        week_dir = tmp_path / "season=2025" / "week=18"
        week_dir.mkdir(parents=True)
        (week_dir / "enriched_test_20260708_000000.json").write_text(
            _json.dumps(
                {
                    "records": [
                        {
                            "doc_id": doc_id,
                            "summary": "Enriched Guy is dealing with a setback.",
                            "refined_category": "injury",
                        }
                    ]
                }
            )
        )
        monkeypatch.setattr(news_service, "_SILVER_ENRICHED_DIR", tmp_path)

        out = news_service.get_top_stories("day", limit=5)
        story = out["stories"][0]
        assert story["summary"] == "Enriched Guy is dealing with a setback."
        assert story["category"] == "injury"

    def test_no_sidecar_tree_degrades_gracefully(self, monkeypatch, tmp_path):
        _patch_records(monkeypatch, [_rec("Plain Guy", 0.5, hours_ago=1)])
        monkeypatch.setattr(
            news_service, "_SILVER_ENRICHED_DIR", tmp_path / "does-not-exist"
        )
        out = news_service.get_top_stories("day", limit=5)
        assert out["stories"][0]["summary"] is None

    def test_inline_claude_primary_summary_surfaces(self, monkeypatch, tmp_path):
        # claude_primary extraction writes the summary inline on the Silver
        # record (sidecar enrichment is skipped for those envelopes); the
        # news item builder must honor it instead of hardcoding None.
        rec = _rec("Primary Guy", -0.6, hours_ago=1)
        rec["summary"] = "Primary Guy summary from claude_primary extraction."
        _patch_records(monkeypatch, [rec])
        monkeypatch.setattr(
            news_service, "_SILVER_ENRICHED_DIR", tmp_path / "no-sidecars"
        )
        out = news_service.get_top_stories("day", limit=5)
        assert (
            out["stories"][0]["summary"]
            == "Primary Guy summary from claude_primary extraction."
        )
