---
phase: 71-llm-primary-extraction
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/sentiment/processing/extractor.py
  - src/sentiment/processing/pipeline.py
  - tests/sentiment/test_schema_contracts.py
autonomous: true
requirements:
  - LLM-01
  - LLM-05
must_haves:
  truths:
    - "PlayerSignal carries the new optional `summary`, `source_excerpt`, `team_abbr`, and `extractor` fields; existing fields unchanged"
    - "Silver signal records carry an optional top-level `extractor` field with value `rule | claude_primary | claude_legacy`, defaulting to `rule` for back-compat"
    - "PipelineResult exposes `claude_failed_count`, `unresolved_player_count`, `non_player_count`, `non_player_items`, `is_claude_primary`, `cost_usd_total` fields (defaults preserve prior behavior)"
    - "A `ClaudeClient` Protocol exists in the extractor module so tests inject a fake without monkeypatching `_build_client`"
  artifacts:
    - path: "src/sentiment/processing/extractor.py"
      provides: "PlayerSignal with new fields + ClaudeClient Protocol + BATCH_SIZE/_EXTRACTOR_NAME constants"
      contains: "class ClaudeClient(Protocol)"
    - path: "src/sentiment/processing/pipeline.py"
      provides: "PipelineResult with new metric fields"
      contains: "is_claude_primary"
    - path: "tests/sentiment/test_schema_contracts.py"
      provides: "Schema contract tests for PlayerSignal, PipelineResult, Silver record shape"
      exports: ["test_player_signal_new_fields_default", "test_pipeline_result_new_counts", "test_silver_record_extractor_field"]
  key_links:
    - from: "tests/sentiment/test_schema_contracts.py"
      to: "src/sentiment/processing/extractor.py"
      via: "import PlayerSignal, ClaudeClient"
      pattern: "from src.sentiment.processing.extractor import"
    - from: "src/sentiment/processing/pipeline.py::_build_silver_record"
      to: "PlayerSignal.extractor"
      via: "serialization into Silver record dict"
      pattern: "\"extractor\":"
---

<objective>
Establish the schema contracts that Plans 71-02 through 71-05 build on. Add new optional fields to `PlayerSignal` (summary, source_excerpt, team_abbr, extractor), new optional counters to `PipelineResult`, and a `ClaudeClient` Protocol so downstream tests can inject a fake without monkeypatching. No behavior change — purely additive schema evolution locked in before implementation tasks begin.

Purpose: Avoid the "scavenger hunt" anti-pattern. Every later plan will import from these contracts directly.
Output: Extended `extractor.py`, extended `pipeline.py` dataclasses, and a dedicated contract test file.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/71-llm-primary-extraction/71-CONTEXT.md
@src/sentiment/processing/extractor.py
@src/sentiment/processing/pipeline.py

<interfaces>
<!-- Key types downstream plans depend on. Locked in this plan. -->

Existing `PlayerSignal` in `src/sentiment/processing/extractor.py` (already has 12 event booleans + sentiment/confidence/category/raw_excerpt). This plan ADDS the following optional fields (all with safe defaults, never remove/rename existing ones):

```python
# PlayerSignal additions (append to dataclass, keep existing fields untouched)
summary: str = ""                  # <= 200 chars, 1-sentence, Claude-generated (empty for rule)
source_excerpt: str = ""           # <= 500 chars, raw snippet Claude cited (optional)
team_abbr: Optional[str] = None    # Non-player items carry the team; player items may populate as enrichment
extractor: str = "rule"            # "rule" | "claude_primary" | "claude_legacy"
```

Existing `PipelineResult` in `src/sentiment/processing/pipeline.py` (has 5 fields). This plan ADDS:

```python
# PipelineResult additions
claude_failed_count: int = 0              # per-doc soft fallback increments
unresolved_player_count: int = 0          # PlayerNameResolver.resolve() returned None
non_player_count: int = 0                 # Claude returned player_name=null item
non_player_items: List[Dict[str, Any]] = field(default_factory=list)
is_claude_primary: bool = False           # True when active extractor is claude_primary
cost_usd_total: float = 0.0               # sum of per-call costs (written by Plan 71-03)
```

New module-level constants in `src/sentiment/processing/extractor.py`:

```python
# Extractor identity strings (single source of truth — reuse everywhere)
_EXTRACTOR_NAME_RULE = "rule"
_EXTRACTOR_NAME_CLAUDE_PRIMARY = "claude_primary"
_EXTRACTOR_NAME_CLAUDE_LEGACY = "claude_legacy"

# Default batch size for claude_primary extraction (5-10 per D-01; default 8)
BATCH_SIZE = 8
```

New `ClaudeClient` Protocol (DI seam for tests) — **attribute-based shape** matching the real `anthropic.Anthropic` SDK:

```python
from typing import Protocol, Any, runtime_checkable

@runtime_checkable
class ClaudeClient(Protocol):
    """Minimal shape the extractor uses; `anthropic.Anthropic` satisfies it.

    Uses attribute access because `anthropic.Anthropic` exposes chained
    `.messages.create(...)`, not a method. `FakeClaudeClient` in
    `tests/sentiment/fakes.py` (Plan 71-02) matches this same shape.
    """
    messages: Any   # object with .create(model=..., max_tokens=..., system=..., messages=...) -> response
```

Note: the real `anthropic.Anthropic` exposes `.messages.create(...)`. Task 3 below defines the Protocol with an attribute named `messages` (not a method) — the batched extractor in Plan 71-03 calls `client.messages.create(...)` on both the real SDK and the test double. Exporting the Protocol makes the seam type-checkable.

Silver record shape (built in `pipeline._build_silver_record`) gains one optional top-level key (NON-BREAKING):

```python
{
    # ... all existing keys preserved ...
    "extractor": signal.extractor,    # NEW: defaults to "rule"
    "summary": signal.summary,        # NEW: empty string when absent
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend PlayerSignal with new optional fields</name>
  <files>src/sentiment/processing/extractor.py, tests/sentiment/test_schema_contracts.py</files>
  <read_first>
    - src/sentiment/processing/extractor.py (read full file — understand existing PlayerSignal shape and to_dict())
    - src/sentiment/processing/rule_extractor.py lines 1-120 (confirm it imports PlayerSignal and constructs it positionally in one place; we must not break that call site)
    - .planning/phases/71-llm-primary-extraction/71-CONTEXT.md (Decisions > Prompt Design & Batching, Downstream Integration)
  </read_first>
  <behavior>
    - Test: `PlayerSignal(player_name="x", sentiment=0.0, confidence=0.5, category="general")` constructs without error (existing call sites unaffected)
    - Test: `PlayerSignal(...).summary == ""` by default
    - Test: `PlayerSignal(...).source_excerpt == ""` by default
    - Test: `PlayerSignal(...).team_abbr is None` by default
    - Test: `PlayerSignal(...).extractor == "rule"` by default
    - Test: `PlayerSignal(...).to_dict()` returns a dict that contains `"summary"`, `"source_excerpt"`, `"team_abbr"`, `"extractor"` keys alongside existing ones — existing `events` sub-dict preserved intact
    - Test: module exposes `BATCH_SIZE == 8`, `_EXTRACTOR_NAME_RULE == "rule"`, `_EXTRACTOR_NAME_CLAUDE_PRIMARY == "claude_primary"`, `_EXTRACTOR_NAME_CLAUDE_LEGACY == "claude_legacy"`
  </behavior>
  <action>
    1. Open `src/sentiment/processing/extractor.py`.
    2. After the existing 12 event bool fields and `raw_excerpt: str = ""` in `PlayerSignal`, append four new optional fields exactly as specified in the `<interfaces>` block above (`summary`, `source_excerpt`, `team_abbr`, `extractor`). Use `Optional[str]` for `team_abbr` (import already present). Defaults MUST be as listed (empty strings, None, "rule").
    3. Extend `PlayerSignal.to_dict()` to include the four new keys at the top level (next to `raw_excerpt`). Do NOT alter the existing `events` sub-dict or any existing key.
    4. After the `_MAX_TOKENS = 1024` constant, add the four new module-level constants (`_EXTRACTOR_NAME_RULE`, `_EXTRACTOR_NAME_CLAUDE_PRIMARY`, `_EXTRACTOR_NAME_CLAUDE_LEGACY`, `BATCH_SIZE`) exactly as listed in `<interfaces>`.
    5. Create `tests/sentiment/test_schema_contracts.py` with six pytest functions asserting the behavior bullets above. Use the `PlayerSignal` constructor with only the 4 required positional/kw fields to lock in back-compat. One function should assert the constants exist and have the expected string/int values.
    6. Run `pytest tests/sentiment/test_schema_contracts.py -v` and confirm all pass.
    7. Run `pytest tests/sentiment/test_rule_extractor_events.py -v` to confirm no rule-extractor regression (RuleExtractor constructs PlayerSignal and still passes).
    Why this shape: per CONTEXT.md "Silver schema gains an optional `extractor` field per signal record" (non-breaking) and "PlayerSignal dataclass also gets the matching field." The four new fields are ALL optional with safe defaults so RuleExtractor is unaffected and legacy tests keep passing. Do NOT remove or rename any existing field.
  </action>
  <acceptance_criteria>
    - `grep -n "class PlayerSignal" src/sentiment/processing/extractor.py` returns exactly one hit
    - `grep -nE "^\s+(summary|source_excerpt|team_abbr|extractor): " src/sentiment/processing/extractor.py` returns 4 lines
    - `grep -nE "^(BATCH_SIZE|_EXTRACTOR_NAME_RULE|_EXTRACTOR_NAME_CLAUDE_PRIMARY|_EXTRACTOR_NAME_CLAUDE_LEGACY) = " src/sentiment/processing/extractor.py` returns 4 lines
    - `python -c "from src.sentiment.processing.extractor import PlayerSignal; s=PlayerSignal(player_name='x', sentiment=0.0, confidence=0.5, category='general'); assert s.extractor=='rule' and s.summary=='' and s.source_excerpt=='' and s.team_abbr is None"` exits 0
    - `python -c "from src.sentiment.processing.extractor import BATCH_SIZE, _EXTRACTOR_NAME_CLAUDE_PRIMARY; assert BATCH_SIZE==8 and _EXTRACTOR_NAME_CLAUDE_PRIMARY=='claude_primary'"` exits 0
    - `python -m pytest tests/sentiment/test_schema_contracts.py tests/sentiment/test_rule_extractor_events.py -v` all pass
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_schema_contracts.py tests/sentiment/test_rule_extractor_events.py -v</automated>
  </verify>
  <done>PlayerSignal has 4 new optional fields with safe defaults; new constants exported; existing RuleExtractor tests still pass; contract tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Extend PipelineResult and _build_silver_record with new metrics + extractor field</name>
  <files>src/sentiment/processing/pipeline.py, tests/sentiment/test_schema_contracts.py</files>
  <read_first>
    - src/sentiment/processing/pipeline.py (full file — already read; re-confirm PipelineResult shape and _build_silver_record)
    - tests/sentiment/test_daily_pipeline_resilience.py (confirm any existing PipelineResult-shape assertions still pass with new default-zero fields)
  </read_first>
  <behavior>
    - Test: `PipelineResult()` constructs with no args and exposes `claude_failed_count==0`, `unresolved_player_count==0`, `non_player_count==0`, `non_player_items==[]`, `is_claude_primary is False`, `cost_usd_total==0.0` as defaults — and all 5 existing fields still default as before
    - Test: Calling `pipeline._build_silver_record(doc={...}, signal=PlayerSignal(player_name='X', sentiment=0.1, confidence=0.5, category='general'), player_id='00-0001', season=2025, week=17, source='rss')` returns a dict whose `"extractor"` key equals `"rule"` (from PlayerSignal default), and whose `"summary"` key equals `""`
    - Test: When signal is constructed with `extractor="claude_primary"` and `summary="Kelce limited at practice"`, the built record reflects those values
  </behavior>
  <action>
    1. Open `src/sentiment/processing/pipeline.py`.
    2. Extend the `PipelineResult` dataclass (after `output_files`) with the six new fields listed in the `<interfaces>` block above. Use `field(default_factory=list)` for `non_player_items`. Import `Any` from typing if not already present (it is).
    3. Extend `_build_silver_record()` to include two new top-level keys in the returned dict — `"extractor": signal.extractor` and `"summary": signal.summary` — immediately after the existing `"raw_excerpt"` key. Do not remove or rename any existing key.
    4. Add new test functions to `tests/sentiment/test_schema_contracts.py`:
       - `test_pipeline_result_new_counts` — `PipelineResult()` with no args has all 6 new fields at their documented defaults
       - `test_silver_record_extractor_field_defaults_to_rule` — build a record with a default-constructed `PlayerSignal` and assert `record["extractor"] == "rule"` and `record["summary"] == ""`
       - `test_silver_record_extractor_field_reflects_claude_primary` — construct `PlayerSignal(...summary="x", extractor="claude_primary")` and assert the built record carries them
    5. Run `pytest tests/sentiment/test_schema_contracts.py tests/sentiment/test_daily_pipeline_resilience.py -v` — all pass.
    Why: per CONTEXT.md "Silver schema gains an optional `extractor` field per signal record" and "PipelineResult emits new metrics." Additive only — no existing consumer of PipelineResult or Silver records should break.
  </action>
  <acceptance_criteria>
    - `grep -nE "^\s+(claude_failed_count|unresolved_player_count|non_player_count|non_player_items|is_claude_primary|cost_usd_total): " src/sentiment/processing/pipeline.py` returns 6 lines
    - `grep -nE "\"extractor\": signal.extractor" src/sentiment/processing/pipeline.py` returns 1 hit
    - `grep -nE "\"summary\": signal.summary" src/sentiment/processing/pipeline.py` returns 1 hit
    - `python -c "from src.sentiment.processing.pipeline import PipelineResult; r=PipelineResult(); assert r.claude_failed_count==0 and r.non_player_items==[] and r.is_claude_primary is False and r.cost_usd_total==0.0"` exits 0
    - `python -m pytest tests/sentiment/test_schema_contracts.py tests/sentiment/test_daily_pipeline_resilience.py -v` all pass
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_schema_contracts.py tests/sentiment/test_daily_pipeline_resilience.py -v</automated>
  </verify>
  <done>PipelineResult gains 6 new default-zero/default-empty fields; Silver record shape gains `extractor` + `summary` top-level keys; schema contract tests cover both.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Export ClaudeClient Protocol as DI seam</name>
  <files>src/sentiment/processing/extractor.py, tests/sentiment/test_schema_contracts.py</files>
  <read_first>
    - src/sentiment/processing/extractor.py (confirm current `_build_client` + `_call_claude` shape; we keep them for legacy `"claude"` mode)
    - src/sentiment/enrichment/llm_enrichment.py lines 110-150 (reuse fail-open `_build_client` pattern per CONTEXT "Established Patterns")
  </read_first>
  <behavior>
    - Test: `from src.sentiment.processing.extractor import ClaudeClient` succeeds (name is exported)
    - Test: `isinstance` check via Protocol works with a hand-rolled duck-typed object (runtime_checkable Protocol)
    - Test: existing `ClaudeExtractor` legacy methods (`_call_claude`, `extract`, `extract_batch`) still work unchanged
  </behavior>
  <action>
    1. Open `src/sentiment/processing/extractor.py`.
    2. Add `from typing import Protocol, runtime_checkable` to the existing `from typing import` line (preserve existing imports — use `from typing import Any, Dict, List, Optional, Protocol, runtime_checkable`).
    3. After the `PlayerSignal` dataclass and BEFORE the `ClaudeExtractor` class, add:
       ```python
       @runtime_checkable
       class ClaudeClient(Protocol):
           """Minimal duck-typed surface for the Anthropic client.

           The real ``anthropic.Anthropic`` instance satisfies this Protocol
           via its ``.messages.create()`` attribute chain. ``FakeClaudeClient``
           in ``tests/sentiment/fakes.py`` (Plan 71-02) also satisfies it.

           This seam lets Plan 71-03 batched extractor be injected with a
           fake without monkeypatching ``_build_client``.

           Uses attribute access because ``anthropic.Anthropic`` exposes
           chained ``.messages.create(...)``, not a method.
           """
           messages: Any   # Exposes .create(model=..., max_tokens=..., system=..., messages=...)
       ```
    4. Do NOT touch the existing `ClaudeExtractor` class — it keeps working in the deprecated `"claude"` mode.
    5. Add three tests to `tests/sentiment/test_schema_contracts.py`:
       - `test_claude_client_protocol_importable` — `from src.sentiment.processing.extractor import ClaudeClient; assert ClaudeClient is not None`
       - `test_claude_client_protocol_runtime_check` — a class with a `.messages` attribute is recognized as a `ClaudeClient`
       - `test_legacy_claude_extractor_still_instantiable` — `ClaudeExtractor()` instantiates (client may be None without ANTHROPIC_API_KEY) and `is_available` property works
    6. Run `pytest tests/sentiment/test_schema_contracts.py -v` — all pass.
    Why: CONTEXT.md D-02 "Tests inject the fake client via constructor DI (no monkeypatching `_build_client`)" — a typed Protocol seam is the cleanest way. Plan 71-02 implements `FakeClaudeClient`; Plan 71-03 consumes the Protocol. Attribute-based shape matches the real `anthropic.Anthropic` SDK (which exposes chained `.messages.create(...)`, not a flat method).
  </action>
  <acceptance_criteria>
    - `grep -n "class ClaudeClient(Protocol)" src/sentiment/processing/extractor.py` returns 1 hit
    - `grep -n "@runtime_checkable" src/sentiment/processing/extractor.py` returns 1 hit
    - `python -c "from src.sentiment.processing.extractor import ClaudeClient, ClaudeExtractor; e=ClaudeExtractor(); assert hasattr(e, 'is_available')"` exits 0
    - `python -m pytest tests/sentiment/test_schema_contracts.py -v -k "claude_client or legacy_claude"` all pass
    - Full pytest sentiment suite still passes: `python -m pytest tests/sentiment/ -v`
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/ -v</automated>
  </verify>
  <done>ClaudeClient Protocol is importable and runtime-checkable; legacy ClaudeExtractor unchanged; all sentiment tests pass.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| test → module | Tests import dataclasses and constants; no secrets crossed |
| schema → downstream | Silver record shape is consumed by `enrich_silver_records` and `WeeklyAggregator` — additive keys only; no rename/drop |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-71-01-01 | Tampering | PlayerSignal schema | mitigate | All new fields have safe defaults; existing field order preserved; contract tests lock defaults |
| T-71-01-02 | Denial of Service | Dataclass default_factory for non_player_items | accept | `List[Dict]` default is standard pattern; no unbounded growth in schema declaration |
| T-71-01-03 | Information disclosure | `raw_excerpt`/`source_excerpt` fields | mitigate | Truncation to 500 chars (existing contract) remains; no new PII surface |
</threat_model>

<verification>
- `grep` checks above all pass
- `python -m pytest tests/sentiment/ -v` — entire sentiment suite green (existing 6 test files + new `test_schema_contracts.py`)
- `python -c "from src.sentiment.processing.extractor import PlayerSignal, ClaudeClient, BATCH_SIZE; from src.sentiment.processing.pipeline import PipelineResult; print('OK')"` prints OK
</verification>

<success_criteria>
- PlayerSignal carries the 4 new optional fields with documented defaults
- PipelineResult carries the 6 new optional counter/list/bool/float fields
- `_build_silver_record` emits `extractor` + `summary` top-level keys (defaulting to `rule` + `""`)
- `ClaudeClient` Protocol is importable and runtime-checkable
- No existing sentiment test regressed
</success_criteria>

<output>
After completion, create `.planning/phases/71-llm-primary-extraction/71-01-SUMMARY.md`.
</output>
