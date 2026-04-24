"""Tests for the batched primary Claude extractor (Plan 71-03 Task 2).

Covers the new ``extract_batch_primary`` path on
``src/sentiment/processing/extractor.py``:

* DI seam: ``ClaudeExtractor(client=FakeClaudeClient(), ...)`` bypasses
  ``ANTHROPIC_API_KEY`` gating.
* Prompt caching: every ``messages.create`` call carries a 2-element
  ``system`` list with ``cache_control: {"type": "ephemeral"}`` markers.
* Batching: ``batch_size=N`` slices the doc list into ceil(len/N) calls.
* Non-player capture: items with ``player_name: null`` surface via the
  second return value.
* Cost tracking: a ``CostRecord`` is written per call when ``cost_log``
  is injected.
* Fail-open: missing client ⇒ returns ``({}, [])`` without raising.
* SHA replay: the 30-doc Bronze fixture replayed against recorded W17 +
  W18 fixture JSONs (with ``roster_provider=lambda: []`` to honor the
  determinism contract from Plan 71-02) yields >= 5 signals and every
  signal carries ``extractor == "claude_primary"``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from src.sentiment.processing.cost_log import CostLog
from src.sentiment.processing.extractor import (
    BATCH_SIZE,
    ClaudeExtractor,
    PlayerSignal,
    _build_batched_prompt_for_sha,
)
from tests.sentiment.fakes import FakeClaudeClient, prompt_sha


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bronze_docs() -> list:
    path = Path("tests/fixtures/bronze_sentiment/offseason_w17_w18.json")
    data = json.loads(path.read_text())
    return data["items"]


@pytest.fixture
def w17_docs(bronze_docs) -> list:
    return [d for d in bronze_docs if d.get("week") == 17]


@pytest.fixture
def w18_docs(bronze_docs) -> list:
    return [d for d in bronze_docs if d.get("week") == 18]


@pytest.fixture
def fake_from_fixture_dir() -> FakeClaudeClient:
    """Load FakeClaudeClient from the recorded response fixtures."""
    return FakeClaudeClient.from_fixture_dir(
        Path("tests/fixtures/claude_responses")
    )


# ---------------------------------------------------------------------------
# DI and fail-open behaviour
# ---------------------------------------------------------------------------


def test_constructor_accepts_injected_fake_client(monkeypatch):
    """ClaudeExtractor(client=fake) MUST NOT read ANTHROPIC_API_KEY."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake = FakeClaudeClient()
    extractor = ClaudeExtractor(
        client=fake, roster_provider=lambda: ["Patrick Mahomes"]
    )
    assert extractor._client is fake


def test_extract_batch_primary_fail_open_without_client(monkeypatch, caplog):
    """No client + no API key ⇒ ({}, []) and a warning, never raise."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    extractor = ClaudeExtractor()  # no DI, no env — _client is None
    by_doc, non_player = extractor.extract_batch_primary(
        [{"external_id": "x", "title": "t", "body_text": "b"}],
        season=2025,
        week=17,
    )
    assert by_doc == {}
    assert non_player == []


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def _synthetic_docs(n: int) -> List[dict]:
    return [
        {
            "external_id": f"synth-{i:03d}",
            "title": f"Title {i}",
            "body_text": f"Body text for doc {i}. " * 10,
        }
        for i in range(n)
    ]


def test_batch_size_eight_produces_two_calls_for_sixteen_docs():
    fake = FakeClaudeClient(strict=False)
    extractor = ClaudeExtractor(
        client=fake, roster_provider=lambda: [], batch_size=BATCH_SIZE
    )
    extractor.extract_batch_primary(_synthetic_docs(16), season=2025, week=1)
    assert len(fake.call_log) == 2


def test_batch_size_three_on_ten_docs_produces_four_calls():
    fake = FakeClaudeClient(strict=False)
    extractor = ClaudeExtractor(
        client=fake, roster_provider=lambda: [], batch_size=3
    )
    extractor.extract_batch_primary(_synthetic_docs(10), season=2025, week=1)
    assert len(fake.call_log) == 4  # sizes 3, 3, 3, 1


# ---------------------------------------------------------------------------
# Prompt shape: caching markers, roster block
# ---------------------------------------------------------------------------


class _SpyMessages:
    """Inspector that captures ``.create(**kwargs)`` call arguments."""

    def __init__(self):
        self.calls: List[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class _Resp:
            class _Block:
                text = "[]"

            content = [_Block()]

            class _Usage:
                input_tokens = 0
                output_tokens = 0
                cache_read_input_tokens = 0
                cache_creation_input_tokens = 0

            usage = _Usage()

        return _Resp()


class _SpyClient:
    def __init__(self):
        self.messages = _SpyMessages()


def test_system_list_has_two_cache_control_markers():
    spy = _SpyClient()
    extractor = ClaudeExtractor(
        client=spy, roster_provider=lambda: ["Patrick Mahomes", "Travis Kelce"]
    )
    extractor.extract_batch_primary(_synthetic_docs(1), season=2025, week=1)

    call = spy.messages.calls[0]
    system = call["system"]
    assert isinstance(system, list)
    assert len(system) == 2
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    # Static prefix first, roster block second.
    assert "NFL" in system[0]["text"]
    assert "ACTIVE PLAYERS:" in system[1]["text"]
    # Roster names present
    assert "Patrick Mahomes" in system[1]["text"]
    assert "Travis Kelce" in system[1]["text"]


def test_empty_roster_drops_second_system_entry():
    """With empty roster, the system list is a SINGLE cached entry."""
    spy = _SpyClient()
    extractor = ClaudeExtractor(client=spy, roster_provider=lambda: [])
    extractor.extract_batch_primary(_synthetic_docs(1), season=2025, week=1)

    call = spy.messages.calls[0]
    system = call["system"]
    assert isinstance(system, list)
    assert len(system) == 1
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_max_tokens_is_batched_value():
    spy = _SpyClient()
    extractor = ClaudeExtractor(client=spy, roster_provider=lambda: [])
    extractor.extract_batch_primary(_synthetic_docs(2), season=2025, week=1)

    assert spy.messages.calls[0]["max_tokens"] == 4096


# ---------------------------------------------------------------------------
# Response parsing: malformed JSON and non-player capture
# ---------------------------------------------------------------------------


def _register_empty_for_all(fake: FakeClaudeClient, extractor: ClaudeExtractor,
                             docs: List[dict]) -> None:
    """Helper: register an empty JSON array response for every batch in ``docs``."""
    for start in range(0, len(docs), extractor.batch_size):
        batch = docs[start:start + extractor.batch_size]
        system, messages = _build_batched_prompt_for_sha(
            static_prefix=extractor._system_prefix_for_test(),
            roster_block=extractor._get_roster_block(),
            batch_docs=batch,
        )
        sha = prompt_sha(system, messages, extractor.model)
        fake.register_response(sha, "[]")


def test_malformed_json_response_drops_batch_signals_without_raising(caplog):
    fake = FakeClaudeClient(strict=True)
    extractor = ClaudeExtractor(
        client=fake, roster_provider=lambda: [], batch_size=2
    )
    docs = _synthetic_docs(2)
    system, messages = _build_batched_prompt_for_sha(
        static_prefix=extractor._system_prefix_for_test(),
        roster_block=extractor._get_roster_block(),
        batch_docs=docs,
    )
    sha = prompt_sha(system, messages, extractor.model)
    fake.register_response(sha, "not valid json!!")

    by_doc, non_player = extractor.extract_batch_primary(
        docs, season=2025, week=1
    )
    assert by_doc == {}
    assert non_player == []


def test_non_player_items_routed_to_second_return_value():
    fake = FakeClaudeClient(strict=True)
    extractor = ClaudeExtractor(
        client=fake, roster_provider=lambda: [], batch_size=2
    )
    docs = _synthetic_docs(2)
    system, messages = _build_batched_prompt_for_sha(
        static_prefix=extractor._system_prefix_for_test(),
        roster_block=extractor._get_roster_block(),
        batch_docs=docs,
    )
    sha = prompt_sha(system, messages, extractor.model)
    response = [
        {
            "doc_id": "synth-000",
            "player_name": "Patrick Mahomes",
            "sentiment": 0.5,
            "confidence": 0.8,
            "category": "usage",
            "events": {},
            "summary": "Mahomes update.",
            "team_abbr": "KC",
        },
        {
            "doc_id": "synth-001",
            "player_name": None,
            "sentiment": -0.3,
            "confidence": 0.7,
            "category": "general",
            "events": {},
            "summary": "Team news",
            "team_abbr": "DAL",
        },
    ]
    fake.register_response(sha, response)

    by_doc, non_player = extractor.extract_batch_primary(
        docs, season=2025, week=1
    )
    assert "synth-000" in by_doc
    assert by_doc["synth-000"][0].player_name == "Patrick Mahomes"
    assert by_doc["synth-000"][0].extractor == "claude_primary"
    assert by_doc["synth-000"][0].team_abbr == "KC"
    assert by_doc["synth-000"][0].summary == "Mahomes update."

    assert len(non_player) == 1
    assert non_player[0]["team_abbr"] == "DAL"
    assert non_player[0]["summary"] == "Team news"
    # Non-player dict carries the source doc_id / external_id for downstream
    # routing.
    assert non_player[0]["doc_id"] == "synth-001"


def test_api_error_re_raises_to_caller():
    """Actual API errors from messages.create MUST propagate up."""
    fake = FakeClaudeClient(strict=True)
    extractor = ClaudeExtractor(
        client=fake, roster_provider=lambda: [], batch_size=2
    )
    docs = _synthetic_docs(2)
    system, messages = _build_batched_prompt_for_sha(
        static_prefix=extractor._system_prefix_for_test(),
        roster_block=extractor._get_roster_block(),
        batch_docs=docs,
    )
    sha = prompt_sha(system, messages, extractor.model)
    fake.register_failure(sha, RuntimeError("rate limit hit"))

    with pytest.raises(RuntimeError, match="rate limit"):
        extractor.extract_batch_primary(docs, season=2025, week=1)


# ---------------------------------------------------------------------------
# Cost log integration
# ---------------------------------------------------------------------------


def test_cost_log_receives_one_record_per_call(tmp_path):
    fake = FakeClaudeClient(strict=False)  # non-strict returns "[]" for unseen
    cost_log = CostLog(base_dir=tmp_path)
    extractor = ClaudeExtractor(
        client=fake,
        roster_provider=lambda: [],
        cost_log=cost_log,
        batch_size=4,
    )
    extractor.extract_batch_primary(
        _synthetic_docs(10), season=2025, week=1
    )  # 4/4/2 → 3 batches

    # 3 Parquet files should exist under the partition.
    partition = tmp_path / "season=2025" / "week=01"
    files = sorted(partition.glob("llm_costs_*.parquet"))
    assert len(files) == 3


def test_cost_log_none_produces_no_files(tmp_path, monkeypatch):
    fake = FakeClaudeClient(strict=False)
    extractor = ClaudeExtractor(
        client=fake, roster_provider=lambda: [], batch_size=4
    )
    extractor.extract_batch_primary(_synthetic_docs(4), season=2025, week=1)

    # No files written anywhere (default base dir untouched)
    assert not list((tmp_path).rglob("llm_costs_*.parquet"))


# ---------------------------------------------------------------------------
# SHA-keyed fixture replay on the real W17+W18 recorded fixtures
# ---------------------------------------------------------------------------


def _update_fixture_sha(path: Path, new_sha: str) -> None:
    """Rewrite a fixture file's ``prompt_sha`` field in place."""
    data = json.loads(path.read_text())
    data["prompt_sha"] = new_sha
    path.write_text(json.dumps(data, indent=2) + "\n")


def _record_real_shas(extractor: ClaudeExtractor, w17_docs: list,
                       w18_docs: list) -> tuple:
    """Compute real SHAs for the fixture batches (uses roster_provider=lambda:[]).

    Writes the computed SHAs back into the fixture files, overwriting the
    ``_PENDING_WAVE_2_SHA_<tag>`` placeholders. This is the Plan 71-03 Task 2
    Wave-3 recording step, implemented inline for determinism.
    """
    prefix = extractor._system_prefix_for_test()
    roster = extractor._get_roster_block()

    # Match fixture granularity: one call per week batch (so batch_size >= 15).
    system_w17, messages_w17 = _build_batched_prompt_for_sha(
        static_prefix=prefix, roster_block=roster, batch_docs=w17_docs
    )
    sha_w17 = prompt_sha(system_w17, messages_w17, extractor.model)

    system_w18, messages_w18 = _build_batched_prompt_for_sha(
        static_prefix=prefix, roster_block=roster, batch_docs=w18_docs
    )
    sha_w18 = prompt_sha(system_w18, messages_w18, extractor.model)

    # Persist back into the fixture JSON files — overwriting the
    # _PENDING_WAVE_2_SHA_w17 / _w18 placeholders that Plan 71-02 left behind.
    _update_fixture_sha(
        Path("tests/fixtures/claude_responses/offseason_batch_w17.json"),
        sha_w17,
    )
    _update_fixture_sha(
        Path("tests/fixtures/claude_responses/offseason_batch_w18.json"),
        sha_w18,
    )
    return sha_w17, sha_w18


def test_sha_replay_against_w17_fixture_yields_claude_primary_signals(
    w17_docs, w18_docs
):
    """Full SHA-keyed replay against the recorded W17 fixture.

    Updates the fixture's ``prompt_sha`` to the real value computed from
    ``_build_batched_prompt_for_sha`` with ``roster_provider=lambda: []``
    (the determinism contract from Plan 71-02). Then loads the fixture dir
    into a FakeClaudeClient and runs ``extract_batch_primary`` against W17
    docs, asserting that >= 5 signals are produced with
    ``extractor="claude_primary"``.
    """
    # Create extractor with batch_size=15 so W17 is a single batch
    # matching the single recorded response.
    recording_extractor = ClaudeExtractor(
        client=FakeClaudeClient(strict=False),
        roster_provider=lambda: [],
        batch_size=15,
    )
    _record_real_shas(recording_extractor, w17_docs, w18_docs)

    # Now load the (updated) fixtures into a fresh FakeClaudeClient
    fake = FakeClaudeClient.from_fixture_dir(
        Path("tests/fixtures/claude_responses")
    )
    extractor = ClaudeExtractor(
        client=fake, roster_provider=lambda: [], batch_size=15
    )

    by_doc, non_player = extractor.extract_batch_primary(
        w17_docs, season=2025, week=17
    )

    total_signals = sum(len(sigs) for sigs in by_doc.values())
    assert total_signals >= 5, f"expected >= 5 signals, got {total_signals}"
    assert len(non_player) >= 1

    # Every signal carries the claude_primary tag (overrides PlayerSignal default "rule").
    for sigs in by_doc.values():
        for sig in sigs:
            assert isinstance(sig, PlayerSignal)
            assert sig.extractor == "claude_primary"


def test_fixture_shas_updated_from_pending_placeholder(w17_docs, w18_docs):
    """After the fixture recording test runs, prompt_sha must be a real 64-hex."""
    recording_extractor = ClaudeExtractor(
        client=FakeClaudeClient(strict=False),
        roster_provider=lambda: [],
        batch_size=15,
    )
    _record_real_shas(recording_extractor, w17_docs, w18_docs)

    for name in ("offseason_batch_w17.json", "offseason_batch_w18.json"):
        data = json.loads(
            Path(f"tests/fixtures/claude_responses/{name}").read_text()
        )
        sha = data["prompt_sha"]
        assert not sha.startswith("_PENDING_WAVE_2_SHA"), (
            f"{name} still carries placeholder SHA"
        )
        assert len(sha) == 64, f"{name} SHA not 64 hex chars: {sha!r}"
        int(sha, 16)  # must be valid hex
