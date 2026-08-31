"""Offline tests for the VORP-based MARKET vs MODEL insights (task 1) and the
keyword NEWS advisory guard (task 2) in ``src.draft_value``.

Panel fix: the live MARKET vs MODEL panel ranked by raw projected points, so
QBs dominated (Josh Allen "VALUE", Gibbs at ADP 1 "BUST").
``compute_market_insights`` ranks by VORP instead, so a positional #1 at ADP 1
is never a scarcity-artifact BUST.

NEWS aperture: ``load_roster_status`` only sees Sleeper roster designations, so
suspensions/legal risk were invisible (zero NEWS tags in a live mock while a
real Josh Jacobs legal risk went undetected). ``load_news_risk`` scans the
ingested Bronze sentiment feeds for risk keywords and emits ADVISORY tags.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import pytest

import src.draft_value as draft_value
from src.draft_value import (
    attach_features,
    compute_market_insights,
    label_board,
    load_news_risk,
    summarize,
)

NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Task 1 — MARKET vs MODEL panel ranks by VORP, not raw points
# ---------------------------------------------------------------------------


def _panel_board() -> pd.DataFrame:
    """The exact failure mode from the live mock: QBs top the raw-points
    board, but the elite RB carries the most value over replacement."""
    rows = [
        # name, pos, points, vorp, adp
        ("Josh Allen", "QB", 380.0, 62.0, 25),  # raw-points #1, mid VORP
        ("Mid QB", "QB", 340.0, 20.0, 150),
        ("Jahmyr Gibbs", "RB", 290.0, 110.0, 1),  # positional #1, ADP 1
        ("Elite WR", "WR", 280.0, 95.0, 3),
        ("Good RB", "RB", 240.0, 61.0, 20),
        ("Fair WR", "WR", 220.0, 35.0, 30),
        ("Value TE", "TE", 180.0, 55.0, 70),  # VBD well ahead of ADP
        ("Kicker", "K", 150.0, 10.0, 160),
    ]
    # Depth fillers so ranks behave like a real board: 8 RB/WRs whose VORP
    # sits between Allen's and the elite tier (raw points all below Allen's).
    for i in range(8):
        rows.append(
            (f"Filler {i}", "RB" if i % 2 else "WR", 250.0 - i, 90.0 - 3 * i, 4 + i)
        )
    df = pd.DataFrame(
        rows,
        columns=[
            "player_name",
            "position",
            "projected_season_points",
            "vorp",
            "adp_rank",
        ],
    )
    # Raw-points model_rank, exactly as compute_value_scores emits it.
    df["model_rank"] = (
        df["projected_season_points"].rank(ascending=False, method="first").astype(int)
    )
    return df


@pytest.mark.unit
def test_positional_number_one_at_adp_1_is_never_a_bust():
    # Old panel: Gibbs model_rank (raw points) ~4 vs ADP 1 -> "room reaches
    # 3 spots early" -> BUST for pure scarcity reasons. VBD rank kills that.
    out = compute_market_insights(_panel_board(), on_clock_pick=1)
    bust_names = {r["player_name"] for r in out["busts"]}
    assert "Jahmyr Gibbs" not in bust_names
    # And Gibbs' model rank is now his VBD rank (#1), not a raw-points rank.
    all_rows = out["values"] + out["busts"]
    for r in all_rows:
        if r["player_name"] == "Jahmyr Gibbs":
            assert r["model_rank"] == 1


@pytest.mark.unit
def test_qb_raw_points_dominance_gone():
    # Josh Allen is raw-points #1 but only mid-VORP: he must NOT rank #1 on
    # the model side, and he is NOT a VALUE at ADP 25 (gap < 15 on VBD board).
    out = compute_market_insights(_panel_board(), on_clock_pick=1)
    value_names = {r["player_name"] for r in out["values"]}
    assert "Josh Allen" not in value_names
    for r in out["values"] + out["busts"]:
        if r["player_name"] == "Josh Allen":
            assert r["model_rank"] > 1
    # The true VBD value (TE ranked ~5 by VORP, ADP 70) surfaces instead.
    assert "Value TE" in value_names


@pytest.mark.unit
def test_market_insights_bust_requires_adp_within_horizon():
    # "Reach RB": VBD rank ~62 but the room drafts him at ADP 40 -> a bust
    # ONLY once the clock is close enough that the market will actually take
    # him (ADP within ~3 rounds of the pick).
    rows = [("Stud", "RB", 300.0, 100.0, 1), ("Reach RB", "RB", 150.0, 1.0, 40)]
    rows += [(f"WR {i}", "WR", 250.0 - i, 90.0 - i, 100 + i) for i in range(60)]
    df = pd.DataFrame(
        rows,
        columns=[
            "player_name",
            "position",
            "projected_season_points",
            "vorp",
            "adp_rank",
        ],
    )
    near = compute_market_insights(df, on_clock_pick=10)
    far = compute_market_insights(df, on_clock_pick=None)
    assert "Reach RB" in {r["player_name"] for r in near["busts"]}
    assert "Reach RB" not in {r["player_name"] for r in far["busts"]}


@pytest.mark.unit
def test_market_insights_skips_positions_and_fails_soft():
    board = _panel_board()
    out = compute_market_insights(board, skip_positions={"TE"})
    assert all(r["position"] != "TE" for r in out["values"] + out["busts"])
    # K never enters the VBD board.
    assert all(r["position"] != "K" for r in out["values"] + out["busts"])
    # Missing columns / empty frames -> empty result, no crash.
    assert compute_market_insights(None) == {"values": [], "busts": []}
    assert compute_market_insights(pd.DataFrame()) == {"values": [], "busts": []}
    assert compute_market_insights(board.drop(columns=["vorp"])) == {
        "values": [],
        "busts": [],
    }


# ---------------------------------------------------------------------------
# Task 2 — keyword NEWS advisories from the Bronze sentiment feeds
# ---------------------------------------------------------------------------


class _StubResolver:
    """PlayerNameResolver stand-in: knows only current players."""

    def __init__(self, known):
        self._known = {k.lower() for k in known}

    def resolve(self, name, team=None, position=None):
        return "00-TEST" if str(name).lower() in self._known else None


def _write_feed(root, source, season, fname, items):
    d = os.path.join(root, source, f"season={season}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, fname), "w", encoding="utf-8") as fh:
        json.dump({"source": source, "items": items}, fh)


def _news_root(tmp_path):
    root = str(tmp_path / "sentiment")
    _write_feed(
        root,
        "rss",
        2026,
        "rss_test_20260828_120000.json",
        [
            {
                "title": "Josh Jacobs suspended six games by the NFL",
                "body_text": "The league announced the suspension Tuesday.",
                "candidate_names": ["Josh Jacobs"],
                "published_at": "2026-08-27T15:00:00+00:00",
            },
            {
                "title": "Training camp notes: depth chart battles",
                "body_text": "No risk words here at all.",
                "candidate_names": ["Clean Player"],
                "published_at": "2026-08-27T16:00:00+00:00",
            },
            {
                # Retired name-sake: resolver does not know him -> no tag.
                "title": "Ray Rice arrested years after retirement",
                "body_text": "A look back.",
                "candidate_names": ["Ray Rice"],
                "published_at": "2026-08-26T10:00:00+00:00",
            },
        ],
    )
    # Stale file: outside the window entirely, filename-dated.
    _write_feed(
        root,
        "rss",
        2026,
        "rss_test_20260501_120000.json",
        [
            {
                "title": "Old Player suspended indefinitely",
                "body_text": "",
                "candidate_names": ["Old Player"],
                "published_at": "2026-05-01T10:00:00+00:00",
            }
        ],
    )
    return root


@pytest.mark.unit
def test_keyword_scan_finds_planted_suspension(tmp_path):
    root = _news_root(tmp_path)
    resolver = _StubResolver(["Josh Jacobs", "Old Player"])
    out = load_news_risk(days=14, now=NOW, root=root, resolver=resolver)
    from src.draft_optimizer import name_key

    jacobs = name_key("Josh Jacobs")  # nickname-canonical, same as board keys
    assert jacobs in set(out["_name_key"])
    row = out[out["_name_key"] == jacobs].iloc[0]
    assert "suspen" in row["news_keyword"]
    assert row["news_date"] == "2026-08-27"
    # Clean item never fires; stale file (outside 14 days) never fires.
    assert "clean player" not in set(out["_name_key"])
    assert "old player" not in set(out["_name_key"])


@pytest.mark.unit
def test_namesake_collision_guard_holds(tmp_path):
    # The resolver only knows CURRENT players — a retired name-sake in the
    # news must never produce a tag that could attach to an active player.
    root = _news_root(tmp_path)
    out = load_news_risk(
        days=14, now=NOW, root=root, resolver=_StubResolver(["Josh Jacobs"])
    )
    assert "ray rice" not in set(out["_name_key"])


@pytest.mark.unit
def test_missing_sentiment_dir_fails_soft(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="src.draft_value"):
        out = load_news_risk(
            days=14, now=NOW, root=str(tmp_path / "nope"), resolver=_StubResolver([])
        )
    assert out.empty
    assert list(out.columns) == ["_name_key", "news_keyword", "news_date"]
    assert any("NEWS advisories" in r.message for r in caplog.records)


@pytest.mark.unit
def test_corrupt_feed_file_fails_soft(tmp_path):
    root = str(tmp_path / "sentiment")
    d = os.path.join(root, "rss", "season=2026")
    os.makedirs(d)
    with open(os.path.join(d, "rss_bad_20260828_120000.json"), "w") as fh:
        fh.write("{not json")
    out = load_news_risk(days=14, now=NOW, root=root, resolver=_StubResolver([]))
    assert out.empty


@pytest.mark.unit
def test_roundup_articles_are_skipped(tmp_path):
    # A 20-name listicle mentioning "injury" must not tag all 20 players.
    root = str(tmp_path / "sentiment")
    names = [f"Player Number{i}" for i in range(20)]
    _write_feed(
        root,
        "rss",
        2026,
        "rss_test_20260828_120000.json",
        [
            {
                "title": "Injury roundup: 20 players to watch",
                "body_text": "injury injury injury",
                "candidate_names": names,
                "published_at": "2026-08-27T15:00:00+00:00",
            }
        ],
    )
    out = load_news_risk(days=14, now=NOW, root=root, resolver=_StubResolver(names))
    assert out.empty


@pytest.mark.unit
def test_sleeper_items_use_player_name(tmp_path):
    root = str(tmp_path / "sentiment")
    _write_feed(
        root,
        "sleeper",
        2026,
        "sleeper_news_20260828_120000.json",
        [
            {
                "player_name": "Holdout Back",
                "position": "RB",
                "news_body": "Continues to hold out of training camp.",
                "news_date": "2026-08-26T10:00:00+00:00",
            }
        ],
    )
    out = load_news_risk(
        days=14, now=NOW, root=root, resolver=_StubResolver(["Holdout Back"])
    )
    assert "holdout back" in set(out["_name_key"])


# ---------------------------------------------------------------------------
# Advisory merge semantics: tag, never hard-exclude
# ---------------------------------------------------------------------------


def _labeled_board_with_news(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # all real feature loaders fail soft -> empty
    news = pd.DataFrame(
        [
            {
                "_name_key": "value back",
                "news_keyword": "suspension",
                "news_date": "2026-08-27",
            }
        ]
    )
    monkeypatch.setattr(draft_value, "load_news_risk", lambda **kw: news)
    board = pd.DataFrame(
        [
            ("Value Back", "RB", 60.0, 40, 220.0),
            ("Fair WR", "WR", 40.0, 30, 180.0),
        ],
        columns=[
            "player_name",
            "position",
            "vorp",
            "adp_rank",
            "projected_season_points",
        ],
    )
    board["model_rank"] = (
        board["projected_season_points"]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    return label_board(attach_features(board, 2026))


@pytest.mark.unit
def test_news_advisory_tags_but_does_not_hard_exclude(monkeypatch, tmp_path):
    out = _labeled_board_with_news(monkeypatch, tmp_path).set_index("player_name")
    row = out.loc["Value Back"]
    assert row["news_risk"] == "suspension 2026-08-27"
    assert "[NEWS: suspension 2026-08-27]" in row["reasons"]
    # ADVISORY: unlike roster-status news, the value flag survives (§36 needs
    # the tag to surface; a keyword match alone is not a hard exclusion).
    assert bool(row["flag_value"])
    assert not bool(row["flag_bust"])
    assert pd.isna(out.loc["Fair WR", "news_risk"])


@pytest.mark.unit
def test_news_advisory_shows_in_summary_and_tag_players(monkeypatch, tmp_path):
    lab = _labeled_board_with_news(monkeypatch, tmp_path)
    s = summarize(lab)
    assert "news_risk" in s["values"].columns
    assert "Value Back" in set(s["values"]["player_name"])
    from src.draft_targets import tag_players

    tags = tag_players(lab, my_guys=[], fades=[])
    assert "NEWS:suspension" in tags["value back"]
    assert "VALUE" in tags["value back"]


@pytest.mark.unit
def test_roster_status_hard_exclusion_unchanged(monkeypatch, tmp_path):
    # The Sleeper roster-designation guard keeps its hard semantics even with
    # the keyword source merged in: non-Active -> bust-tagged, never VALUE.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        draft_value,
        "load_news_risk",
        lambda **kw: pd.DataFrame(columns=["_name_key", "news_keyword", "news_date"]),
    )
    status = pd.DataFrame(
        [{"_name_key": "value back", "position": "RB", "roster_status": "Suspended"}]
    )
    monkeypatch.setattr(draft_value, "load_roster_status", lambda season: status)
    board = pd.DataFrame(
        [("Value Back", "RB", 60.0, 40, 220.0)],
        columns=[
            "player_name",
            "position",
            "vorp",
            "adp_rank",
            "projected_season_points",
        ],
    )
    board["model_rank"] = 1
    out = label_board(attach_features(board, 2026)).set_index("player_name")
    row = out.loc["Value Back"]
    assert bool(row["flag_bust"])
    assert not bool(row["flag_value"])
    assert "(NEWS) roster status: Suspended" in row["reasons"]
