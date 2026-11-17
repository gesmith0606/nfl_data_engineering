"""The claims file is the top of the ranked list, each with its drop."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", Path(__file__).resolve().parent.parent / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)


def _rows():
    mk = lambda name, verdict, bid, blend, score, **kw: {  # noqa: E731
        "name": name,
        "verdict": verdict,
        "bid": (bid, "why"),
        "blend": blend,
        "score": score,
        "gain4": kw.get("gain4", 0.0),
        "bye": kw.get("bye", False),
        "dyn": kw.get("dyn", 900),
    }
    return [
        mk("Alpha", "STARTS", 3, 9.0, 5.0, gain4=5.0),
        mk(
            "Bravo", "no help", 2, 4.0, 40.0
        ),  # a young asset: no lineup gain, big dynasty value
        mk("Charlie", "BENCH+", 1, 12.0, 2.0, gain4=2.0),
        mk("Delta", "STARTS", 1, 30.0, 99.0, bye=True),  # on a bye: never claimed
    ]


def _claims(tmp_path, dynasty):
    path = tmp_path / "claims.yaml"
    msg = waiver_wire.emit_claims(
        path,
        "x",
        11,
        _rows(),
        [{"name": "Xavier"}, {"name": "Yuri"}, {"name": "Zed"}],
        0,
        manual=False,
        limit=3,
        dynasty=dynasty,
    )
    assert "wrote" in msg
    return [ln for ln in path.read_text().splitlines() if ln.strip().startswith("- {")]


def test_redraft_claims_follow_the_lineup_gain_not_the_raw_blend(tmp_path):
    lines = _claims(tmp_path, dynasty=False)
    assert [ln.split("add: ")[1].split(",")[0] for ln in lines] == ["Alpha", "Charlie"]
    assert "drop: Xavier" in lines[0] and "drop: Yuri" in lines[1]
    assert "gain4 +5.0" in lines[0]  # the reason it was offered travels with the claim


def test_a_dynasty_asset_the_verdict_calls_no_help_can_still_be_claimed(tmp_path):
    lines = _claims(tmp_path, dynasty=True)
    assert [ln.split("add: ")[1].split(",")[0] for ln in lines] == [
        "Bravo",
        "Alpha",
        "Charlie",
    ]
    assert not any("Delta" in ln for ln in lines)  # a bye is never offered


def test_a_dynasty_swap_must_upgrade_something(tmp_path):
    """No lineup gain and a lower dynasty value than the player dropped: no claim."""
    rows = [
        {
            "name": "Stash",
            "verdict": "depth",
            "bid": (2, "why"),
            "blend": 5.0,
            "score": 39.0,
            "gain4": 0.0,
            "dyn": 979,
            "bye": False,
        },
        {
            "name": "Asset",
            "verdict": "no help",
            "bid": (2, "why"),
            "blend": 5.0,
            "score": 60.0,
            "gain4": 0.0,
            "dyn": 1500,
            "bye": False,
        },
    ]
    drops = [{"name": "Douglas", "dyn": 1187}, {"name": "Shakir", "dyn": 1320}]
    path = tmp_path / "claims.yaml"
    waiver_wire.emit_claims(
        path, "mantis", 11, rows, drops, 0, manual=True, limit=3, dynasty=True
    )
    text = path.read_text()
    claims = [ln for ln in text.splitlines() if ln.strip().startswith("- {")]
    assert [ln.split("add: ")[1].split(",")[0] for ln in claims] == ["Asset"]
    assert "drop: Douglas" in claims[0]
    assert "not worth dropping Shakir" in text  # and the refusal says why


def test_the_gate_still_parses_a_row_of_the_ranked_list():
    """The rank sits inside the name column: a tag in the margin hid every row
    from the gate ("no free agents parsed from the report", CRITICAL)."""
    from src.waiver_sanity import parse_rows

    text = (
        "-- Claim targets (free agents), ranked by gain to my best lineup --\n"
        "        #1 Kyle McCord           QB MIA  ours    - slpr 12.9 blend 12.9 "
        "last    - adds   27k         snap   -    dyn  979 gain4  +0.0 dynpts  39 "
        "age 24 depth   BID $2 (wins ~83%; $2 for 80%; worth $123) [unclaimed]\n"
    )
    rows = parse_rows(text)
    assert len(rows) == 1 and rows[0].name == "#1 Kyle McCord"
    assert rows[0].bid == 2 and rows[0].verdict == "depth" and rows[0].age == 24
