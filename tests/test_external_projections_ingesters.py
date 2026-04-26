"""Tests for the Phase 73 external projections Bronze ingesters.

Three sources covered:
  - ESPN public fantasy projections API
  - Sleeper public projections API (via shared HTTP helper, D-01)
  - FantasyPros consensus HTML scrape (Yahoo proxy, D-03)

All tests are fixture-driven; no live network calls.  Tests honour the D-06
fail-open contract: a network/HTTP error logs a WARNING and exits 0 with no
Parquet written.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Bootstrap project root on sys.path so `import scripts.*` and `import src.*`
# resolve when pytest is invoked from any working directory.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_FIXTURE_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "external_projections"


def _load_json_fixture(name: str) -> Dict[str, Any]:
    path = _FIXTURE_DIR / name
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_text_fixture(name: str) -> str:
    path = _FIXTURE_DIR / name
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ===========================================================================
# Task 1: ESPN ingester
# ===========================================================================


@pytest.mark.unit
def test_espn_parses_fixture() -> None:
    """ESPN fixture parses to >=10 rows with the required Bronze schema."""
    espn_module = importlib.import_module("scripts.ingest_external_projections_espn")

    payload = _load_json_fixture("espn_sample.json")
    df = espn_module._parse_espn_response(
        payload, season=2025, week=1, scoring="half_ppr"
    )

    assert espn_module._SOURCE_LABEL == "espn"
    assert len(df) >= 10
    expected_cols = {
        "player_name",
        "player_id",
        "team",
        "position",
        "projected_points",
        "scoring_format",
        "source",
        "season",
        "week",
        "projected_at",
        "raw_payload",
    }
    assert expected_cols.issubset(set(df.columns)), (
        f"Missing columns: {expected_cols - set(df.columns)}"
    )

    # projected_points must be non-negative floats
    assert df["projected_points"].dtype.kind in ("f", "i")
    assert (df["projected_points"] >= 0).all()

    # Source provenance
    assert (df["source"] == "espn").all()
    assert (df["scoring_format"] == "half_ppr").all()
    assert (df["season"] == 2025).all()
    assert (df["week"] == 1).all()


@pytest.mark.unit
def test_espn_fail_open_on_network_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ESPN ingester exits 0 with no Parquet when requests.get raises."""
    espn_module = importlib.import_module("scripts.ingest_external_projections_espn")

    import requests

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise requests.RequestException("simulated network failure")

    monkeypatch.setattr(espn_module.requests, "get", _boom)

    out_root = tmp_path / "external_projections"
    rc = espn_module.main(
        [
            "--season",
            "2025",
            "--week",
            "1",
            "--out-root",
            str(out_root),
        ]
    )
    assert rc == 0
    # No Parquet files written under the out-root
    parquets = list(out_root.rglob("*.parquet"))
    assert parquets == []


# ===========================================================================
# Task 2: Sleeper ingester
# ===========================================================================


@pytest.mark.unit
def test_sleeper_parses_fixture() -> None:
    """Sleeper fixture parses to a DataFrame with Bronze schema."""
    sleeper_module = importlib.import_module(
        "scripts.ingest_external_projections_sleeper"
    )

    payload = _load_json_fixture("sleeper_sample.json")
    df = sleeper_module._parse_sleeper_response(
        payload, season=2025, week=1, scoring="half_ppr"
    )

    assert sleeper_module._SOURCE_LABEL == "sleeper"
    assert len(df) >= 5
    expected_cols = {
        "player_name",
        "player_id",
        "team",
        "position",
        "projected_points",
        "scoring_format",
        "source",
        "season",
        "week",
        "projected_at",
        "raw_payload",
    }
    assert expected_cols.issubset(set(df.columns)), (
        f"Missing columns: {expected_cols - set(df.columns)}"
    )
    assert (df["source"] == "sleeper").all()
    assert (df["scoring_format"] == "half_ppr").all()
    assert (df["projected_points"] >= 0).all()


@pytest.mark.unit
def test_sleeper_fail_open_on_network_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sleeper ingester exits 0 with no Parquet when fetch returns {}."""
    sleeper_module = importlib.import_module(
        "scripts.ingest_external_projections_sleeper"
    )

    # The shared helper returns {} on any error per D-06; simulate that.
    monkeypatch.setattr(
        sleeper_module, "fetch_sleeper_json", lambda *a, **kw: {}
    )

    out_root = tmp_path / "external_projections"
    rc = sleeper_module.main(
        [
            "--season",
            "2025",
            "--week",
            "1",
            "--out-root",
            str(out_root),
        ]
    )
    assert rc == 0
    parquets = list(out_root.rglob("*.parquet"))
    assert parquets == []


@pytest.mark.unit
def test_sleeper_uses_shared_http_helper_not_requests_directly() -> None:
    """D-01 structural guard: new ingester must NOT contain `import requests`.

    Sleeper HTTP must flow through `src/sleeper_http.py` to keep the single
    source of truth for Sleeper API calls.
    """
    script_path = (
        _PROJECT_ROOT / "scripts" / "ingest_external_projections_sleeper.py"
    )
    source = script_path.read_text(encoding="utf-8")
    # Match top-level import statements only
    forbidden_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("import requests")
        or line.strip().startswith("from requests")
    ]
    assert forbidden_lines == [], (
        "D-01 violation: scripts/ingest_external_projections_sleeper.py "
        "must not import the `requests` library directly. Use "
        "src.sleeper_http.fetch_sleeper_json instead. Found: "
        f"{forbidden_lines}"
    )

    # And the shared helper must be imported.
    assert "from src.sleeper_http import" in source, (
        "Sleeper ingester must import from src.sleeper_http (D-01)."
    )


# ===========================================================================
# Task 3: Yahoo (FantasyPros consensus proxy) ingester
# ===========================================================================


@pytest.mark.unit
def test_fantasypros_parses_fixture_qb() -> None:
    """FantasyPros QB fixture parses to >=5 rows with Bronze schema."""
    yahoo_module = importlib.import_module(
        "scripts.ingest_external_projections_yahoo"
    )

    html = _load_text_fixture("fantasypros_sample.html")
    df = yahoo_module._parse_fp_position(
        html, position="qb", season=2025, week=1, scoring="half_ppr"
    )

    assert len(df) >= 5
    expected_cols = {
        "player_name",
        "player_id",
        "team",
        "position",
        "projected_points",
        "scoring_format",
        "source",
        "season",
        "week",
        "projected_at",
        "raw_payload",
    }
    assert expected_cols.issubset(set(df.columns)), (
        f"Missing columns: {expected_cols - set(df.columns)}"
    )
    assert (df["position"] == "QB").all()
    assert (df["projected_points"] >= 0).all()


@pytest.mark.unit
def test_yahoo_proxy_label_present() -> None:
    """Yahoo proxy ingester must label source 'yahoo_proxy_fp' (D-03)."""
    yahoo_module = importlib.import_module(
        "scripts.ingest_external_projections_yahoo"
    )

    assert yahoo_module._SOURCE_LABEL == "yahoo_proxy_fp"

    html = _load_text_fixture("fantasypros_sample.html")
    df = yahoo_module._parse_fp_position(
        html, position="qb", season=2025, week=1, scoring="half_ppr"
    )
    assert (df["source"] == "yahoo_proxy_fp").all(), (
        "All rows must carry source='yahoo_proxy_fp' for provenance "
        "transparency per D-03."
    )


@pytest.mark.unit
def test_fantasypros_fail_open_on_network_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """FantasyPros ingester exits 0 when ALL position fetches fail."""
    yahoo_module = importlib.import_module(
        "scripts.ingest_external_projections_yahoo"
    )

    import requests

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise requests.RequestException("simulated FP outage")

    monkeypatch.setattr(yahoo_module.requests, "get", _boom)

    out_root = tmp_path / "external_projections"
    rc = yahoo_module.main(
        [
            "--season",
            "2025",
            "--week",
            "1",
            "--out-root",
            str(out_root),
        ]
    )
    assert rc == 0
    parquets = list(out_root.rglob("*.parquet"))
    assert parquets == []
