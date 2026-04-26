---
plan: 72-01-schema-rules-prompt
phase: 72-event-flag-expansion
status: complete
completed: 2026-04-25
requirements: [EVT-01]
commits: 3
---

# Plan 72-01: Schema, Rules, Prompt — SUMMARY

## What Was Built

Foundational schema + prompt + RuleExtractor extensions for the 7 new draft-season event flags. Phase 72 downstream plans consume this layer.

### Code Changes

| File | Change |
|------|--------|
| `src/sentiment/processing/extractor.py` | PlayerSignal gains 7 new bool fields (`is_drafted`, `is_rumored_destination`, `is_coaching_change`, `is_trade_buzz`, `is_holdout`, `is_cap_cut`, `is_rookie_buzz`) + `subject_type: str = "player"` field with `__post_init__` normalizer. `_EVENT_FLAG_KEYS` frozenset extended to 19 entries. New `_VALID_SUBJECT_TYPES = {"player","coach","team","reporter"}` constant. `_SYSTEM_PREFIX` updated to enumerate 19 flags + REQUIRED `subject_type` per CONTEXT Phase 72 Schema Note. `to_dict()` events sub-dict carries the 7 new keys. |
| `src/sentiment/processing/rule_extractor.py` | 7 new high-precision regex patterns (drafted/rumored/coaching/trade-buzz/holdout/cap-cut/rookie-buzz). Confidence cap 0.5 (zero-cost dev fallback only — Claude is the production producer). |

### Tests

| File | Change |
|------|--------|
| `tests/sentiment/test_schema_contracts.py` | Extended schema contract tests cover the 7 new flag fields, subject_type validator, normalizer behavior, and to_dict() output shape. |
| `tests/sentiment/test_rule_extractor_events.py` | New file (was placeholder); 43 tests for the 7 new keyword patterns covering positive matches, negative cases, case-insensitivity, and confidence cap. |

## Test Results

- `tests/sentiment/test_schema_contracts.py` — all passing
- `tests/sentiment/test_rule_extractor_events.py` — 43/43 passing
- Full sentiment suite: **190/191 passing**

### Known Failure (Expected)

- `tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason` — FAILS as expected. Cause: changing `_SYSTEM_PREFIX` invalidates the prompt SHA, so `FakeClaudeClient` no longer matches the recorded W17/W18 fixtures. Plan 72-02 re-records the fixtures and restores LLM-03. This is the documented expected breakage in CONTEXT D-04 ("VCR fixtures re-recorded so signals include the new flags where applicable. The fixture `prompt_sha` updates because the prompt text changed.").

## Commits

- `3bcfc26` — `test(72-01): add failing tests for 7 new event flags + subject_type schema` (RED)
- `3cf2996` — `feat(72-01): extend PlayerSignal with 7 event flags + subject_type validator` (GREEN — Task 2)
- `e2af383` — `feat(72-01): add RuleExtractor patterns for 7 new draft-season flags` (Task 3)

## Self-Check: PASSED

- [x] PlayerSignal carries 7 new bool fields (default False) + `subject_type` field
- [x] `_EVENT_FLAG_KEYS` frozenset = 19 entries
- [x] `_VALID_SUBJECT_TYPES` frozenset = 4 entries
- [x] `EXTRACTION_PROMPT` and `_SYSTEM_PREFIX` instruct Claude to emit `subject_type` as REQUIRED
- [x] 7 new RuleExtractor patterns added with confidence cap 0.5
- [x] All schema-contract + rule-extractor-events tests pass
- [x] LLM-03 benchmark failure is documented expected; 72-02 will resolve

## Handoff to Plan 72-02

Plan 72-02 must:
1. Re-record W17 + W18 Claude fixtures using the new `_SYSTEM_PREFIX` (per Phase 71 determinism contract: `roster_provider=lambda: []`).
2. Verify every recorded item has `subject_type` populated (per CONTEXT amendment + the strengthened prompt; if not, strengthen the prompt further — never hand-augment).
3. Re-measure cost projection BEFORE deciding green; locked remediation order: `_BATCH_DOC_BODY_TRUNCATE` → `_SYSTEM_PREFIX` compression → `BATCH_SIZE` increase. No silent regression accepted.
4. Restore LLM-03 5× and LLM-04 <$5/wk gates.
