# Claude Response Fixtures

Recorded Anthropic Claude Haiku 4.5 responses used by every Claude-related
test in Phase 71 (`claude_primary` extractor). These fixtures power the
deterministic replay harness in `tests/sentiment/fakes.py::FakeClaudeClient`
and are the reason CI can exercise the full extraction pipeline without
touching the live API.

## Purpose

Phase 71 adds a Claude-primary extraction path to
`src/sentiment/processing/extractor.py`. Every test that sends a batch
through the Claude code path — unit, integration, and benchmark alike —
injects a `FakeClaudeClient` loaded with the fixtures in this directory.

Requirement **LLM-05** (see `.planning/REQUIREMENTS.md`) states:

> Claude-extraction tests use recorded fixtures (VCR-style), not live API
> calls — deterministic CI.

This folder is the physical manifestation of that contract.

## File Shape

Each response fixture is a single JSON object:

```json
{
  "_comment": "human-readable context for this fixture",
  "prompt_sha": "abc123...",                // 64-hex SHA-256 or a placeholder
  "model": "claude-haiku-4-5",
  "input_tokens": 1243,
  "output_tokens": 487,
  "cache_read_input_tokens": 1100,
  "cache_creation_input_tokens": 0,
  "response_text": "[{\"player_name\":\"...\",...}]"
}
```

`response_text` is a JSON-encoded **string** whose contents are a JSON array
of signal dicts matching the extended Plan 71-01 schema
(`player_name`, `sentiment`, `confidence`, `category`, `events` +
optional `summary`, `source_excerpt`, `team_abbr`). Non-player items
(`player_name: null`) are valid and exercise the EVT-02 path.

## `prompt_sha` Computation

`FakeClaudeClient` keys responses by the SHA-256 of the canonicalised
payload sent to Claude:

```python
import hashlib, json

def prompt_sha(system, messages, model: str) -> str:
    payload = json.dumps(
        {"model": model, "system": system, "messages": messages},
        sort_keys=True, default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

`sort_keys=True` makes the digest stable across dict reorderings, and
`default=str` guards against accidental non-JSON-native payload values.
`max_tokens` is intentionally excluded so the same prompt cached at
different output ceilings resolves to one registry entry.

## Roster-Provider Determinism Contract

**Hard invariant — Plan 71-03 MUST honor this.**

All fixtures in this directory MUST be recorded with a frozen empty roster
provider:

```python
# in the test / recording path only:
extract_batch_primary(..., roster_provider=lambda: [])
```

The cached player-list block in the Claude prompt would otherwise vary
across machines, dates, and roster-parquet refreshes — any drift breaks
the SHA match and all fixtures become unusable. By freezing
`roster_provider=lambda: []` for fixture recording, the SHA depends only on
the static system prefix + the per-doc user block.

Plan 71-03's `_build_batched_prompt` and its benchmark test MUST call
`extract_batch_primary(..., roster_provider=lambda: [])` for the
test/benchmark paths. Production-mode extraction uses the real roster
provider and will (by design) produce different SHAs; a separate fixture
set would be required if fixtures are ever recorded against production
mode. For Phase 71 tests, the empty-roster path is the only one exercised.

Look for `lambda: []`, "empty roster", or "frozen roster" anywhere the
fixtures are generated or consumed — any deviation is a determinism bug.

## Re-recording Procedure

Plan 71-03 will ship a helper script (working name
`scripts/record_claude_fixtures.py`) that:

1. Reads the Bronze docs from
   `tests/fixtures/bronze_sentiment/offseason_w17_w18.json`.
2. Instantiates the batched Claude extractor **with a frozen
   `roster_provider=lambda: []`** to satisfy the determinism contract
   above.
3. Calls `extract_batch_primary(...)` per batch against the real
   `anthropic.Anthropic` client (one-time, developer laptop only — never
   CI).
4. Writes each call's `{prompt_sha, model, input_tokens, output_tokens,
   cache_read_input_tokens, cache_creation_input_tokens, response_text}`
   into `tests/fixtures/claude_responses/<name>.json`, overwriting the
   `_PENDING_WAVE_2_SHA` placeholders the Plan 71-02 seed fixtures carry.

Until that script lands, the seed fixtures use `_PENDING_WAVE_2_SHA_<tag>`
literals (e.g. `_PENDING_WAVE_2_SHA_w17`, `_PENDING_WAVE_2_SHA_w18`) as
keys so `FakeClaudeClient.from_fixture_dir` loads them cleanly without
collision while any real-prompt call still raises a strict-mode
`AssertionError`. The tests in
`test_fake_claude_client.py::PlaceholderShaWorkflowTests` lock this
two-phase workflow in place.

## CI Prohibition on Live Calls (LLM-05)

Under no circumstances may a CI test invoke the real `anthropic.Anthropic`
client. Violations include:

- Calling `anthropic.Anthropic(api_key=...)` directly in a test.
- Monkeypatching `ClaudeExtractor._build_client` to return a real client.
- Setting `ANTHROPIC_API_KEY` in the CI environment (GHA secret is
  deliberately not exported to the test matrix).

Plan 71-05 adds a guard that asserts the benchmark test specifically uses
a `FakeClaudeClient` and not the real SDK. New Claude tests should follow
the same pattern: instantiate `FakeClaudeClient`, call
`register_response` or `from_fixture_dir`, and inject via constructor DI.

## Files in this Directory

| File                         | Purpose                                             |
|------------------------------|-----------------------------------------------------|
| `offseason_batch_w17.json`   | 2025 W17 batch (cold cache: `cache_creation > 0`).  |
| `offseason_batch_w18.json`   | 2025 W18 batch (warm cache: `cache_read > 0`).      |
| `README.md`                  | This file — workflow + contracts.                   |

Each batch contains >= 5 signals, at least 2 of which are non-player
`team_abbr`-only items so Plan 72's EVT-02 routing gets test coverage
out of the gate.
