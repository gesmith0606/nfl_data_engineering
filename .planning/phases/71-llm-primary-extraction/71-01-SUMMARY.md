---
phase: 71
plan: 01
subsystem: sentiment-extraction
tags: [schema, contracts, tdd, protocol, dataclass]
requires: []
provides:
  - PlayerSignal.summary
  - PlayerSignal.source_excerpt
  - PlayerSignal.team_abbr
  - PlayerSignal.extractor
  - BATCH_SIZE
  - _EXTRACTOR_NAME_RULE
  - _EXTRACTOR_NAME_CLAUDE_PRIMARY
  - _EXTRACTOR_NAME_CLAUDE_LEGACY
  - ClaudeClient (Protocol)
  - PipelineResult.claude_failed_count
  - PipelineResult.unresolved_player_count
  - PipelineResult.non_player_count
  - PipelineResult.non_player_items
  - PipelineResult.is_claude_primary
  - PipelineResult.cost_usd_total
  - Silver record "extractor" + "summary" top-level keys
affects:
  - src/sentiment/processing/extractor.py
  - src/sentiment/processing/pipeline.py
  - tests/sentiment/test_schema_contracts.py
tech-stack:
  added: []
  patterns:
    - "@runtime_checkable Protocol as DI seam (attribute-based shape)"
    - "Additive dataclass extension with safe defaults (no rename/remove)"
    - "TDD: RED commit (test-only) → GREEN commit (feat) per task"
key-files:
  created:
    - tests/sentiment/test_schema_contracts.py
  modified:
    - src/sentiment/processing/extractor.py
    - src/sentiment/processing/pipeline.py
decisions:
  - "Protocol uses attribute-based shape (messages: Any), not method, to match real anthropic.Anthropic SDK"
  - "All schema extensions are additive with safe defaults — no existing field renamed or removed"
  - "Extractor identity strings live as module-level constants (_EXTRACTOR_NAME_*) for single-source-of-truth"
metrics:
  duration: "~9 min"
  completed: "2026-04-24"
  tasks: 3
  files_modified: 3
  tests_added: 15
  tests_total_suite: 75
---

# Phase 71 Plan 01: Schema and Contracts Summary

Locked the additive schema evolution that Plans 71-02 through 71-05 build on: extended `PlayerSignal` with four optional fields (`summary`, `source_excerpt`, `team_abbr`, `extractor`), extended `PipelineResult` with six optional counter/flag/cost fields, added `extractor` + `summary` top-level keys to Silver records, and exposed a `@runtime_checkable` `ClaudeClient` Protocol so downstream tests can inject a fake via constructor DI. No behavior change — pure schema additive evolution, fully backward-compatible with existing RuleExtractor / ClaudeExtractor / pipeline call sites.

## Tasks Completed

| Task | Name | Commits (RED → GREEN) | Verification |
|------|------|----------------------|--------------|
| 1 | Extend PlayerSignal with new optional fields | `000c8b6` → `0f0c194` | 8 contract tests + 29 RuleExtractor regression tests pass |
| 2 | Extend PipelineResult + `_build_silver_record` | `63a5e83` → `746aa45` | 4 contract tests + 7 daily-pipeline resilience tests pass |
| 3 | Export ClaudeClient Protocol as DI seam | `1401522` → `bcd11df` | 4 contract tests + 75-test full sentiment suite pass |

## Key Changes

### 1. PlayerSignal (`src/sentiment/processing/extractor.py`)

Added four optional fields with safe defaults (immediately after `raw_excerpt`):

```python
summary: str = ""
source_excerpt: str = ""
team_abbr: Optional[str] = None
extractor: str = "rule"
```

Extended `to_dict()` to emit the four new keys at the top level while preserving the existing `events` sub-dict exactly. Updated the class docstring with a new "Claude-primary extensions (Plan 71-01, optional — safe defaults)" section.

### 2. Module-level Constants (`src/sentiment/processing/extractor.py`)

Added after `_MAX_TOKENS = 1024`:

```python
_EXTRACTOR_NAME_RULE = "rule"
_EXTRACTOR_NAME_CLAUDE_PRIMARY = "claude_primary"
_EXTRACTOR_NAME_CLAUDE_LEGACY = "claude_legacy"
BATCH_SIZE = 8
```

Single source of truth for extractor identity strings and Claude-primary batch size (Decision D-01, range 5-10).

### 3. ClaudeClient Protocol (`src/sentiment/processing/extractor.py`)

Added a `@runtime_checkable` Protocol between `PlayerSignal` and `ClaudeExtractor`:

```python
@runtime_checkable
class ClaudeClient(Protocol):
    messages: Any   # exposes .create(...) -> response
```

Attribute-based shape matches the real `anthropic.Anthropic` SDK (which exposes chained `.messages.create(...)`, not a flat method). Plan 71-02's `FakeClaudeClient` and Plan 71-03's batched extractor both consume this seam.

### 4. PipelineResult (`src/sentiment/processing/pipeline.py`)

Added six optional fields after `output_files`:

```python
claude_failed_count: int = 0
unresolved_player_count: int = 0
non_player_count: int = 0
non_player_items: List[Dict[str, Any]] = field(default_factory=list)
is_claude_primary: bool = False
cost_usd_total: float = 0.0
```

All defaults preserve prior `PipelineResult()` call sites. `non_player_items` uses `field(default_factory=list)` to avoid shared-default pitfalls (verified by a dedicated test).

### 5. Silver Record (`src/sentiment/processing/pipeline.py`)

Extended `_build_silver_record` to emit two new top-level keys immediately after `raw_excerpt`:

```python
"extractor": signal.extractor,   # defaults to "rule" via PlayerSignal
"summary": signal.summary,       # defaults to ""
```

Additive only; no existing key removed or renamed.

## Acceptance Criteria

All automated checks from the plan passed:

- [x] `grep -n "class PlayerSignal"` returns exactly one hit (line 92)
- [x] `grep` for new PlayerSignal fields returns 4 lines (185-188)
- [x] `grep` for new module constants returns 4 lines (40-47)
- [x] `grep` for 6 new PipelineResult fields returns 6 lines (90-95)
- [x] `grep` for `"extractor": signal.extractor` in pipeline.py returns 1 hit (line 353)
- [x] `grep` for `"summary": signal.summary` in pipeline.py returns 1 hit (line 354)
- [x] `grep -n "class ClaudeClient(Protocol)"` in extractor.py returns 1 hit (line 237)
- [x] `grep -n "@runtime_checkable"` in extractor.py returns 1 hit (line 236)
- [x] `python -c "from src.sentiment.processing.extractor import PlayerSignal; s=PlayerSignal(...); assert s.extractor=='rule' and s.summary=='' and s.source_excerpt=='' and s.team_abbr is None"` exits 0
- [x] `python -c "from src.sentiment.processing.extractor import BATCH_SIZE, _EXTRACTOR_NAME_CLAUDE_PRIMARY; assert BATCH_SIZE==8 and _EXTRACTOR_NAME_CLAUDE_PRIMARY=='claude_primary'"` exits 0
- [x] `python -c "from src.sentiment.processing.pipeline import PipelineResult; r=PipelineResult(); assert r.claude_failed_count==0 and r.non_player_items==[] and r.is_claude_primary is False and r.cost_usd_total==0.0"` exits 0
- [x] `python -c "from src.sentiment.processing.extractor import ClaudeClient, ClaudeExtractor; e=ClaudeExtractor(); assert hasattr(e, 'is_available')"` exits 0
- [x] Full sentiment suite green: `python -m pytest tests/sentiment/ -v` = **75 passed** in 135s

## Test Coverage

New file `tests/sentiment/test_schema_contracts.py` adds 15 tests across four test classes:

| Class | Tests | Scope |
|-------|-------|-------|
| `PlayerSignalNewFieldsTests` | 6 | Back-compat constructor, 4 new-field defaults, `to_dict()` keys |
| `ExtractorConstantsTests` | 2 | `BATCH_SIZE == 8`, 3 `_EXTRACTOR_NAME_*` strings |
| `PipelineResultNewFieldsTests` | 2 | All 6 new defaults, `default_factory` isolation |
| `SilverRecordExtractorFieldTests` | 2 | Default `"rule" / ""` emission, `claude_primary` override |
| `ClaudeClientProtocolTests` | 4 | Importable, runtime-checkable positive/negative, legacy extractor regression |

Regression coverage: all 7 `test_daily_pipeline_resilience.py` tests and 29 `test_rule_extractor_events.py` tests continued to pass after every change.

## Deviations from Plan

None — plan executed exactly as written. Each task followed the RED → GREEN TDD cycle with a dedicated test commit before the implementation commit.

## Threat Model Compliance

- **T-71-01-01 (Tampering on PlayerSignal schema):** Mitigated — all new fields have safe defaults, existing field order preserved, contract tests lock defaults.
- **T-71-01-02 (DoS on non_player_items default):** Accepted — standard `field(default_factory=list)` pattern; schema declaration has no unbounded growth.
- **T-71-01-03 (Information disclosure via source_excerpt):** Mitigated — existing `raw_excerpt` 500-char truncation contract remains; `source_excerpt` documented with same `<= 500 chars` bound in the PlayerSignal docstring. Downstream enforcement lands in Plan 71-03 where the Claude response is parsed.

## Commits

```
bcd11df feat(71-01): add ClaudeClient Protocol as DI seam for batched extractor
1401522 test(71-01): add failing tests for ClaudeClient Protocol DI seam
746aa45 feat(71-01): extend PipelineResult and Silver record with claude_primary fields
63a5e83 test(71-01): add failing tests for PipelineResult + Silver record extensions
0f0c194 feat(71-01): extend PlayerSignal with 4 optional fields + extractor constants
000c8b6 test(71-01): add failing schema contract tests for PlayerSignal fields
```

Six commits (three TDD pairs) with atomic RED → GREEN pattern per task.

## Known Stubs

None. All added fields are first-class schema surface; the `extractor` default `"rule"` is semantically correct (RuleExtractor is the current production path until Plan 71-04 wires the `claude_primary` mode).

## TDD Gate Compliance

Plan type is `execute`, not top-level `tdd`, but individual tasks carried `tdd="true"`. Each task paired a RED commit (`test(71-01): ...`) before a GREEN commit (`feat(71-01): ...`). No REFACTOR commits were needed — the GREEN implementations remained minimal and clean.

## Handoff to Plan 71-02

Plan 71-02 (`71-02-fixtures-and-fake-client-PLAN.md`) can now import:

```python
from src.sentiment.processing.extractor import ClaudeClient, BATCH_SIZE
```

and implement `FakeClaudeClient` in `tests/sentiment/fakes.py` as a `ClaudeClient`-satisfying double. No further schema work needed for Plans 71-02..05 — they consume these contracts directly.

## Self-Check: PASSED

Verified post-write:

- `src/sentiment/processing/extractor.py`: exists (contains `ClaudeClient`, `BATCH_SIZE`, 4 new PlayerSignal fields, 3 `_EXTRACTOR_NAME_*` constants)
- `src/sentiment/processing/pipeline.py`: exists (contains 6 new PipelineResult fields, `"extractor"` + `"summary"` Silver record keys)
- `tests/sentiment/test_schema_contracts.py`: exists (15 tests across 5 classes)
- All 6 task commits present in `git log`: `000c8b6`, `0f0c194`, `63a5e83`, `746aa45`, `1401522`, `bcd11df`
- Full sentiment test suite: 75 passed, 0 failed
