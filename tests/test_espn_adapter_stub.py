"""Offline tests for the gated EspnAdapter stub (Phase 89, ESPN-02/03 NO-GO path).

The ESPN-01 spike returned NO-GO for automated live capture, so ``EspnAdapter`` is
an honestly-gated stub: it conforms to the ``DraftAdapter`` protocol (so ESPN is a
registerable platform) but disables live capture loudly. These tests pin that
documented behavior. 100% offline: ``@pytest.mark.unit``, no network.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from src.draft_adapter import DraftAdapter
from src.draft_models import PickEvent
from src.espn_adapter import EspnAdapter

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sleeper_draft")


@pytest.fixture
def projections_df():
    with open(
        os.path.join(_FIXTURE_DIR, "projections_sample.json"), encoding="utf-8"
    ) as fh:
        return pd.DataFrame(json.load(fh))


@pytest.mark.unit
def test_espn_adapter_conforms_to_protocol():
    """EspnAdapter satisfies the runtime-checkable DraftAdapter protocol."""
    adapter = EspnAdapter()
    assert isinstance(adapter, DraftAdapter)
    assert adapter.platform == "espn"
    assert adapter.spike_verdict == "NO-GO"


@pytest.mark.unit
def test_resolve_draft_reports_not_found_fail_open():
    """resolve_draft never raises and reports ESPN is unsupported."""
    res = EspnAdapter().resolve_draft("anyuser", "2026")
    assert res["found"] is False
    assert res["candidates"] == []
    assert res["platform"] == "espn"
    assert "--manual" in res["reason"]


@pytest.mark.unit
def test_load_state_raises_with_manual_guidance():
    """load_state raises NotImplementedError pointing to the manual fallback."""
    with pytest.raises(NotImplementedError) as exc:
        EspnAdapter().load_state("123456")
    msg = str(exc.value)
    assert "--manual" in msg
    assert "89-SPIKE-FINDINGS" in msg


@pytest.mark.unit
def test_map_picks_works_network_free(projections_df):
    """map_picks resolves typed ESPN picks to projections (no network)."""
    picks = [
        PickEvent(
            pick_no=1,
            round=1,
            draft_slot=1,
            roster_id=1,
            picked_by="manual",
            sleeper_player_id="",
            first_name="Ja'Marr",
            last_name="Chase",
            position="WR",
            team="CIN",
            is_keeper=False,
        ),
        PickEvent(
            pick_no=2,
            round=1,
            draft_slot=2,
            roster_id=2,
            picked_by="manual",
            sleeper_player_id="",
            first_name="Totally",
            last_name="Unknown",
            position="",
            team="",
            is_keeper=False,
        ),
    ]
    matched, unmatched = EspnAdapter().map_picks(picks, projections_df)
    matched_names = {m.get("player_name") for m in matched}
    assert "Ja'Marr Chase" in matched_names
    # Unknown player is surfaced as unmatched, never silently dropped.
    assert any(p.full_name == "Totally Unknown" for p in unmatched)
