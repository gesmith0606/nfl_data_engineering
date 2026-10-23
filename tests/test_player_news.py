"""Tests for scripts/player_news.py — read the news, don't count the flags.

Gold sentiment reduces an article to keyword flags and the waiver report shows
only a COUNT of them. For the handful of candidates a claim comes down to, the
articles themselves are the better input, and they are already in Bronze with
``resolved_player_ids`` attached.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _mod(bronze: Path | None = None):
    spec = importlib.util.spec_from_file_location(
        "player_news", REPO / "scripts" / "player_news.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["player_news"] = m
    spec.loader.exec_module(m)
    if bronze is not None:
        m.BRONZE = bronze
    return m


def _write(bronze: Path, name: str, docs: list) -> None:
    bronze.mkdir(parents=True, exist_ok=True)
    (bronze / name).write_text(json.dumps(docs), encoding="utf-8")


def test_the_same_article_from_several_feeds_is_counted_once(tmp_path):
    """One story arrives via rss, pft and a daily recapture."""
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = {
        "external_id": "abc123",
        "title": "Schultz returns to practice",
        "published_at": today,
        "source": "pft",
    }
    pn = _mod(tmp_path)
    _write(tmp_path / "rss", "a.json", [doc])
    _write(tmp_path / "pft", "b.json", [dict(doc)])
    assert len(pn.load_docs(7)) == 1


def test_articles_older_than_the_window_are_left_out(tmp_path):
    pn = _mod(tmp_path)
    _write(
        tmp_path / "rss",
        "a.json",
        [
            {"external_id": "old", "title": "June news", "published_at": "2020-06-01"},
            {"external_id": "bad", "title": "No date", "published_at": "not-a-date"},
        ],
    )
    assert pn.load_docs(7) == []


def test_a_player_is_matched_by_resolved_id_or_by_name(tmp_path):
    """The id path is exact; the name path catches what the ingester missed."""
    pn = _mod(tmp_path)
    docs = [
        {"title": "By id", "resolved_player_ids": ["00-0012345"], "published_at": "x"},
        {"title": "Dalton Schultz returns", "published_at": "x"},
        {
            "title": "Unrelated",
            "candidate_names": ["Someone Else"],
            "published_at": "x",
        },
        {
            "title": "By candidate",
            "candidate_names": ["Dalton Schultz"],
            "published_at": "x",
        },
    ]
    hits = pn.about(docs, ["00-0012345"], "Dalton Schultz")
    assert [h["title"] for h in hits] == [
        "By id",
        "Dalton Schultz returns",
        "By candidate",
    ]


def test_no_news_says_so_rather_than_implying_good_news(tmp_path):
    """Roschon Johnson: 1,355k trending adds, 0 articles in 5 days."""
    pn = _mod(tmp_path)
    assert pn.about([], [], "Roschon Johnson") == []
    src = (REPO / "scripts" / "player_news.py").read_text(encoding="utf-8")
    assert "Silence is not good news; it is no news." in src
