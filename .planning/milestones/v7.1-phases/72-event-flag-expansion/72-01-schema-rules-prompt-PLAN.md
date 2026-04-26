---
phase: 72
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/sentiment/processing/extractor.py
  - src/sentiment/processing/rule_extractor.py
  - tests/sentiment/test_schema_contracts.py
  - tests/sentiment/test_rule_extractor_events.py
autonomous: true
requirements:
  - EVT-01
tags: [event-flags, schema, rule-patterns, prompt, additive-only]
must_haves:
  truths:
    - "PlayerSignal accepts 7 new boolean fields with default False and roundtrips through to_dict() under an `events` sub-dict"
    - "PlayerSignal.subject_type defaults to 'player' and accepts {player, coach, team, reporter}; values outside that set normalise to 'player'"
    - "All 12 existing event flags + the 7 new flags appear in the _EVENT_FLAG_KEYS frozenset (cardinality == 19)"
    - "EXTRACTION_PROMPT and _SYSTEM_PREFIX enumerate the 7 new flags AND the optional subject_type field"
    - "RuleExtractor emits at least one of the 7 new flags when its keyword pattern matches a fixture string"
    - "Schema contract tests + RuleExtractor pattern tests all pass under `python -m pytest tests/sentiment/ -k 'schema_contracts or rule_extractor_events' -v`"
  artifacts:
    - path: "src/sentiment/processing/extractor.py"
      provides: "PlayerSignal extended with 7 new bool fields + subject_type str + _EVENT_FLAG_KEYS_NEW frozenset; EXTRACTION_PROMPT + _SYSTEM_PREFIX updated with new flags + subject_type description"
      contains: "is_drafted"
      contains_2: "subject_type"
    - path: "src/sentiment/processing/rule_extractor.py"
      provides: "7 high-precision regex patterns for the new flags appended to _compile_patterns()"
      contains: "is_drafted"
    - path: "tests/sentiment/test_schema_contracts.py"
      provides: "extended class covering 7 new flag defaults + subject_type validation + to_dict() events sub-dict shape"
    - path: "tests/sentiment/test_rule_extractor_events.py"
      provides: "extended cases asserting each of the 7 new flags fires on its sentinel input string"
  key_links:
    - from: "src/sentiment/processing/extractor.py::PlayerSignal"
      to: "PlayerSignal.to_dict() -> events sub-dict"
      via: "every new bool field appears once in the dataclass body and once in to_dict() events"
      pattern: "is_drafted.*is_rumored_destination.*is_coaching_change.*is_trade_buzz.*is_holdout.*is_cap_cut.*is_rookie_buzz"
    - from: "src/sentiment/processing/rule_extractor.py::_compile_patterns"
      to: "PlayerSignal new flags"
      via: "events dict populated in PlayerSignal(...) constructor at the bottom of RuleExtractor.extract"
      pattern: "events\\.get\\(\"is_(drafted|rumored_destination|coaching_change|trade_buzz|holdout|cap_cut|rookie_buzz)\""
---

<objective>
Foundation plan for Phase 72: extend the sentiment schema additively with 7 new event flags + an optional `subject_type` field, update Claude's prompt + system prefix to enumerate the new vocabulary, and add high-precision RuleExtractor keyword patterns so the zero-cost dev path also produces the new flags.

Purpose: Every downstream plan (fixture re-record, pipeline routing, aggregator, API/frontend, backfill+audit) consumes this contract. Locking it first means Wave 2 fixtures can be recorded against the final prompt SHA, and Wave 3 / Wave 4 can rely on the additive Pydantic shape without re-validating field names.

Output: Modified `extractor.py` + `rule_extractor.py` with 19-flag vocabulary (12 existing + 7 new) and 4-value `subject_type` enum default `"player"`. Schema-contract + rule-pattern tests prove additivity (no rename, no drop).
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/72-event-flag-expansion/72-CONTEXT.md
@.planning/phases/71-llm-primary-extraction/71-SUMMARY.md
@CLAUDE.md
@.claude/rules/coding-style.md
@.claude/rules/testing.md

<interfaces>
<!-- LOCKED contracts from Phase 71 that this plan extends additively. -->

From src/sentiment/processing/extractor.py (Phase 71 final state):

```python
# Module-level constants (DO NOT rename — downstream plans depend on these strings):
_CLAUDE_MODEL = "claude-haiku-4-5"
_EXTRACTOR_NAME_RULE = "rule"
_EXTRACTOR_NAME_CLAUDE_PRIMARY = "claude_primary"
_EXTRACTOR_NAME_CLAUDE_LEGACY = "claude_legacy"
BATCH_SIZE = 8
_SYSTEM_PREFIX = """You are an NFL news analyst..."""  # full text in source
EXTRACTION_PROMPT = """Analyze this NFL news article..."""  # full text in source

_VALID_CATEGORIES = frozenset({"injury", "usage", "trade", "weather", "motivation", "legal", "general"})

_EVENT_FLAG_KEYS = frozenset({
    "is_ruled_out", "is_inactive", "is_questionable", "is_suspended", "is_returning",
    "is_traded", "is_released", "is_signed", "is_activated",
    "is_usage_boost", "is_usage_drop",
    "is_weather_risk",
})  # 12 existing flags

@dataclass
class PlayerSignal:
    player_name: str
    sentiment: float
    confidence: float
    category: str
    # 12 existing event bool fields, all default False
    is_ruled_out: bool = False
    is_inactive: bool = False
    is_questionable: bool = False
    is_suspended: bool = False
    is_returning: bool = False
    is_traded: bool = False
    is_released: bool = False
    is_signed: bool = False
    is_activated: bool = False
    is_usage_boost: bool = False
    is_usage_drop: bool = False
    is_weather_risk: bool = False
    raw_excerpt: str = ""
    # Phase 71 extensions
    summary: str = ""
    source_excerpt: str = ""
    team_abbr: Optional[str] = None
    extractor: str = "rule"

    def to_dict(self) -> Dict[str, Any]:
        # Returns {"player_name": ..., ..., "events": {12 flags}, ..., "extractor": ...}
```

From src/sentiment/processing/rule_extractor.py (Phase 61 final):

```python
# _compile_patterns() returns List[(re.Pattern, sentiment, category, events_dict)]
# Categories of patterns: _transaction (4), _injury (10), _role (4), _weather (4),
# _positive (2), _negative (2). Each entry tuple is (regex, sentiment_float, category, dict[str,bool]).
# RuleExtractor.extract() builds PlayerSignal(...) with events.get(flag_name, False)
# for every dataclass bool field. We add 7 new dataclass fields + populate them in the
# constructor identically.

_RULE_CONFIDENCE = 0.7  # Confidence ceiling for rule path; new patterns inherit this.
```

From tests/sentiment/test_schema_contracts.py (Phase 71 final, 12 test classes):

```python
class PlayerSignalNewFieldsTests(unittest.TestCase):
    """Tests for summary/source_excerpt/team_abbr/extractor (Phase 71 fields)"""

class PlayerSignalToDictTests(unittest.TestCase):
    """Tests events sub-dict has 12 keys (extend to 19)"""

class EventFlagKeysFrozensetTests(unittest.TestCase):
    """Tests _EVENT_FLAG_KEYS cardinality == 12 (extend to 19)"""
```

From tests/sentiment/test_rule_extractor_events.py (Phase 61 final):

```python
# Test format: parametrised cases where each rule produces a known flag from sentinel text.
# Pattern: assert PlayerSignal.is_<flag> is True after rule.extract({"title":..., "body_text":...})
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add 7 new event flags + subject_type to PlayerSignal schema (RED→GREEN)</name>
  <read_first>
    - src/sentiment/processing/extractor.py (full file — must understand PlayerSignal layout, _EVENT_FLAG_KEYS, to_dict structure, and existing additive-field convention)
    - tests/sentiment/test_schema_contracts.py (existing test classes — extend the same patterns)
  </read_first>
  <files>src/sentiment/processing/extractor.py, tests/sentiment/test_schema_contracts.py</files>
  <behavior>
    - Test 1: PlayerSignal(player_name="X", sentiment=0, confidence=0.5, category="general") has is_drafted == False (and same for is_rumored_destination, is_coaching_change, is_trade_buzz, is_holdout, is_cap_cut, is_rookie_buzz — 7 new defaults)
    - Test 2: PlayerSignal(...).subject_type == "player" by default
    - Test 3: PlayerSignal(subject_type="coach") roundtrips; PlayerSignal(subject_type="bogus") falls back to "player" (validated at construction via __post_init__ OR a module-level coercer used by Claude/Rule paths)
    - Test 4: PlayerSignal(is_drafted=True, is_coaching_change=True).to_dict()["events"] contains all 19 flag keys (12 existing + 7 new); is_drafted == True, is_coaching_change == True, all others False
    - Test 5: _EVENT_FLAG_KEYS frozenset cardinality == 19 and contains every new key string
    - Test 6 (regression): Phase 71 fields (summary, source_excerpt, team_abbr, extractor) still default the same way — copy/extend existing tests, do not delete them
  </behavior>
  <action>
    Per CONTEXT D-01 (locked):

    1. Edit `src/sentiment/processing/extractor.py`:
       - Extend `_EVENT_FLAG_KEYS` frozenset by appending exactly these 7 strings (in this order, comment block them as `# Draft-season events (Plan 72-01)`):
         `"is_drafted", "is_rumored_destination", "is_coaching_change", "is_trade_buzz", "is_holdout", "is_cap_cut", "is_rookie_buzz"`
       - Add 7 new boolean fields to `PlayerSignal` dataclass below `is_weather_risk` and above `raw_excerpt`, each `bool = False`, in the same order as the frozenset entries. Group them under a `# Draft-season events (Plan 72-01)` comment.
       - Add `subject_type: str = "player"` as the LAST field on `PlayerSignal` (below `extractor`). Document in the class docstring as: "One of {'player', 'coach', 'team', 'reporter'}; defaults to 'player' for back-compat with rule path which only emits player items. Phase 72 EVT-02 routes coach/team to team rollup and reporter to non_player_news Silver channel."
       - Add a `__post_init__` method that validates `subject_type`: if not in `frozenset({"player", "coach", "team", "reporter"})`, log a debug message and reset to `"player"`.
       - Extend `to_dict()` `events` sub-dict to include the 7 new flag keys (verbatim names) using `self.is_<flag>` values. Add a top-level key `"subject_type": self.subject_type`. Group the new event keys under `# Draft-season events (Plan 72-01)` inline comment.
       - Update `EXTRACTION_PROMPT` template (the legacy single-doc prompt): append the 7 new flag names to the `events: dict of boolean flags` enumeration in alphabetical order alongside existing keys.
       - Update `_SYSTEM_PREFIX` (the cached batched prompt): append "is_drafted, is_rumored_destination, is_coaching_change, is_trade_buzz, is_holdout, is_cap_cut, is_rookie_buzz" to the "Event flag keys:" line. Add a new line below it: `Optional subject_type field: "player" | "coach" | "team" | "reporter" (default "player").`
       - Do NOT modify `_item_to_signal` or `_item_to_claude_signal` constructor calls beyond passing the 7 new flags + subject_type via `events.get(...)` and `item.get("subject_type", "player")`. Mirror the existing pattern for is_weather_risk exactly. Subject_type lives at the top level of Claude's response item (not inside `events`).
       - Use Optional/List/Dict/frozenset imports from `typing` — no PEP 604 `|` syntax (Python 3.9 compat).

    2. Edit `tests/sentiment/test_schema_contracts.py`:
       - Add a new test class `PlayerSignalDraftSeasonFlagsTests(unittest.TestCase)` with the 6 behaviour tests above. Mirror the docstring + assertion style of `PlayerSignalNewFieldsTests`.
       - Add a new test class `PlayerSignalSubjectTypeTests(unittest.TestCase)` covering the 4 valid values + the bogus-value normalisation.
       - Extend the existing `_EVENT_FLAG_KEYS` cardinality assertion to expect 19 (search for `assertEqual(len(_EVENT_FLAG_KEYS), 12)` and update the literal).
       - Extend the existing `to_dict()` events-sub-dict shape assertion to assert the 19 keys (search for any `len(d["events"])` and update).

    3. Run the targeted tests, verify RED first by writing tests before edits (TDD), then GREEN after edits:
       `python -m pytest tests/sentiment/test_schema_contracts.py -v`

    4. Commit two commits per TDD discipline (RED then GREEN):
       - `test(72-01): add failing tests for 7 new event flags + subject_type schema`
       - `feat(72-01): extend PlayerSignal with 7 draft-season event flags + subject_type`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/sentiment/test_schema_contracts.py -v</automated>
  </verify>
  <done>
    All test_schema_contracts.py tests pass (existing 12 classes still green, 2 new classes pass). PlayerSignal accepts is_drafted/is_rumored_destination/is_coaching_change/is_trade_buzz/is_holdout/is_cap_cut/is_rookie_buzz as bool fields with default False. PlayerSignal.subject_type defaults to "player" and normalises invalid input. PlayerSignal(...).to_dict()["events"] contains all 19 keys. _EVENT_FLAG_KEYS cardinality == 19. EXTRACTION_PROMPT + _SYSTEM_PREFIX texts include the 7 new flag names + subject_type descriptor. Two commits land in git log with correct message prefixes.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add 7 RuleExtractor regex patterns for the new flags (RED→GREEN)</name>
  <read_first>
    - src/sentiment/processing/rule_extractor.py (full file — must understand _compile_patterns ordering, _PatternEntry tuple, and the existing 4-category structure: transaction/injury/role/weather/general)
    - tests/sentiment/test_rule_extractor_events.py (existing test format — mirror exactly)
  </read_first>
  <files>src/sentiment/processing/rule_extractor.py, tests/sentiment/test_rule_extractor_events.py</files>
  <behavior>
    - Test 1: Doc with title="Bears select WR Tate with No. 12 pick" + body containing "drafted by the Bears" → signals[0].is_drafted == True
    - Test 2: Doc with body "Mahomes rumored to be traded to the 49ers" → signals[0].is_rumored_destination == True (and is_traded stays False — these are different signals)
    - Test 3: Doc with body "Panthers fired head coach Reich after 4-12 season" OR "Detroit hired Ben Johnson as head coach" → signals[0].is_coaching_change == True
    - Test 4: Doc with body "Bears fielded calls on Allen in trade talks" → signals[0].is_trade_buzz == True
    - Test 5: Doc with body "Aaron Donald begins holdout" or "skipping mandatory minicamp" → signals[0].is_holdout == True
    - Test 6: Doc with body "Cowboys release Vander Esch for cap relief" → signals[0].is_cap_cut == True (cap-driven release, separate signal from generic is_released which may also fire)
    - Test 7: Doc with body "Carnell Tate surges up draft boards as 2026 prospect" → signals[0].is_rookie_buzz == True
    - Test 8 (precision): Doc with body "Patrick Mahomes threw for 350 yards" → NO new flags fire (high-precision contract per CONTEXT)
  </behavior>
  <action>
    Per CONTEXT "Implementation Decisions" → "RuleExtractor gains minimal keyword patterns" (locked):

    1. Edit `src/sentiment/processing/rule_extractor.py`:
       - Inside `_compile_patterns()`, after the `_weather` block (line ~302) and before `_positive`, add a new `_draft_season` block of 7 entries with this exact structure (each tuple = `(regex_str, sentiment_float, category_str, events_dict)`). Wrap each entry in `re.compile(..., re.IGNORECASE)` and append to `entries` via the same idiom (`for pat, sent, cat, evts in _draft_season: entries.append((re.compile(pat, re.IGNORECASE), sent, cat, evts))`).
       - Use BOUNDED quantifiers (no unbounded `.*` inside alternations) per the precision contract documented in the existing _compile_patterns docstring. Use `\b` word boundaries.
       - Suggested patterns (Claude's discretion per CONTEXT — adjust within these bounds):
         * `is_drafted`: `r"\b(?:drafted|selected)\s+(?:by|to)\s+the\s+\w{3,20}\b|\b(?:select|picked|takes)\s+(?:WR|RB|QB|TE|LB|CB|DE|DT|OL|S|K)\s+\w+\s+(?:at|with)\s+(?:No\.|pick|number)\s+\d{1,2}"` — sentiment 0.4, category "general"
         * `is_rumored_destination`: `r"\b(?:trade rumor|rumored to be (?:traded|dealt|moved|sent)|rumored destination|reportedly (?:headed|going) to)\b"` — sentiment 0.0, category "trade"
         * `is_coaching_change`: `r"\b(?:fired|hired|parted ways with|relieved of duties)\s+(?:head\s+)?coach\b|\b(?:head|offensive|defensive)\s+coordinator\s+(?:hired|fired|search)\b|\bcoaching\s+(?:search|vacancy|change)\b"` — sentiment -0.1, category "general"
         * `is_trade_buzz`: `r"\b(?:fielded calls on|gauging\s+(?:the\s+)?trade market|exploring trade options|in trade talks|on the (?:trade )?block)\b"` — sentiment -0.1, category "trade"
         * `is_holdout`: `r"\b(?:holdout|holding out|hold-out|skip(?:ping)?\s+(?:mandatory )?(?:minicamp|OTAs|training camp))\b"` — sentiment -0.3, category "trade"
         * `is_cap_cut`: `r"\b(?:released for cap (?:relief|space)|cap (?:cut|casualty)|cut for cap (?:relief|space)|salary[\s-]cap (?:cut|move|casualty))\b"` — sentiment -0.4, category "trade"
         * `is_rookie_buzz`: `r"\b(?:2026\s+(?:NFL\s+)?Draft (?:prospect|board|class)|surge(?:d|s)?\s+(?:up|on)\s+(?:NFL\s+)?Draft\s+boards?|projected\s+(?:as\s+)?(?:first|top)[\s-](?:overall|round)\s+pick|Heisman\s+(?:contender|finalist|winner))\b"` — sentiment 0.4, category "motivation"

    2. Extend `RuleExtractor.extract` (around line 416) so the `PlayerSignal(...)` constructor passes the 7 new flags from the `events` dict using the SAME idiom as the existing flags (`is_drafted=events.get("is_drafted", False)`, ...). Mirror the comment-block grouping (`# Draft-season events (Plan 72-01)`).

    3. Edit `tests/sentiment/test_rule_extractor_events.py`:
       - Add a new test class `RuleExtractorDraftSeasonFlagsTests(unittest.TestCase)` with the 8 behaviour tests above. Each test instantiates `RuleExtractor()`, calls `extract({"title": "...", "body_text": "..."})`, and asserts the expected flag.
       - Use realistic sentinel strings derived from the W17/W18 fixture content (CONTEXT says high-precision low-recall — false-positive checks are mandatory).

    4. Run targeted tests:
       `python -m pytest tests/sentiment/test_rule_extractor_events.py -v`

    5. Commit two commits per TDD discipline:
       - `test(72-01): add failing tests for 7 new RuleExtractor draft-season patterns`
       - `feat(72-01): add high-precision regex patterns for 7 draft-season event flags`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/sentiment/test_rule_extractor_events.py tests/sentiment/test_schema_contracts.py -v</automated>
  </verify>
  <done>
    All test_rule_extractor_events.py tests pass (existing classes still green + 1 new class with 8 tests). 7 new compiled regex entries exist inside `_compile_patterns()`. `RuleExtractor.extract` constructs PlayerSignal with all 19 flag fields populated from the events dict. Test 8 (precision) confirms no new flags fire on a benign string. Two commits land in git log.
  </done>
</task>

<task type="auto">
  <name>Task 3: Validate full sentiment suite + write SUMMARY for Plan 72-01</name>
  <read_first>
    - tests/sentiment/ (directory listing — confirm full sentiment suite still 165+ tests)
    - .planning/phases/71-llm-primary-extraction/71-01-SUMMARY.md (mirror SUMMARY structure exactly)
  </read_first>
  <files>.planning/phases/72-event-flag-expansion/72-01-SUMMARY.md</files>
  <action>
    1. Run the full sentiment suite to prove zero regressions:
       `source venv/bin/activate && python -m pytest tests/sentiment/ --tb=short -q`
       Confirm the count is `>= 165 + N` where N is the new tests added in Tasks 1+2 (expected ~14 new tests). Capture the exact passing count for the SUMMARY.

    2. Confirm benchmark + cost-projection tests still pass (these depend on prompt SHA — Wave 2 will re-record fixtures, but THIS plan's prompt edits already changed `_SYSTEM_PREFIX`, which means the existing W17/W18 fixtures will FAIL the benchmark + cost-projection tests). This is expected and Wave 2 fixes it. Document this in the SUMMARY as a known pre-Wave-2 state.

       Acceptable failures at this point (will be closed by Plan 72-02):
       - `tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason` (prompt_sha mismatch)
       - `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars` (depends on W18 fixture token counts)
       - `tests/sentiment/test_batched_claude_extractor.py::*` (any test that exercises FakeClaudeClient against a recorded fixture)
       - `tests/sentiment/test_pipeline_claude_primary.py::*` (same)

       All schema contract + rule extractor + Phase 71 unit tests with stubbed Claude clients MUST still pass.

    3. Write `.planning/phases/72-event-flag-expansion/72-01-SUMMARY.md` mirroring `71-01-SUMMARY.md` structure (frontmatter + sections: Performance, Requirements Coverage, Files Changed, Key Decisions, Risks & Watchouts, Threat Flags, Self-Check). Include:
       - `requirements-completed: [EVT-01]` (partial — Wave 2 finalises by re-recording fixtures so Claude actually emits the new flags)
       - Exact passing test count
       - List of fixture-dependent tests that will turn RED until Plan 72-02 completes
       - Note that no Bronze writes occurred (D-06 fail-open contract observed)

    4. Commit:
       `docs(72-01): plan summary — 7 new event flags + subject_type shipped`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/sentiment/test_schema_contracts.py tests/sentiment/test_rule_extractor_events.py -v && test -f .planning/phases/72-event-flag-expansion/72-01-SUMMARY.md</automated>
  </verify>
  <done>
    Full sentiment suite has been run and the summary records the exact pass/fail counts. SUMMARY file exists with the 71-01 structure. Single docs commit lands in git log. No edits to data/bronze/.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Bronze JSON → ClaudeExtractor | Untrusted RSS / Sleeper / Reddit text crosses into the extractor and into prompts sent to Anthropic |
| Bronze JSON → RuleExtractor | Same untrusted text crosses into local regex evaluation |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-72-01-01 | Tampering | PlayerSignal.subject_type | mitigate | __post_init__ validates against frozenset({"player","coach","team","reporter"}); invalid input falls back to "player" with debug log. Prevents downstream routing logic from seeing arbitrary strings. |
| T-72-01-02 | Denial of Service | RuleExtractor regex patterns | mitigate | All new patterns use bounded quantifiers + word-boundary anchors per the existing _compile_patterns invariant (no unbounded `.*` inside alternations). Prevents catastrophic backtracking from adversarial Bronze text (T-61-02-02 lineage). |
| T-72-01-03 | Information Disclosure | _SYSTEM_PREFIX prompt edits | accept | Prompt text is sent to Anthropic per existing contract; no new sensitive data is added. Risk unchanged from Phase 71. |
| T-72-01-04 | Repudiation | extractor field on PlayerSignal | accept | Phase 71 already established `extractor` provenance string; this plan does not change that. New flags inherit the same audit trail. |
</threat_model>

<verification>
- `python -m pytest tests/sentiment/test_schema_contracts.py tests/sentiment/test_rule_extractor_events.py -v` → all pass
- `python -m pytest tests/sentiment/ --tb=no -q` → 179+ pass (165 baseline + ~14 new); fixture-dependent tests (benchmark, cost-projection, batched extractor, pipeline_claude_primary) may fail with `prompt_sha` mismatches — these turn green in Plan 72-02
- `grep -c "is_drafted\|is_rumored_destination\|is_coaching_change\|is_trade_buzz\|is_holdout\|is_cap_cut\|is_rookie_buzz" src/sentiment/processing/extractor.py` returns >= 14 (each name appears at least twice: dataclass field + to_dict events)
- `grep -c "is_drafted\|is_rumored_destination\|is_coaching_change\|is_trade_buzz\|is_holdout\|is_cap_cut\|is_rookie_buzz" src/sentiment/processing/rule_extractor.py` returns >= 14 (regex pattern + PlayerSignal constructor kwarg)
- `python -c "from src.sentiment.processing.extractor import _EVENT_FLAG_KEYS; assert len(_EVENT_FLAG_KEYS) == 19"` exits 0
</verification>

<success_criteria>
- All 7 new event flags are first-class boolean fields on PlayerSignal with default False
- subject_type field accepts exactly 4 values and normalises invalid input to "player"
- _EVENT_FLAG_KEYS cardinality == 19; to_dict() events sub-dict contains all 19 keys
- EXTRACTION_PROMPT + _SYSTEM_PREFIX both enumerate the new flags + subject_type
- RuleExtractor produces signals with the new flags when sentinel text matches
- 14+ new unit tests pass; existing 165 sentiment tests retain their pass status (modulo Wave-2-dependent fixture tests)
- Plan 72-01 SUMMARY documents the partial EVT-01 status (Claude emission proven in Plan 72-02)
</success_criteria>

<output>
After completion, create `.planning/phases/72-event-flag-expansion/72-01-SUMMARY.md` mirroring the structure of `71-01-SUMMARY.md`.
</output>
