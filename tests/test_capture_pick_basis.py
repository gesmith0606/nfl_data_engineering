"""Line capture must be measured against the price the pick was made at.

`run_line_capture_backtest` used to re-assign the pick side against the open
proxy:

    has_open & (joined["predicted_margin"] > -joined["open_spread"])

so the harness pretended we bet in June, at the June price, with a model run in
October. Any model merely better informed than a stale line picks whatever side
the market later moved toward, and gets paid for the market's own learning.
Simulated on the 93 settled 2026 games, a model with **no edge at all** scored
+2.277 mean capture; one with 8 points of error — worse than reading the line
off the board — still scored +0.923. The gate asks for +0.3, so it could not
fail.

Two things had to change together:

1. The pick side comes from the board we published (`_attach_published_picks`),
   never from the price being measured against.
2. The open must be a betting-week price (`open_within_days=7`), not the first
   snapshot ever captured — a median 109 days before kickoff.

With both in place the first honest reading of 2026 week 7 is **-1.071 pts on
14 picks**, where the stale-open wiring had reported +1.26 season-to-date.

See `.planning/OPEN_PROXY_VALIDATION_2026_10_25.md`.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

import backtest_predictions as bp  # noqa: E402

BACKTEST_SRC = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "backtest_predictions.py"
)


def _write_board(root, season, week, rows, stamp="20261020_090000"):
    """Write a Gold prediction board the way generate_predictions.py does."""
    week_dir = os.path.join(root, f"season={season}", f"week={week:02d}")
    os.makedirs(week_dir, exist_ok=True)
    path = os.path.join(week_dir, f"predictions_{stamp}.parquet")
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


@pytest.fixture()
def board_root(tmp_path, monkeypatch):
    root = tmp_path / "predictions"
    root.mkdir()
    monkeypatch.setattr(bp, "_GOLD_PREDICTIONS_DIR", str(root))
    return str(root)


class TestLoadPublishedPicks:
    def test_pick_side_comes_from_the_board(self, board_root):
        _write_board(
            board_root,
            2026,
            7,
            [
                {"game_id": "2026_07_A_B", "ats_pick": "B", "home_team": "B"},
                {"game_id": "2026_07_C_D", "ats_pick": "C", "home_team": "D"},
            ],
        )
        picks = bp._load_published_picks([2026]).set_index("game_id")["pick_side"]
        assert picks["2026_07_A_B"] == "home"  # ats_pick == home_team
        assert picks["2026_07_C_D"] == "away"  # ats_pick is the away side

    def test_blank_ats_pick_publishes_no_side(self, board_root):
        """A suppressed pick must not become a side. It is not a pick."""
        _write_board(
            board_root,
            2026,
            7,
            [
                {"game_id": "2026_07_A_B", "ats_pick": "", "home_team": "B"},
                {"game_id": "2026_07_C_D", "ats_pick": "D", "home_team": "D"},
            ],
        )
        picks = bp._load_published_picks([2026])
        # Non-vacuity: the fixture really does carry one blank and one real pick.
        assert len(picks) == 1
        assert picks.iloc[0]["game_id"] == "2026_07_C_D"

    def test_newest_board_in_a_week_wins(self, board_root):
        _write_board(
            board_root, 2026, 7,
            [{"game_id": "2026_07_A_B", "ats_pick": "B", "home_team": "B"}],
            stamp="20261020_090000",
        )
        _write_board(
            board_root, 2026, 7,
            [{"game_id": "2026_07_A_B", "ats_pick": "A", "home_team": "B"}],
            stamp="20261021_090000",
        )
        picks = bp._load_published_picks([2026]).set_index("game_id")["pick_side"]
        assert picks["2026_07_A_B"] == "away", "the later board should win"

    def test_no_boards_returns_empty_with_the_right_columns(self, board_root):
        picks = bp._load_published_picks([2026])
        assert picks.empty
        assert list(picks.columns) == ["game_id", "pick_side"]

    def test_a_board_without_ats_pick_is_skipped(self, board_root):
        _write_board(
            board_root, 2026, 7,
            [{"game_id": "2026_07_A_B", "home_team": "B", "predicted_spread": 1.0}],
        )
        assert bp._load_published_picks([2026]).empty


class TestAttachPublishedPicks:
    def _games(self):
        return pd.DataFrame(
            {
                "game_id": ["2026_07_A_B", "2026_07_C_D"],
                "season": [2026, 2026],
                "predicted_margin": [7.0, 7.0],
                "open_spread": [-1.0, -1.0],
            }
        )

    def test_rows_without_a_published_pick_are_dropped(self, board_root, capsys):
        _write_board(
            board_root, 2026, 7,
            [{"game_id": "2026_07_A_B", "ats_pick": "B", "home_team": "B"}],
        )
        games = self._games()
        # Non-vacuity: two games in, only one of them on the board.
        assert len(games) == 2
        out = bp._attach_published_picks(games, label="test")
        assert list(out["game_id"]) == ["2026_07_A_B"]
        assert "Dropped 1 game(s) with no published pick" in capsys.readouterr().out

    def test_pick_side_is_the_boards_not_rederived_from_the_open(self, board_root):
        """The regression this whole change exists to prevent.

        The board published the AWAY side. Re-deriving from the open
        (``predicted_margin > -open_spread`` → 7.0 > 1.0 → home) would say HOME.
        The board must win.
        """
        _write_board(
            board_root, 2026, 7,
            [{"game_id": "2026_07_A_B", "ats_pick": "A", "home_team": "B"}],
        )
        games = self._games().head(1)
        # Non-vacuity: the open-derived pick really would disagree.
        assert (games["predicted_margin"] > -games["open_spread"]).all()
        out = bp._attach_published_picks(games)
        assert out["pick_side"].tolist() == ["away"]

    def test_no_boards_yields_an_empty_frame_carrying_pick_side(
        self, board_root, capsys
    ):
        out = bp._attach_published_picks(self._games(), label="test")
        assert out.empty
        assert "pick_side" in out.columns
        assert "No published boards found" in capsys.readouterr().out

    def test_does_not_mutate_the_caller(self, board_root):
        _write_board(
            board_root, 2026, 7,
            [{"game_id": "2026_07_A_B", "ats_pick": "B", "home_team": "B"}],
        )
        games = self._games()
        before = games.copy()
        bp._attach_published_picks(games)
        pd.testing.assert_frame_equal(games, before)


class TestNoBackFittedPickRemains:
    """A source guard, like test_no_unfiltered_assembly_call_remains next door.

    The defect was one specific expression. Behavioural tests cover the helper,
    but only a source check stops the expression itself being reintroduced into
    the capture path by a later edit.
    """

    def test_pick_side_is_never_derived_from_the_open(self):
        src = open(BACKTEST_SRC).read()
        # Strip comments so the explanatory note describing the old defect
        # (which quotes it) does not trip the guard.
        code = "\n".join(
            line for line in src.splitlines() if not line.lstrip().startswith("#")
        )
        assert '-joined["open_spread"]' not in code, (
            "pick_side must not be re-derived against the open — that is what "
            "made the gate unfalsifiable."
        )
        assert "open_edge" not in code, (
            "open_edge recorded the back-fitted pick's basis and has no consumer."
        )

    def test_capture_open_is_bounded_to_the_betting_week(self):
        assert bp._CAPTURE_OPEN_WITHIN_DAYS == 7.0
        src = open(BACKTEST_SRC).read()
        assert "open_within_days=_CAPTURE_OPEN_WITHIN_DAYS" in src, (
            "the capture path must pass the horizon to the snapshot loader."
        )
