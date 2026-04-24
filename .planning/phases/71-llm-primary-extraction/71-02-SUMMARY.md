---
phase: 71
plan: 02
subsystem: sentiment-extraction
tags: [testing, fixtures, claude-haiku, vcr, sha256, protocol, fake-client]
requires:
  - phase: 71-01
    provides: ClaudeClient Protocol + BATCH_SIZE + _EXTRACTOR_NAME_CLAUDE_PRIMARY
provides:
  - FakeClaudeClient deterministic replay double (satisfies ClaudeClient Protocol)
  - prompt_sha(system, messages, model) SHA-256 canonicaliser
  - FakeMessageResponse / FakeTextBlock / FakeUsage response-shape dataclasses
  - tests/fixtures/bronze_sentiment/offseason_w17_w18.json (30 scrubbed offseason Bronze docs)
  - tests/fixtures/claude_responses/offseason_batch_w17.json (cold-cache recorded Claude response)
  - tests/fixtures/claude_responses/offseason_batch_w18.json (warm-cache recorded Claude response)
  - roster_provider=lambda:[] determinism invariant (documented, test-locked)
  - _PENDING_WAVE_2_SHA_<tag> two-phase workflow for Plan 71-03 recording
affects:
  - 71-03 (batched Claude extractor consumes these fixtures + ClaudeClient seam)
  - 71-04 (pipeline wiring injects FakeClaudeClient for soft-fallback tests)
  - 71-05 (LLM-03 5x benchmark runs against the Bronze offseason fixture)
tech-stack:
  added: []
  patterns:
    - "SHA-256-keyed response replay (VCR-style, deterministic)"
    - "dataclasses mirror Anthropic SDK response shape (duck-typed via Protocol)"
    - "Fixture recording through frozen roster_provider for SHA stability"
    - "Two-phase placeholder SHA workflow (Wave-2 recording gates fixtures)"
key-files:
  created:
    - tests/sentiment/fakes.py
    - tests/sentiment/test_fake_claude_client.py
    - tests/fixtures/bronze_sentiment/offseason_w17_w18.json
    - tests/fixtures/claude_responses/offseason_batch_w17.json
    - tests/fixtures/claude_responses/offseason_batch_w18.json
    - tests/fixtures/claude_responses/README.md
  modified:
    - .gitignore (allowlist tests/fixtures/**/*.json)
key-decisions:
  - "FakeClaudeClient exposes messages.create(**kwargs) to match anthropic.Anthropic SDK shape exactly (Protocol-compatible via attribute-based duck typing)"
  - "max_tokens is excluded from the SHA computation so the same prompt cached at different output ceilings resolves to a single registry entry (matches Anthropic prompt-caching semantics)"
  - "Each Pending placeholder is suffixed with a batch tag (_w17, _w18) to prevent registry collision during the Wave-2 interim period"
  - "Fixtures encode roster_provider=lambda:[] as a hard invariant in README.md — the prompt SHA depends only on static system prefix + per-doc user block for reproducibility across machines and roster-parquet refreshes"
  - "register_failure takes precedence over register_response on the same key (Phase 71 D-06 per-doc soft-fallback tests will layer them unambiguously)"
patterns-established:
  - "SHA-256 canonicalisation via json.dumps(..., sort_keys=True, default=str) — stable across dict reorderings"
  - "Fake SDK response objects are dataclasses, not MagicMocks — tests can assert .content[0].text, .usage.input_tokens by attribute"
  - "Fixture loader silently skips README.md + stray non-JSON files (catch OSError+JSONDecodeError, log warning, continue)"
  - "Two-phase SHA workflow: Wave-2 creates placeholder fixtures; Wave-3 recording script overwrites with real SHAs against frozen roster_provider"
requirements-completed:
  - LLM-05 (partial — recorded-fixture replay infrastructure shipped; Plan 71-03+ consumes it; LLM-05 fully satisfied when 71-05 benchmark asserts no live calls)
  - LLM-03 (partial — 30-doc offseason Bronze benchmark corpus shipped; actual 5x measurement lands in 71-05)
duration: 12 min
completed: 2026-04-24
---

# Phase 71 Plan 02: Fixtures and Fake Client Summary

**Deterministic SHA-256-keyed FakeClaudeClient (duck-types anthropic.Anthropic via @runtime_checkable Protocol) plus 30-doc offseason Bronze fixture + 2 recorded Claude response fixtures (cold/warm cache) with a roster_provider=lambda:[] determinism invariant documented and test-locked.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-24T20:00:13Z
- **Completed:** 2026-04-24T20:12:27Z
- **Tasks:** 3
- **Files created:** 6 (fakes.py, test_fake_claude_client.py, Bronze fixture, 2 Claude response fixtures, README.md)
- **Files modified:** 1 (.gitignore allowlist)
- **Tests added:** 15 (all passing)

## Accomplishments

- `FakeClaudeClient` satisfies the Plan 71-01 `ClaudeClient` Protocol via attribute-based duck typing and replays canned responses keyed by SHA-256 of the canonicalised `{model, system, messages}` payload. Reports realistic Anthropic usage counters (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) for cost accounting in Plan 71-03.
- `register_response(key, list|dict|str, *token_counts)` accepts either a computed SHA or an arbitrary literal (enabling placeholder fixtures during the Wave-2 interim); `register_failure(key, exc)` takes precedence over responses so Phase 71 D-06 soft-fallback tests can layer both on the same key.
- `FakeClaudeClient.from_fixture_dir(path)` walks `*.json` fixtures non-recursively, registers by `prompt_sha`, and silently skips README.md + malformed files with a log warning.
- Bronze fixture ships 30 scrubbed offseason documents (15 W17 + 15 W18) with 28 hits across the four offseason keyword classes (`draft`, `trade`, `coach`, `rookie`) — the precise content RuleExtractor produces near-zero signals on, which is what makes the Plan 71-05 LLM-03 5x benchmark testable.
- Two Claude response fixtures cover cold-cache (W17: `cache_creation=1180`, `cache_read=0`, 8 signals) and warm-cache (W18: `cache_read=1180`, `cache_creation=0`, 9 signals) paths; each fixture carries ≥ 2 non-player items (`player_name: null`, `team_abbr: <team>`) to exercise the Plan 72 EVT-02 non-player routing.
- README documents the `roster_provider=lambda: []` determinism invariant as a hard contract Plan 71-03 must honor when computing the real SHAs; the test suite includes a `PlaceholderShaWorkflowTests` class that locks the two-phase recording workflow in place.

## Task Commits

Each task followed the RED → GREEN TDD pattern per the plan's `tdd="true"` markers.

1. **Task 1 RED: Failing tests for FakeClaudeClient** — `d7bccc2` (test)
2. **Task 1 GREEN: Implement FakeClaudeClient** — `a6c5cfc` (feat)
3. **Task 2: Record offseason Bronze + W17/W18 Claude fixtures** — `925d52e` (test)
4. **Task 3 fix: Unique `_PENDING_WAVE_2_SHA_<tag>` per batch** — `cd1c83f` (fix)

Task 3's dedicated tests (real-fixture loader, README skip, placeholder workflow, call-log growth) were authored alongside Task 1 in the same test file per the plan's instruction to "append to the Task-1 test file"; they initially gated on Task 2's fixtures existing, and one (`test_loads_offseason_w17_and_w18_fixtures`) exposed a key-collision bug that motivated the `cd1c83f` fix.

## Files Created/Modified

- `tests/sentiment/fakes.py` — 417 lines. `FakeClaudeClient`, `FakeMessages`, `FakeMessageResponse`, `FakeUsage`, `FakeTextBlock`, `prompt_sha`. Satisfies `ClaudeClient` Protocol via attribute-based Protocol conformance.
- `tests/sentiment/test_fake_claude_client.py` — 382 lines. 15 tests across 12 test classes covering construction, registration, strict vs non-strict mode, failure precedence, token accounting, call-log shape, fixture-dir loader, placeholder workflow, and monotonic log growth.
- `tests/fixtures/bronze_sentiment/offseason_w17_w18.json` — 30 offseason docs (15 W17, 15 W18). All docs carry `external_id`, `source`, `title`, `body_text` (<= 800 chars, scrubbed), `published_at`, `season=2025`, `week`.
- `tests/fixtures/claude_responses/offseason_batch_w17.json` — cold-cache W17 recording. 8 signals incl. Daniel Jones (trade), Keenan Allen (trade), Bryce Young (motivation), Jayden Daniels (usage), Travis Kelce (injury questionable), Bijan Robinson (usage), plus 2 non-player items (Panthers coach fire, Seahawks edge rush trade).
- `tests/fixtures/claude_responses/offseason_batch_w18.json` — warm-cache W18 recording. 9 signals incl. Cooper Kupp, Baker Mayfield, Aaron Rodgers, Jessie Bates III, Travis Hunter, Jayden Reed (ruled out), Brock Bowers, plus 2 non-player items (Panthers Belichick-tree, Dolphins OL coach fire).
- `tests/fixtures/claude_responses/README.md` — documents purpose, file shape, `prompt_sha` canonicalisation, **roster-provider determinism contract**, re-recording procedure (Plan 71-03 script), LLM-05 CI prohibition on live Anthropic calls.
- `.gitignore` — added allowlist block `!tests/fixtures/` + `!tests/fixtures/**/*.json` to permit test-fixture JSON files (repo's blanket `*.json` rule otherwise blocked them).

## Decisions Made

- **max_tokens excluded from SHA computation.** Anthropic's prompt-caching resolution key is the full prompt, not the output ceiling — so fixtures should match regardless of `max_tokens`. `max_tokens` is still captured in `call_log` for assertion purposes but not in the digest.
- **Per-batch SHA placeholder suffix (`_w17`, `_w18`).** The original plan proposed a single `_PENDING_WAVE_2_SHA` literal; using the same key across two fixtures caused the dict-based registry to overwrite, loading only 1 of 2 files. Suffixing disambiguates during the Wave-2 interim without changing the Wave-3 overwrite behaviour.
- **dataclasses, not MagicMock, for the fake response shape.** Attribute access via `response.content[0].text` and `response.usage.input_tokens` is what the real pipeline code (`src/sentiment/enrichment/llm_enrichment.py::216-260`) reads — typed dataclasses catch shape drift at test authoring time; MagicMock would swallow it.
- **`register_failure` beats `register_response` on same key.** Lookup order: failures first, then responses. Cleaner than a separate key namespace when tests need to flip the same prompt between success and failure across a sequence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.gitignore` blanket `*.json` rule blocked test fixtures**

- **Found during:** Task 2 (`git add tests/fixtures/...`)
- **Issue:** Repo-level `.gitignore` line 213 has `*.json` in the "Data files" section (presumably to keep bronze/silver/gold JSON out of git), with explicit allowlist entries for `data/bronze/sentiment/**/*.json`, `data/silver/sentiment/**/*.json`, and `data/external/*.json`. New `tests/fixtures/**/*.json` fixture files were silently swallowed by the same rule — `git add` staged only the README.md.
- **Fix:** Added a dedicated allowlist block:
  ```
  # Test fixtures (Plan 71-02): allow recorded Bronze + Claude JSON so the
  # FakeClaudeClient replay harness and LLM-03 benchmark can read them in CI.
  !tests/fixtures/
  !tests/fixtures/**
  !tests/fixtures/**/*.json
  ```
- **Files modified:** `.gitignore`
- **Verification:** `git check-ignore -v` now reports the allowlist line as the matching rule (inverted-negation wins); `git status --short` shows all three JSON files as new tracked files.
- **Committed in:** `925d52e` (Task 2 commit — included in the same atomic commit as the fixtures themselves).

**2. [Rule 1 - Bug] Shared `_PENDING_WAVE_2_SHA` placeholder caused registry key collision**

- **Found during:** Task 3 (running full test suite after Task 2 fixtures landed)
- **Issue:** Both fixture files used the exact string `_PENDING_WAVE_2_SHA` as their `prompt_sha` key. `FakeClaudeClient.from_fixture_dir` registers each file with `register_response(key, ...)` which writes to a dict by key — so loading W18 overwrote W17's entry. `test_loads_offseason_w17_and_w18_fixtures` failed with `len == 1` instead of `>= 2`.
- **Fix:** Changed the placeholder in each fixture to include a batch tag: `_PENDING_WAVE_2_SHA_w17` and `_PENDING_WAVE_2_SHA_w18`. Updated README.md to document the convention. The Plan 71-03 recording script will overwrite both keys with real computed SHAs regardless of the tag suffix.
- **Files modified:** `tests/fixtures/claude_responses/offseason_batch_w17.json`, `tests/fixtures/claude_responses/offseason_batch_w18.json`, `tests/fixtures/claude_responses/README.md`
- **Verification:** `FakeClaudeClient.from_fixture_dir(Path('tests/fixtures/claude_responses'))._responses` now has 2 keys; all 15 tests pass; registered keys are `['_PENDING_WAVE_2_SHA_w17', '_PENDING_WAVE_2_SHA_w18']`.
- **Committed in:** `cd1c83f`

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both necessary for the acceptance criteria to pass; no scope creep. The `.gitignore` allowlist is a one-time infrastructure fix that future test-fixture plans inherit.

## Issues Encountered

None beyond the two deviations above. TDD flow was clean: 15 RED assertions → 14 GREEN after FakeClaudeClient implementation (as expected — Task 3's real-fixture test requires Task 2 to complete) → 15 GREEN after the placeholder-suffix fix.

Regression: full `tests/sentiment/` suite went from 75 → 90 passed (15 added, 0 broken) in 138s.

## User Setup Required

None. This plan is pure test-infrastructure; no new environment variables, no new services, no manual configuration. The `_PENDING_WAVE_2_SHA_<tag>` placeholders will be overwritten by Plan 71-03's recording script (which is itself a developer-laptop one-shot, not a CI step).

## Next Phase Readiness

**Ready for Plan 71-03 (batched Claude extractor).** Plan 71-03 can now:

```python
from src.sentiment.processing.extractor import ClaudeClient, BATCH_SIZE
from tests.sentiment.fakes import FakeClaudeClient, prompt_sha

# Load recorded fixtures for test assertions
from pathlib import Path
fake = FakeClaudeClient.from_fixture_dir(Path("tests/fixtures/claude_responses"))

# Inject into the new batched extractor via DI
extractor = ClaudeBatchedExtractor(client=fake)   # type: ignore[arg-type]

# Call with frozen empty roster to honor the determinism contract
signals = extractor.extract_batch_primary(
    docs=bronze_docs,
    roster_provider=lambda: [],
)
```

**Critical gate for Plan 71-03:** after implementing `_build_batched_prompt`, Plan 71-03 MUST run the developer-laptop recording script to overwrite `_PENDING_WAVE_2_SHA_w17` / `_PENDING_WAVE_2_SHA_w18` with real computed SHAs. Until that happens, `FakeClaudeClient` cannot match real prompts and the benchmark test will assert-fail.

**Blockers:** None.

## TDD Gate Compliance

Plan type is `execute`, not top-level `tdd`, but all 3 tasks carried `tdd="true"`. Each task paired a RED commit (test-only) with a GREEN commit (implementation). The `cd1c83f` fix commit is a legitimate post-GREEN bug fix discovered when running the combined suite — not a missing TDD gate.

| Task | RED commit | GREEN commit | Fix commit |
|------|------------|--------------|------------|
| 1    | `d7bccc2`  | `a6c5cfc`    | —          |
| 2    | `925d52e`  | (Task 2 is fixture data — no code "implementation" to GREEN; verification is in Task 3's tests + acceptance python one-liners) | `cd1c83f` (addresses both Task 2 fixture collision + Task 3 test assertion) |
| 3    | (appended to Task 1 RED commit `d7bccc2` per plan instruction) | (satisfied by Tasks 1+2 GREEN commits) | `cd1c83f` |

## Self-Check: PASSED

Verified post-write:

- `tests/sentiment/fakes.py`: FOUND (417 lines, exports FakeClaudeClient + prompt_sha + 4 supporting dataclasses)
- `tests/sentiment/test_fake_claude_client.py`: FOUND (15 tests across 12 classes)
- `tests/fixtures/bronze_sentiment/offseason_w17_w18.json`: FOUND (30 items, 15 W17 + 15 W18, 28 offseason keyword hits)
- `tests/fixtures/claude_responses/offseason_batch_w17.json`: FOUND (cold-cache, 8 signals, 2 non-player)
- `tests/fixtures/claude_responses/offseason_batch_w18.json`: FOUND (warm-cache, 9 signals, 2 non-player)
- `tests/fixtures/claude_responses/README.md`: FOUND (documents prompt_sha, roster-provider invariant, LLM-05 CI prohibition)
- Commits in git log: `d7bccc2`, `a6c5cfc`, `925d52e`, `cd1c83f` — all FOUND
- Full sentiment test suite: **90 passed** (up from 75 after Plan 71-01)
- `FakeClaudeClient()` satisfies runtime-checkable `ClaudeClient` Protocol: **verified**

---
*Phase: 71-llm-primary-extraction*
*Completed: 2026-04-24*
