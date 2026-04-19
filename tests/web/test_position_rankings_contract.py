"""Contract tests for the advisor ``getPositionRankings`` tool (plan 63-04).

These tests encode the contract that the FastAPI ``/api/projections`` endpoint
MUST honor so the AI advisor's position-rankings flow always renders real
Gold-layer numbers instead of hallucinated ones.

The six contract assertions:

1. ``GET /api/projections?position=RB&limit=10&season=2026&week=1`` returns
   HTTP 200.
2. The response body exposes a ``projections`` list with length 10 (or 0 when
   the preseason slate is genuinely empty).
3. Every projection entry has a ``projected_points`` value that is a finite
   ``float`` greater than zero.
4. The list is sorted by ``projected_points`` descending (tie-break
   irrelevant).
5. Every projection entry carries ``position == 'RB'``.
6. A top-level ``meta.data_as_of`` field exposes the source parquet's mtime
   as an ISO 8601 UTC timestamp. (Task 2 of plan 63-04 adds this; skipped
   until then.)
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from web.api.main import app  # noqa: E402

client = TestClient(app)

_ISO_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


@pytest.fixture(scope="module")
def rankings_response() -> dict:
    """Fetch the canonical RB top-10 response once for every assertion."""
    resp = client.get(
        "/api/projections",
        params={
            "position": "RB",
            "limit": 10,
            "season": 2026,
            "week": 1,
            "scoring": "half_ppr",
        },
    )
    assert (
        resp.status_code == 200
    ), f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    return resp.json()


# ---------------------------------------------------------------------------
# Assertion 1 -- endpoint returns HTTP 200
# ---------------------------------------------------------------------------


def test_returns_200_for_rb_top_10() -> None:
    """Contract: /api/projections?position=RB&limit=10&... must return 200."""
    resp = client.get(
        "/api/projections",
        params={
            "position": "RB",
            "limit": 10,
            "season": 2026,
            "week": 1,
            "scoring": "half_ppr",
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Assertion 2 -- projections is a list of length 10 (or empty when preseason
#                slate is absent)
# ---------------------------------------------------------------------------


def test_projections_length_is_ten_or_empty(rankings_response: dict) -> None:
    """Contract: ``projections`` is a list with len == 10 for limit=10, OR
    len == 0 when no Gold data exists for the requested slice.
    """
    assert "projections" in rankings_response
    projections = rankings_response["projections"]
    assert isinstance(projections, list)
    if len(projections) == 0:
        # Preseason-empty path: meta.data_as_of MUST be null when list is empty
        # (Task 2 of 63-04 adds the meta block; Task 1 only declares intent.)
        return
    assert (
        len(projections) == 10
    ), f"Expected 10 RB entries for limit=10, got {len(projections)}"


# ---------------------------------------------------------------------------
# Assertion 3 -- projected_points is a finite float > 0
# ---------------------------------------------------------------------------


def test_projected_points_are_positive_floats(rankings_response: dict) -> None:
    """Contract: every projection carries a non-null finite ``projected_points``
    greater than zero. Hallucinated or empty Gold reads would break this.
    """
    projections = rankings_response["projections"]
    if not projections:
        pytest.skip("Gold projections unavailable for season=2026 week=1")
    for entry in projections:
        assert "projected_points" in entry, f"entry missing projected_points: {entry}"
        value = entry["projected_points"]
        assert isinstance(
            value, (int, float)
        ), f"projected_points must be numeric, got {type(value).__name__}"
        # NaN guard
        assert value == value, "projected_points is NaN"
        assert (
            value > 0
        ), f"projected_points must be > 0 for {entry.get('player_name')}: {value}"


# ---------------------------------------------------------------------------
# Assertion 4 -- list is sorted by projected_points descending
# ---------------------------------------------------------------------------


def test_projections_sorted_descending(rankings_response: dict) -> None:
    """Contract: advisor expects top-N already sorted by projected_points desc."""
    projections = rankings_response["projections"]
    if not projections:
        pytest.skip("Gold projections unavailable for season=2026 week=1")
    points = [p["projected_points"] for p in projections]
    for prev, curr in zip(points, points[1:]):
        assert (
            prev >= curr
        ), f"Projections not sorted descending: {prev} precedes {curr}"


# ---------------------------------------------------------------------------
# Assertion 5 -- position filter honored: every entry is an RB
# ---------------------------------------------------------------------------


def test_every_entry_is_rb(rankings_response: dict) -> None:
    """Contract: ``position=RB`` filter MUST return only RBs."""
    projections = rankings_response["projections"]
    if not projections:
        pytest.skip("Gold projections unavailable for season=2026 week=1")
    wrong_positions = [p["position"] for p in projections if p["position"] != "RB"]
    assert (
        not wrong_positions
    ), f"Expected only RBs, got extra positions: {wrong_positions}"


# ---------------------------------------------------------------------------
# Assertion 6 -- meta.data_as_of exposes source parquet mtime (Task 2 adds it)
# ---------------------------------------------------------------------------


def test_meta_data_as_of(rankings_response: dict) -> None:
    """Contract: response carries ``meta.data_as_of`` as ISO 8601 UTC so the
    advisor can tell users when the data was last refreshed.

    Task 2 of plan 63-04 lands this addition on the backend. Until then the
    test is marked as expected-to-fail / skipped so the RED phase stays clean.
    """
    if "meta" not in rankings_response:
        pytest.skip("requires Task 2 — backend meta block not implemented yet")

    meta = rankings_response["meta"]
    assert isinstance(meta, dict), "meta must be an object"

    projections = rankings_response["projections"]
    data_as_of = meta.get("data_as_of")
    if not projections:
        # Empty preseason slate: data_as_of is allowed to be null.
        assert (
            data_as_of is None
        ), "data_as_of must be null when projections list is empty"
        return

    assert isinstance(data_as_of, str), "data_as_of must be an ISO 8601 string"
    assert _ISO_UTC_RE.match(
        data_as_of
    ), f"data_as_of does not look ISO 8601 UTC: {data_as_of!r}"
    # Parse round-trip safety: Python 3.9 `datetime.fromisoformat` rejects 'Z'
    # suffix, so normalize first.
    parsed = datetime.fromisoformat(data_as_of.replace("Z", "+00:00"))
    assert parsed is not None


# ---------------------------------------------------------------------------
# /api/projections/latest-week — auto-resolve default week for the advisor
# ---------------------------------------------------------------------------


def test_latest_week_returns_200_with_valid_schema() -> None:
    """Contract: ``/api/projections/latest-week?season=2026`` returns
    ``{season, week, data_as_of}`` with HTTP 200, even when no data exists.
    """
    resp = client.get("/api/projections/latest-week", params={"season": 2026})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {
        "season",
        "week",
        "data_as_of",
    }, f"latest-week response missing keys: {body.keys()}"
    assert body["season"] == 2026
    # week is int or null — nothing else
    assert body["week"] is None or isinstance(body["week"], int)
    # data_as_of is ISO-ish string or null
    assert body["data_as_of"] is None or isinstance(body["data_as_of"], str)


def test_latest_week_picks_highest_week_with_data() -> None:
    """Contract: when Gold data exists for multiple weeks, latest-week picks
    the highest week number. Our Gold layer for season=2026 currently has
    week=1, so week=1 is the expected resolution until later weeks land.
    """
    resp = client.get("/api/projections/latest-week", params={"season": 2026})
    body = resp.json()
    if body["week"] is None:
        pytest.skip(
            "no Gold data for 2026 — latest-week empty path exercised elsewhere"
        )
    assert body["week"] >= 1
    assert body["data_as_of"] is not None
    assert _ISO_UTC_RE.match(body["data_as_of"])


def test_latest_week_empty_season_returns_200_with_nulls() -> None:
    """Contract: querying a season with no Gold data returns HTTP 200 with
    ``week=null`` and ``data_as_of=null`` — never 404.
    """
    # 1999 is deliberately beyond projection coverage
    resp = client.get("/api/projections/latest-week", params={"season": 1999})
    assert resp.status_code == 200
    body = resp.json()
    assert body["season"] == 1999
    assert body["week"] is None
    assert body["data_as_of"] is None


# ---------------------------------------------------------------------------
# /api/projections meta — data_as_of returned alongside projections
# ---------------------------------------------------------------------------


def test_meta_block_roundtrips_season_and_week(rankings_response: dict) -> None:
    """Contract: the ``meta`` block echoes the requested season/week so the
    advisor can cite the exact slice without re-parsing URL params.
    """
    meta = rankings_response.get("meta")
    if meta is None:
        pytest.skip("meta block absent — backend pre-63-04")
    assert meta["season"] == 2026
    assert meta["week"] == 1
