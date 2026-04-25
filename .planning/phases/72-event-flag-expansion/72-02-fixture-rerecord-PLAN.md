---
phase: 72
plan: 02
type: execute
wave: 2
depends_on: [72-01]
files_modified:
  - tests/fixtures/claude_responses/offseason_batch_w17.json
  - tests/fixtures/claude_responses/offseason_batch_w18.json
  - tests/fixtures/claude_responses/README.md
  - tests/sentiment/test_extractor_benchmark.py
  - src/sentiment/processing/extractor.py
autonomous: true
requirements:
  - EVT-01
tags: [fixtures, prompt-sha, claude-recording, deterministic-tests]
must_haves:
  truths:
    - "offseason_batch_w17.json + offseason_batch_w18.json carry NEW prompt_sha values that match the post-72-01 _SYSTEM_PREFIX byte-for-byte (computed by _build_batched_prompt_for_sha against roster_provider=lambda: [])"
    - "Each fixture's response_text JSON array contains at least 5 items where the events sub-dict carries one of the 7 new flags AND at least 5 items carry an explicit subject_type field (player|coach|team|reporter), all emitted by Claude (no hand-augmentation)"
    - "FakeClaudeClient.from_fixture_dir(...) loads both fixtures without warnings"
    - "tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason re-passes with ratio >= 5.0× (the original 5.57× is the floor; new flags should add not remove signals)"
    - "tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars passes (W18 warm-cache projection still < $5/week) — measured BEFORE green/regression decision and remediated per locked order if breached"
    - "tests/sentiment/test_pipeline_claude_primary.py + test_batched_claude_extractor.py all green again"
    - "tests/fixtures/claude_responses/README.md documents the 72-02 re-record procedure + new flag/subject_type contract + the no-hand-augmentation rule"
  artifacts:
    - path: "tests/fixtures/claude_responses/offseason_batch_w17.json"
      provides: "cold-cache W17 fixture re-recorded against post-72-01 prompt"
      contains: "prompt_sha"
      contains_2: "subject_type"
      contains_3: "is_drafted"
    - path: "tests/fixtures/claude_responses/offseason_batch_w18.json"
      provides: "warm-cache W18 fixture re-recorded against post-72-01 prompt"
      contains: "prompt_sha"
      contains_2: "subject_type"
    - path: "tests/fixtures/claude_responses/README.md"
      provides: "updated re-record protocol covering 7 new flags + subject_type"
  key_links:
    - from: "tests/fixtures/claude_responses/offseason_batch_w17.json::prompt_sha"
      to: "src.sentiment.processing.extractor._build_batched_prompt_for_sha"
      via: "computed by helper module (record_fixtures.py) — both fixtures must use roster_provider=lambda: []"
      pattern: "\"prompt_sha\":\\s*\"[a-f0-9]{64}\""
    - from: "tests/sentiment/test_extractor_benchmark.py"
      to: "FakeClaudeClient + new fixtures"
      via: "extract_batch_primary returns >= 5x rule signal count on identical 30-doc Bronze fixture"
      pattern: "ratio.*=.*5\\."
---

<objective>
Re-record W17 + W18 Claude response fixtures against the post-72-01 prompt SHA so the deterministic test suite (LLM-03 benchmark + LLM-04 cost projection + claude_primary pipeline tests + batched extractor tests) is green again, AND so the fixture content actually exercises the 7 new event flags + the new subject_type field — emitted by Claude itself, never post-processed.

Purpose: Plan 72-01 changed `_SYSTEM_PREFIX` (and therefore the prompt SHA), which silently breaks every fixture-dependent test. This plan closes that gap by (a) strengthening the prompt so `subject_type` is REQUIRED in every Claude response item, (b) re-running the recording protocol from Phase 71 (`tests/fixtures/claude_responses/README.md`) with the new prompt + new flag instructions, and (c) honouring the Phase 71 determinism contract: the recording is faithful to whatever Claude returns, never post-augmented in code. If Claude omits subject_type after prompt strengthening, the recording fails and the operator strengthens the prompt further — Python never patches Claude's output.

Output: Two re-recorded fixture JSON files + an updated README documenting the procedure + the strengthened `_SYSTEM_PREFIX`. Benchmark ratio >= 5.0× preserved, cost projection < $5/week preserved (with locked remediation order if breached).
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/72-event-flag-expansion/72-CONTEXT.md
@.planning/phases/72-event-flag-expansion/72-01-SUMMARY.md
@.planning/phases/71-llm-primary-extraction/71-02-SUMMARY.md
@.planning/phases/71-llm-primary-extraction/71-03-SUMMARY.md
@.planning/phases/71-llm-primary-extraction/71-BENCHMARK.md
@tests/fixtures/claude_responses/README.md
@tests/fixtures/bronze_sentiment/offseason_w17_w18.json

<interfaces>
<!-- LOCKED contracts from Plan 72-01 + Phase 71 fixture infrastructure. -->

From src/sentiment/processing/extractor.py (post-72-01 + this plan's prompt strengthening):

```python
def _build_batched_prompt_for_sha(
    static_prefix: str,           # _SYSTEM_PREFIX (post-72-01 + 72-02 strengthening — NEW SHA)
    roster_block: str,            # "" when roster_provider=lambda: []
    batch_docs: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (system, messages) — pass to fakes.prompt_sha(system, messages, model)
    to compute the SHA the fixture must store."""

_SYSTEM_PREFIX = """...is_ruled_out, is_inactive, ..., is_weather_risk,
is_drafted, is_rumored_destination, is_coaching_change, is_trade_buzz,
is_holdout, is_cap_cut, is_rookie_buzz.
REQUIRED subject_type field (every item MUST include this): "player" | "coach" | "team" | "reporter"."""
```

From tests/sentiment/fakes.py (Phase 71):

```python
def prompt_sha(system: Any, messages: Any, model: str) -> str:
    """Returns 64-char hex digest of canonical {model, system, messages} JSON."""

class FakeClaudeClient:
    @classmethod
    def from_fixture_dir(cls, fixture_dir: Path, strict: bool = True) -> "FakeClaudeClient":
        """Walks *.json under fixture_dir, registers each by prompt_sha key."""
```

From tests/fixtures/bronze_sentiment/offseason_w17_w18.json (Phase 71):
- 30 Bronze docs total: 15 in W17 batch + 15 in W18 batch
- Each doc has: external_id, title, body_text, source, season=2025, week=17|18

From tests/fixtures/claude_responses/offseason_batch_w17.json (current — STALE after 72-01):
- prompt_sha: "f59fdd9b..." (PRE-72-01 — must be replaced)
- input_tokens=1420, output_tokens=4350, cache_read=0, cache_creation=1180 (cold-cache)
- response_text: JSON array of ~78 signals, mix of player + null-player items, NO subject_type, NO new flags

From tests/fixtures/claude_responses/offseason_batch_w18.json (current — STALE):
- prompt_sha: "1c0e3e1a..." (PRE-72-01)
- input_tokens=1310, output_tokens=4200, cache_read=1180, cache_creation=0 (warm-cache — gate basis)

From tests/sentiment/test_extractor_benchmark.py:
- Asserts `claude_count / rule_count >= 5.0` on the 30-doc fixture
- Both extractors run against the same Bronze docs; benchmark passes when Claude finds 5x more signals

From tests/sentiment/test_cost_projection.py:
- Computes weekly cost from W18 token counts × BATCH_SIZE × 80 docs/day × 7 days
- Asserts weekly_cost < 5.0
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Strengthen _SYSTEM_PREFIX (require subject_type) + build the fixture-recording helper script + record W17 cold-cache fixture</name>
  <read_first>
    - tests/fixtures/claude_responses/README.md (full file — Phase 71 recording protocol)
    - tests/fixtures/bronze_sentiment/offseason_w17_w18.json (full file — 30 doc fixture for re-record input)
    - tests/sentiment/fakes.py lines 56-80 (prompt_sha helper) and 337-400 (from_fixture_dir loader)
    - src/sentiment/processing/extractor.py lines 313-391 (_format_batch_user_message + _build_batched_prompt_for_sha) AND the `_SYSTEM_PREFIX` block from Plan 72-01 (must locate and edit the subject_type clause)
  </read_first>
  <files>scripts/record_claude_fixture.py, tests/fixtures/claude_responses/offseason_batch_w17.json, src/sentiment/processing/extractor.py</files>
  <action>
    Per CONTEXT "VCR fixtures re-recorded so signals include the new flags where applicable. The fixture prompt_sha updates because the prompt text changed." (locked) AND the Phase 71 determinism contract (no post-processing of recordings):

    1. Strengthen `_SYSTEM_PREFIX` in `src/sentiment/processing/extractor.py` so `subject_type` is REQUIRED rather than optional. Locate the line added in Plan 72-01 that reads (approximately):
       `Optional subject_type field: "player" | "coach" | "team" | "reporter" (default "player").`
       Replace with EXACTLY:
       `REQUIRED subject_type field (every item MUST include this): "player" | "coach" | "team" | "reporter".`
       Also update `EXTRACTION_PROMPT` (the legacy single-doc prompt) so the same enforcement applies: change "Optional subject_type..." to "REQUIRED subject_type..." in the same enumeration block.
       This is a deliberate prompt change — it shifts the prompt SHA again (one hop beyond Plan 72-01's edit) and is the load-bearing reason both W17 + W18 fixtures must be re-recorded together in steps 2-4 below.

       NOTE: This edit changes `_SYSTEM_PREFIX` in `extractor.py`, which Plan 72-01 also touches. Both edits land in the same file; the diff for this task is only the "Optional → REQUIRED" wording change in the subject_type clause. Schema contract tests in test_schema_contracts.py from Plan 72-01 still pass because they assert the presence of subject_type in the prompt text, not its optionality wording (verify by running the suite first).

    2. Create new helper script `scripts/record_claude_fixture.py` (CLI). Read the full Phase 71 README first to mirror the protocol exactly. The helper must:
       - Accept `--week {17|18}` and `--out PATH` args
       - Load the 30-doc Bronze fixture from `tests/fixtures/bronze_sentiment/offseason_w17_w18.json`, filter to the requested week (15 docs each)
       - Construct a real `anthropic.Anthropic` client using `os.environ["ANTHROPIC_API_KEY"]` (raise KeyError with helpful message if missing)
       - Build a `ClaudeExtractor(client=real_anthropic, roster_provider=lambda: [], cost_log=None, batch_size=15)` so the entire week is one batch (matches existing fixture shape)
       - Call `extractor.extract_batch_primary(docs, season=2025, week={17|18})`
       - Capture the raw response from a wrapper around `_call_claude_batch` (intercept by overriding `messages.create` on the client to log the response object before returning) — OR write a small `_record_one_call` helper inside the script that calls `_build_batched_prompt_for_sha`, then `client.messages.create(...)`, then captures the response text + usage tokens
       - Compute `prompt_sha` via `from tests.sentiment.fakes import prompt_sha; sha = prompt_sha(system, messages, _CLAUDE_MODEL)` (the SAME helper FakeClaudeClient uses)
       - Write the fixture JSON file with the schema: `{"_comment": "...", "prompt_sha", "model", "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "response_text"}`
       - **Recording faithfulness rule (LOCKED, Phase 71 contract):** the helper writes Claude's raw response_text to disk verbatim. NO Python post-processing: no subject_type backfill, no flag synthesis, no item editing. If Claude's output fails the verification gate (step 4 below), the recording is rejected and the operator strengthens the prompt further (returning to step 1).
       - For W17: cold-cache (run BEFORE W18 to populate Anthropic's server-side cache)
       - For W18: warm-cache (run AFTER W17 within the cache window)

    3. AFTER ANTHROPIC_API_KEY is set in the local env, run the helper to record W17:
       `source venv/bin/activate && export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) && python scripts/record_claude_fixture.py --week 17 --out tests/fixtures/claude_responses/offseason_batch_w17.json`

    4. Inspect the new W17 fixture and confirm (these are HARD gates — failure means re-record, not patch):
       - `prompt_sha` is a 64-char hex string DIFFERENT from the previous `f59fdd9b...`
       - `cache_read_input_tokens == 0` and `cache_creation_input_tokens > 0` (cold-cache)
       - `response_text` is a JSON-encoded array
       - Decoded array contains: at least 1 item with `subject_type: "coach"`, at least 1 with `subject_type: "team"`, at least 1 with `subject_type: "reporter"`, and at least 5 items with one of the 7 new flags (is_drafted, is_rumored_destination, is_coaching_change, is_trade_buzz, is_holdout, is_cap_cut, is_rookie_buzz) set to True inside `events`
       - **EVERY item in the array has a subject_type field** (per the strengthened prompt). If even one item omits it, the recording fails — return to step 1, strengthen the prompt further (e.g., add a worked example block to `_SYSTEM_PREFIX`), and re-record. Do NOT post-process the file.

       If the count of new-flag items < 5: return to step 1 and adjust the prompt enumeration to make the new flags more salient (e.g., add brief one-liner definitions or a worked example). Do NOT hand-edit the fixture.

    5. Commit (single commit because the prompt edit + fixture are coupled):
       `test(72-02): strengthen subject_type prompt + re-record W17 cold-cache fixture`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -c "
import json
from pathlib import Path
fix = json.loads(Path('tests/fixtures/claude_responses/offseason_batch_w17.json').read_text())
assert len(fix['prompt_sha']) == 64, 'sha must be 64 hex chars'
assert fix['cache_read_input_tokens'] == 0, 'W17 must be cold-cache'
assert fix['cache_creation_input_tokens'] > 0, 'W17 must create cache'
items = json.loads(fix['response_text'])
new_flags = ('is_drafted','is_rumored_destination','is_coaching_change','is_trade_buzz','is_holdout','is_cap_cut','is_rookie_buzz')
new_flag_count = sum(1 for it in items if isinstance(it, dict) and any((it.get('events') or {}).get(f) for f in new_flags))
assert new_flag_count >= 5, f'need >= 5 new-flag items, got {new_flag_count}'
subject_types = {it.get('subject_type') for it in items if isinstance(it, dict)}
assert {'coach', 'team', 'reporter'}.issubset(subject_types), f'missing subject_types in {subject_types}'
missing_st = [it for it in items if isinstance(it, dict) and not it.get('subject_type')]
assert not missing_st, f'every item must have subject_type per strengthened prompt; missing on {len(missing_st)} items'
print(f'OK: sha={fix[\"prompt_sha\"][:16]}... new_flag_items={new_flag_count} subject_types={subject_types}')
"</automated>
  </verify>
  <done>
    `_SYSTEM_PREFIX` strengthened so subject_type is REQUIRED. `scripts/record_claude_fixture.py` exists and is runnable; recording is faithful (no post-processing). New `offseason_batch_w17.json` carries the new prompt_sha, cold-cache token counts, >= 5 items with new flags set, every item has a non-empty subject_type, and at least one each of coach/team/reporter values. Single test() commit lands.
  </done>
</task>

<task type="auto">
  <name>Task 2: Record W18 warm-cache fixture + measure cost projection (locked remediation order if breached) + update README + green the fixture-dependent test suite</name>
  <read_first>
    - tests/fixtures/claude_responses/offseason_batch_w18.json (current — confirm warm-cache token shape: cache_read > 0, cache_creation == 0)
    - tests/fixtures/claude_responses/README.md (full)
    - tests/sentiment/test_extractor_benchmark.py (full — confirm where the >= 5x assertion lives)
    - tests/sentiment/test_cost_projection.py (full — confirm where W18 token counts are read AND the $5/week threshold)
    - src/sentiment/processing/extractor.py (locate `_BATCH_DOC_BODY_TRUNCATE` constant and `BATCH_SIZE` for the locked remediation order)
  </read_first>
  <files>tests/fixtures/claude_responses/offseason_batch_w18.json, tests/fixtures/claude_responses/README.md, tests/sentiment/test_extractor_benchmark.py</files>
  <action>
    1. Run the helper script for W18 immediately after W17 (within the Anthropic cache window so cache_read > 0):
       `python scripts/record_claude_fixture.py --week 18 --out tests/fixtures/claude_responses/offseason_batch_w18.json`

       Expect: `cache_read_input_tokens > 0` (warm — cache primed by W17) and `cache_creation_input_tokens == 0`. If timing slipped and cache went cold, re-record W17 then W18 back-to-back. Document the timing window in the README.

    2. Apply the same hard gates from Task 1 step 4 to the W18 fixture: every item has subject_type, >= 5 carry one of the 7 new flags, at least one each of coach/team/reporter values. Recording is faithful — no post-processing. Failure → re-record with stronger prompt, never patch.

    3. **Measure cost projection BEFORE the green/regression decision** (this gate runs first because it determines whether remediation is needed):
       Run `python -m pytest tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars -v` and ALSO compute the raw projected weekly cost via:
       `python -c "
import json
from pathlib import Path
fix = json.loads(Path('tests/fixtures/claude_responses/offseason_batch_w18.json').read_text())
# Mirror test_cost_projection.py's formula — read the test for canonical cost-per-token + traffic assumptions.
# Print: input_tokens={fix['input_tokens']} output_tokens={fix['output_tokens']} cache_read={fix['cache_read_input_tokens']} → weekly_cost=$X.XX
"`
       Record the exact projected weekly cost (e.g., `$3.42`) for the SUMMARY.

       **Decision branches:**

       a) **If new weekly cost ≤ $5:** green path. Document the number in step 7 SUMMARY. Proceed to step 4.

       b) **If new weekly cost > $5:** REQUIRED remediation order — try each in sequence, re-recording W17+W18 and re-measuring after each step. Do NOT proceed past a failing step.
          - **(a)** Lower `_BATCH_DOC_BODY_TRUNCATE` in `src/sentiment/processing/extractor.py` from `2000` → `1500`. Re-record both fixtures, re-measure cost. If ≤ $5, stop and proceed to step 4 with documentation in SUMMARY.
          - **(b)** Compress `_SYSTEM_PREFIX` flag definitions to one-liner each (collapse multi-line definitions if any exist; keep the REQUIRED subject_type clause intact). Re-record both fixtures, re-measure cost. If ≤ $5, stop and proceed.
          - **(c)** Increase `BATCH_SIZE` in `src/sentiment/processing/extractor.py` from `8` → `10` to amortise batch overhead. Re-record both fixtures (note: the W17/W18 fixtures stay at batch_size=15 internally for the recording — the BATCH_SIZE constant only affects production traffic projection). Re-measure cost. If ≤ $5, stop and proceed.
          - **If all 3 remediations fail:** STOP. Do NOT accept a regression. Escalate to the operator as a CONTEXT-blocking decision: print a clear summary of the cost overage + the 3 attempted remediations + their resulting projections, and pause for the operator to decide whether to (i) accept a higher cost gate by amending CONTEXT D-04, (ii) defer some of the 7 new flags, or (iii) split this work into a follow-up phase. Do NOT proceed to step 4.

    4. Run the benchmark gate:
       `python -m pytest tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason -v`
       PASS with ratio >= 5.0×. If the new flag instructions changed Claude's response shape so the ratio drops below 5.0×, document which items dropped and whether item count or shape is responsible. If item count dropped and the prompt strengthening is the cause, re-tune the prompt to preserve coverage; do NOT relax the gate.

    5. Update `tests/fixtures/claude_responses/README.md` (rewrite the "Recording protocol" section):
       - Document Plan 72-02 re-record date + reason ("post-Plan 72-01 prompt extension + 72-02 subject_type strengthening")
       - Document the new prompt_sha values (W17 + W18) replacing the placeholder/old values
       - Document the determinism contract: "roster_provider=lambda: [] is REQUIRED for SHA reproducibility — never record with a real roster"
       - **Document the no-hand-augmentation rule (LOCKED):** "Recordings are faithful. The Python helper writes Claude's raw response_text verbatim. There is no post-processing of subject_type, no synthesis of new flags, no item editing. If Claude's output fails the verification gates, strengthen the prompt and re-record — never patch the file."
       - Re-run instructions: `python scripts/record_claude_fixture.py --week 17 --out ...` then `--week 18 --out ...` within ~5 min so the cache stays warm
       - Add a section "When to re-record": every time `_SYSTEM_PREFIX` changes in `extractor.py`
       - Add a section "Cost remediation order (Plan 72-02)" documenting the locked sequence: (1) `_BATCH_DOC_BODY_TRUNCATE` 2000→1500, (2) `_SYSTEM_PREFIX` one-liner compression, (3) `BATCH_SIZE` 8→10. Note that exhausting all three escalates as a CONTEXT-blocking decision — never silently accept a >$5/week regression.

    6. Run the full sentiment suite to prove green:
       `python -m pytest tests/sentiment/ --tb=short -q`

       Expected: ALL 165 baseline tests + ~14 from Plan 72-01 + 0 fixture-related failures = >= 179 passed. Specifically validate:
       - `tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason` PASS with ratio >= 5.0×
       - `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars` PASS with W18 weekly cost < $5
       - `tests/sentiment/test_pipeline_claude_primary.py::*` PASS
       - `tests/sentiment/test_batched_claude_extractor.py::*` PASS

    7. Commit two commits:
       - `test(72-02): re-record W18 warm-cache fixture + update README (no-hand-augmentation rule)`
       - `feat(72-02): close fixture-dependent tests; benchmark ratio + cost gate green`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/sentiment/test_extractor_benchmark.py tests/sentiment/test_cost_projection.py tests/sentiment/test_pipeline_claude_primary.py tests/sentiment/test_batched_claude_extractor.py -v && python -m pytest tests/sentiment/ --tb=no -q | tail -5</automated>
  </verify>
  <done>
    Both fixtures re-recorded faithfully and committed. README documents the 72-02 procedure including the no-hand-augmentation rule and the locked cost-remediation order. Cost projection measured BEFORE the green decision; weekly cost ≤ $5 (or remediation applied per locked order, or escalated). Full sentiment suite is green (>= 179 passed). Benchmark ratio >= 5.0×. Two commits land in git log.
  </done>
</task>

<task type="auto">
  <name>Task 3: Write SUMMARY for Plan 72-02</name>
  <read_first>
    - .planning/phases/71-llm-primary-extraction/71-02-SUMMARY.md (mirror structure)
    - tests/fixtures/claude_responses/offseason_batch_w17.json (record final SHA + token counts for SUMMARY)
    - tests/fixtures/claude_responses/offseason_batch_w18.json (same)
  </read_first>
  <files>.planning/phases/72-event-flag-expansion/72-02-SUMMARY.md</files>
  <action>
    Write `.planning/phases/72-event-flag-expansion/72-02-SUMMARY.md` mirroring `71-02-SUMMARY.md` structure. Include:
    - Frontmatter with `requirements-completed: [EVT-01]` (now fully closed — Claude emission proven)
    - Final prompt_sha values for W17 + W18 (full 64 hex)
    - Cost projection numbers: W17 cold-cache weekly $X.XXXX, W18 warm-cache weekly $X.XXXX (must be < $5)
    - **Cost-remediation status:** which remediation step (if any) was applied per the locked order in the action — or "no remediation needed (cost ≤ $5 on first measurement)"
    - Benchmark ratio: rule=N claude=M ratio=K.KKx (must be >= 5.0×)
    - Total sentiment test pass count (>= 179)
    - Note that no edits to `data/bronze/` occurred
    - Note that recordings are faithful (no Python post-processing of Claude output)
    - Risks & Watchouts section: cold-cache cost spike, fixture drift if `_SYSTEM_PREFIX` is re-edited, prompt strengthening may need iteration if Claude omits subject_type

    Commit:
    `docs(72-02): plan summary — fixtures re-recorded, EVT-01 fully closed`
  </action>
  <verify>
    <automated>test -f .planning/phases/72-event-flag-expansion/72-02-SUMMARY.md && grep -E "ratio.*5\.[0-9]+x|prompt_sha.*[a-f0-9]{16}" .planning/phases/72-event-flag-expansion/72-02-SUMMARY.md</automated>
  </verify>
  <done>
    SUMMARY file exists with frontmatter, benchmark ratio, cost projections, remediation status, and final prompt_shas. Single docs commit lands. EVT-01 marked fully complete in REQUIREMENTS.md (deferred to Plan 72-05 traceability update).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Local recording script → Anthropic API | Live API call with API key — only happens during fixture recording, never in CI |
| Recorded fixture JSON → CI test runner | Untrusted-looking JSON loaded into FakeClaudeClient; SHA-keyed lookup means a malicious fixture cannot affect a different test |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-72-02-01 | Information Disclosure | scripts/record_claude_fixture.py | mitigate | Reads ANTHROPIC_API_KEY from env only; never logs it; never writes to a file beyond the fixture JSON. Pre-commit hook (existing) blocks any accidental key leak. |
| T-72-02-02 | Tampering | Fixture JSON files | mitigate | FakeClaudeClient.from_fixture_dir uses SHA-keyed registration; a fixture with a wrong prompt_sha simply won't be matched (test fails with diagnostic). No silent acceptance. Recordings are faithful (no post-processing) so the file is reproducible from a re-run against the same prompt + Bronze. |
| T-72-02-03 | Denial of Service | Re-recorded fixture inflates cost | mitigate | Plan 71-05 CI cost gate (`test_weekly_cost_projection_under_5_dollars`) is the load-bearing check — if W18 token counts push weekly cost over $5, the locked remediation order in Task 2 step 3 kicks in; if all three remediations fail the operator is escalated to. No silent regression accepted. |
| T-72-02-04 | Repudiation | Recording faithfulness | mitigate | The no-hand-augmentation rule is documented in README + enforced by the helper script (which never post-processes). Any fixture in git can be reproduced from the same _SYSTEM_PREFIX + Bronze input, making recordings auditable. |
</threat_model>

<verification>
- `python -m pytest tests/sentiment/ --tb=no -q | tail -5` → 179+ passed, 0 failed
- `python -m pytest tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason -v` → PASS with ratio printed >= 5.0
- `python -m pytest tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars -v` → PASS
- `jq -r '.prompt_sha' tests/fixtures/claude_responses/offseason_batch_w17.json | wc -c` → 65 (64 hex + newline)
- `jq -r '.prompt_sha' tests/fixtures/claude_responses/offseason_batch_w18.json | wc -c` → 65
- `python -c "import json; from pathlib import Path; w17 = json.loads(Path('tests/fixtures/claude_responses/offseason_batch_w17.json').read_text()); items = json.loads(w17['response_text']); print(set(it.get('subject_type') for it in items if isinstance(it, dict)))"` → set contains 'player', 'coach', 'team', 'reporter' AND no None values
- `grep -c "REQUIRED subject_type" src/sentiment/processing/extractor.py` returns >= 1 (prompt strengthened)
</verification>

<success_criteria>
- `_SYSTEM_PREFIX` and `EXTRACTION_PROMPT` enforce subject_type as REQUIRED (not optional)
- New W17 + W18 fixtures land with NEW prompt_sha values matching post-72-02 _SYSTEM_PREFIX
- W17 cold-cache (cache_creation > 0, cache_read == 0); W18 warm-cache (cache_read > 0, cache_creation == 0)
- Each fixture's response_text contains >= 5 items with new flags set + all 4 subject_type values represented + EVERY item has a non-empty subject_type — all emitted by Claude, no post-processing
- Full sentiment suite green: 179+ passed, 0 failed
- LLM-03 benchmark ratio >= 5.0× (preserves Phase 71's 5.57× floor)
- LLM-04 cost projection < $5/week (measured BEFORE green decision; locked remediation order applied if breached; escalation if all 3 remediations fail)
- README documents the 72-02 re-record protocol + no-hand-augmentation rule + cost-remediation order
- SUMMARY file written, including remediation status
</success_criteria>

<output>
After completion, create `.planning/phases/72-event-flag-expansion/72-02-SUMMARY.md` mirroring `71-02-SUMMARY.md`.
</output>
</content>
</invoke>