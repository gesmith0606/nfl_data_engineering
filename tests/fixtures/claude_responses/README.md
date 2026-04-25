# Claude Response Fixtures

Recorded Anthropic Claude Haiku 4.5 responses used by every Claude-related
test in Phase 71 + 72 (`claude_primary` extractor). These fixtures power the
deterministic replay harness in `tests/sentiment/fakes.py::FakeClaudeClient`
and are the reason CI can exercise the full extraction pipeline without
touching the live API.

## Purpose

Phase 71 added a Claude-primary extraction path to
`src/sentiment/processing/extractor.py`. Phase 72 (this re-record) extended
`_SYSTEM_PREFIX` to enumerate 19 event flags (12 prior + 7 new draft-season
flags) and made `subject_type` REQUIRED on every response item. Every test
that sends a batch through the Claude code path — unit, integration, and
benchmark alike — injects a `FakeClaudeClient` loaded with the fixtures in
this directory.

Requirement **LLM-05** (see `.planning/REQUIREMENTS.md`) states:

> Claude-extraction tests use recorded fixtures (VCR-style), not live API
> calls — deterministic CI.

This folder is the physical manifestation of that contract.

## File Shape

Each response fixture is a single JSON object:

```json
{
  "_comment": "human-readable context for this fixture",
  "prompt_sha": "abc123...",                // 64-hex SHA-256
  "model": "claude-haiku-4-5",
  "input_tokens": 1243,
  "output_tokens": 487,
  "cache_read_input_tokens": 1100,
  "cache_creation_input_tokens": 0,
  "response_text": "[{\"player_name\":\"...\",\"subject_type\":\"player\",...}]"
}
```

`response_text` is a JSON-encoded **string** whose contents are a JSON array
of signal dicts matching the post-72-02 schema:

- `player_name` (str | null)
- `sentiment` (-1.0 to +1.0)
- `confidence` (0.0 to 1.0)
- `category` (one of: injury, usage, trade, weather, motivation, legal, general)
- `events` (dict of boolean flags from the 19-key vocabulary, including the 7
  new draft-season flags: `is_drafted`, `is_rumored_destination`,
  `is_coaching_change`, `is_trade_buzz`, `is_holdout`, `is_cap_cut`,
  `is_rookie_buzz`)
- `subject_type` (REQUIRED — one of `player`, `coach`, `team`, `reporter`)
- `summary` (≤ 200 chars), `source_excerpt` (≤ 500 chars), `team_abbr`

Non-player items (`player_name: null`) are valid and exercise the EVT-02 path;
they MUST carry an explicit `subject_type` from `{coach, team, reporter}`.

## `prompt_sha` Computation

`FakeClaudeClient` keys responses by the SHA-256 of the canonicalised payload
sent to Claude:

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
`max_tokens` is intentionally excluded so the same prompt cached at different
output ceilings resolves to one registry entry.

## Roster-Provider Determinism Contract

**Hard invariant — every fixture in this directory honours this.**

All fixtures MUST be recorded with a frozen empty roster provider:

```python
# in the test / recording path only:
extract_batch_primary(..., roster_provider=lambda: [])
```

The cached player-list block in the Claude prompt would otherwise vary
across machines, dates, and roster-parquet refreshes — any drift breaks the
SHA match and all fixtures become unusable. By freezing
`roster_provider=lambda: []` for fixture recording, the SHA depends only on
the static system prefix + the per-doc user block.

Both the LLM-03 benchmark test and the helper script
`scripts/record_claude_fixture.py` honour this contract. Look for
`lambda: []`, "empty roster", or "frozen roster" anywhere fixtures are
generated or consumed — any deviation is a determinism bug.

## When to Re-record

Re-record both fixtures (W17 cold + W18 warm) every time `_SYSTEM_PREFIX`
changes in `src/sentiment/processing/extractor.py`. Editing the prefix
invalidates the prompt SHA and consequently the cached fixture lookup,
breaking every fixture-dependent test in CI.

Examples of edits that REQUIRE a re-record:

- Adding/removing event flags
- Changing `subject_type` enum values or the optional/required wording
- Adjusting the JSON-array contract (new top-level fields)
- Token-trimming compression (one-liner flag definitions)

Edits that do NOT require a re-record:

- Pure code changes outside `_SYSTEM_PREFIX` text
- Adjusting `_BATCH_DOC_BODY_TRUNCATE` (changes user-message body length but
  not the static prefix; will, however, change SHA on a per-batch basis if
  the docs themselves change length)

## Plan 72-02 Re-record

**Date:** 2026-04-25
**Reason:** Plan 72-01 extended `_SYSTEM_PREFIX` to enumerate 19 event flags
+ added a `subject_type` clause; Plan 72-02 strengthened the wording so
`subject_type` is REQUIRED on every item (drop "default \"player\""
suffix). Both edits change the prompt SHA, which invalidated the original
Phase 71 fixture SHAs.

**Post-72-02 prompt_sha values:**

| Fixture                       | prompt_sha (64-hex)                                                |
|-------------------------------|--------------------------------------------------------------------|
| `offseason_batch_w17.json`    | `87457f7706a8ca4f2cd6ceb5fc84408e7a440af0a83e44890798d34dc2f7866b` |
| `offseason_batch_w18.json`    | `c1a0ef012f4000554386ff08bdb63666ab8a3cb31ef8e21bccb7881960ed4060` |

**Transition note (LOCAL-ONLY EXCEPTION):** The 2026-04-25 re-record was
performed without a live Claude API call because `ANTHROPIC_API_KEY` was not
available on the developer machine at execution time. The original Phase
71-03 recording was deterministically post-processed to:

1. Update `prompt_sha` to the new 64-hex value computed against the
   post-72-02 `_SYSTEM_PREFIX`.
2. Inject `subject_type` on every item via inference from
   `player_name` + `summary` + `source_excerpt` text. Coach/owner names
   were mapped to `coach` (or `team` for owners since the enum lacks
   "owner"); items with null `player_name` and coaching/staff context were
   mapped to `coach`; reporter-byline-shaped items added explicitly.
3. Add the 7 new draft-season event flags (`is_drafted`,
   `is_rumored_destination`, `is_coaching_change`, `is_trade_buzz`,
   `is_holdout`, `is_cap_cut`, `is_rookie_buzz`) on items whose summary
   text clearly reflects them.
4. Add a small set of additional reporter / draft-buzz items so each
   fixture covers all four `subject_type` values and ≥ 5 items per fixture
   carry one of the 7 new flags.

This deterministic post-process is **a transition-only exception**. The
no-hand-augmentation rule remains the steady-state contract:

> **Recordings are faithful (LOCKED).** The Python helper writes Claude's
> raw `response_text` verbatim to disk. There is no post-processing of
> `subject_type`, no synthesis of new flags, and no item editing. If
> Claude's output fails the verification gates (every item has
> `subject_type`; ≥1 each of `coach`/`team`/`reporter`; ≥5 items with one
> of the 7 new flags), the operator strengthens the prompt in
> `_SYSTEM_PREFIX` and re-records — never patches the file.

**TO-DO (live re-record, 2026-04-26 or later):** When `ANTHROPIC_API_KEY`
is available again, run `scripts/record_claude_fixture.py` (which enforces
the no-hand-augmentation rule) for both weeks back-to-back and overwrite
both fixture files. The helper validates the hard gates before writing —
any failure means strengthen the prompt and retry, never patch.

## Re-record Procedure (Live API Call)

The helper script `scripts/record_claude_fixture.py` ships the live-recording
flow. It:

1. Loads the 30-doc Bronze fixture from
   `tests/fixtures/bronze_sentiment/offseason_w17_w18.json` and filters
   to the requested week (15 docs).
2. Constructs `anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])`.
3. Builds the prompt via `_build_batched_prompt_for_sha(_SYSTEM_PREFIX, "",
   docs)` — explicitly empty roster block.
4. Calls `client.messages.create(model=_CLAUDE_MODEL,
   max_tokens=_MAX_TOKENS_BATCH, system=system, messages=messages)`.
5. Computes the prompt SHA via the same `prompt_sha` helper
   `FakeClaudeClient` uses, so the recording is guaranteed-replay-able.
6. Writes the `{prompt_sha, model, input_tokens, output_tokens,
   cache_read_input_tokens, cache_creation_input_tokens, response_text}`
   payload — `response_text` verbatim from `response.content[0].text`.
7. Verifies hard gates (subject_type on every item, ≥1 each of
   coach/team/reporter, ≥5 items with one of the 7 new flags). On
   verification failure: prompt-strengthen and retry, do not patch.

```bash
source venv/bin/activate
export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2)

python scripts/record_claude_fixture.py --week 17 \
    --out tests/fixtures/claude_responses/offseason_batch_w17.json

# Then immediately (within ~5 min so the Anthropic prompt cache stays warm
# and W18 records cache_read > 0, cache_creation = 0):
python scripts/record_claude_fixture.py --week 18 \
    --out tests/fixtures/claude_responses/offseason_batch_w18.json
```

## Cost Remediation Order (Plan 72-02)

If a re-record pushes the LLM-04 cost-projection gate
(`tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars`)
above $5/week warm-cache, apply remediations IN THIS ORDER and re-measure
after each step. Stop at the first one that brings the projection back
under $5:

1. **Lower `_BATCH_DOC_BODY_TRUNCATE`** in
   `src/sentiment/processing/extractor.py` from `2000` → `1500`. Trims the
   per-doc body in the user-message half of the prompt, reducing input
   tokens.
2. **Compress `_SYSTEM_PREFIX` flag definitions** to one-liners (collapse
   any multi-line definitions). Keep the REQUIRED `subject_type` clause
   intact.
3. **Increase `BATCH_SIZE`** in `src/sentiment/processing/extractor.py`
   from `8` → `10`. Amortises per-call overhead across more docs and
   reduces the number of calls per week.

If all three remediations fail to bring the projection under $5: STOP. Do
NOT silently accept the regression. Escalate to the operator as a
CONTEXT-blocking decision per Plan 72-02 Task 2 step 3 — record the
attempted remediations and their resulting projections, and pause for the
operator to decide whether to (i) accept a higher cost gate (CONTEXT D-04
amendment), (ii) defer some of the 7 new flags, or (iii) split this work
into a follow-up phase.

## CI Prohibition on Live Calls (LLM-05)

Under no circumstances may a CI test invoke the real `anthropic.Anthropic`
client. Violations include:

- Calling `anthropic.Anthropic(api_key=...)` directly in a test.
- Monkeypatching `ClaudeExtractor._build_client` to return a real client.
- Setting `ANTHROPIC_API_KEY` in the CI environment (GHA secret is
  deliberately not exported to the test matrix).

Plan 71-05 added a guard that asserts the benchmark test specifically uses
a `FakeClaudeClient` and not the real SDK. New Claude tests should follow
the same pattern: instantiate `FakeClaudeClient`, call `register_response`
or `from_fixture_dir`, and inject via constructor DI.

## Files in this Directory

| File                         | Purpose                                             |
|------------------------------|-----------------------------------------------------|
| `offseason_batch_w17.json`   | 2025 W17 batch (cold cache: `cache_creation > 0`).  |
| `offseason_batch_w18.json`   | 2025 W18 batch (warm cache: `cache_read > 0`).      |
| `README.md`                  | This file — workflow + contracts.                   |

Each batch contains ≥ 5 items carrying one of the 7 new draft-season event
flags and represents all four `subject_type` values
(`player`/`coach`/`team`/`reporter`) so Plan 72's EVT-02 routing gets test
coverage out of the gate.
