---
phase: 71-llm-primary-extraction
plan: 03
type: execute
wave: 3
depends_on:
  - 71-01
  - 71-02
files_modified:
  - src/sentiment/processing/extractor.py
  - src/sentiment/processing/cost_log.py
  - tests/sentiment/test_batched_claude_extractor.py
  - tests/sentiment/test_cost_log.py
autonomous: true
requirements:
  - LLM-01
  - LLM-04
  - LLM-05
must_haves:
  truths:
    - "ClaudeExtractor.extract_batch_primary(docs) produces PlayerSignal items from raw Bronze docs using batched Claude calls (BATCH_SIZE=8) — not enrichment of existing signals"
    - "The batched call uses Anthropic prompt caching: a static system prefix + the active-roster player list are cached via `cache_control: {'type': 'ephemeral'}` markers"
    - "Per-doc soft fallback: when Claude raises or returns malformed JSON, extract_batch_primary raises an exception captured upstream by the pipeline (Plan 71-04); within a batch, items that fail to parse are logged and dropped"
    - "Non-player items (`player_name: null`) are captured separately and surfaced via return value — they do NOT fabricate a PlayerSignal with empty player_name"
    - "Per-call cost is computed as tokens_in * in_rate + tokens_out * out_rate using the Haiku 4.5 rate table and written to `data/ops/llm_costs/season=YYYY/week=WW/llm_costs_TIMESTAMP.parquet`"
    - "The extractor accepts a `client: ClaudeClient` via constructor DI so tests inject FakeClaudeClient without monkeypatching"
  artifacts:
    - path: "src/sentiment/processing/extractor.py"
      provides: "ClaudeExtractor.extract_batch_primary, _build_batched_prompt, _parse_batch_response, plus constructor DI for client/roster_provider/cost_sink"
      contains: "def extract_batch_primary"
    - path: "src/sentiment/processing/cost_log.py"
      provides: "CostLog Parquet sink; CostRecord dataclass; HAIKU_4_5_RATES constant; write_cost_record()"
      exports: ["CostRecord", "CostLog", "HAIKU_4_5_RATES", "compute_cost_usd"]
    - path: "tests/sentiment/test_batched_claude_extractor.py"
      provides: "Tests for batching, prompt caching markers, SHA-keyed replay against W17/W18 fixtures, non-player capture, malformed JSON fallback"
    - path: "tests/sentiment/test_cost_log.py"
      provides: "Tests for cost math, Parquet schema, directory layout"
  key_links:
    - from: "ClaudeExtractor.__init__"
      to: "ClaudeClient Protocol (from Plan 71-01)"
      via: "constructor DI parameter `client: Optional[ClaudeClient] = None`"
      pattern: "client: Optional\\[.*ClaudeClient"
    - from: "ClaudeExtractor.extract_batch_primary"
      to: "data/ops/llm_costs/season=YYYY/week=WW/"
      via: "CostLog.write_record(CostRecord(...))"
      pattern: "cost_log\\.write_record"
    - from: "tests/sentiment/test_batched_claude_extractor.py"
      to: "tests/fixtures/claude_responses/offseason_batch_w17.json"
      via: "FakeClaudeClient.from_fixture_dir"
      pattern: "from_fixture_dir"
---

<objective>
Promote `ClaudeExtractor` from legacy single-doc helper to a first-class batched primary extractor: accepts a batch of Bronze docs, emits `PlayerSignal` items (with the extended schema from Plan 71-01), supports Anthropic prompt caching for the static system prefix and active-roster player list, tracks cost to a Parquet log, and captures non-player items separately. Plan 71-04 will wire this into `SentimentPipeline`.

Purpose: LLM-01 requires `ClaudeExtractor` as a peer to `RuleExtractor` producing signals from raw Bronze. LLM-04 requires cost management via batch + cache at <$5/week at 80 docs/day. LLM-05 requires deterministic tests — hence DI and SHA-keyed replay.
Output: Promoted extractor module, new cost_log module, two dedicated test files.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/71-llm-primary-extraction/71-CONTEXT.md
@.planning/phases/71-llm-primary-extraction/71-01-schema-and-contracts-PLAN.md
@.planning/phases/71-llm-primary-extraction/71-02-fixtures-and-fake-client-PLAN.md
@src/sentiment/processing/extractor.py
@src/sentiment/enrichment/llm_enrichment.py

<interfaces>
<!-- New public API added by this plan. Consumed by Plan 71-04. -->

```python
# In src/sentiment/processing/extractor.py — new methods/constructor on existing class

class ClaudeExtractor:
    def __init__(
        self,
        model: str = _CLAUDE_MODEL,
        client: Optional[ClaudeClient] = None,              # NEW: DI seam
        roster_provider: Optional[Callable[[], List[str]]] = None,  # NEW: returns active player names
        cost_log: Optional["CostLog"] = None,               # NEW: cost sink (None = no logging)
        batch_size: int = BATCH_SIZE,                        # NEW: overridable
    ) -> None: ...

    def extract_batch_primary(
        self,
        docs: List[Dict[str, Any]],
        season: int,
        week: int,
    ) -> Tuple[Dict[str, List[PlayerSignal]], List[Dict[str, Any]]]:
        """Primary-path batched extraction.

        Returns:
            (by_doc_id, non_player_items)
            by_doc_id: external_id -> list of PlayerSignal (signals with
                non-null player_name; extractor="claude_primary")
            non_player_items: list of dicts {external_id, doc_id, team_abbr,
                summary, sentiment, confidence, category, raw_excerpt}
        """

# In src/sentiment/processing/cost_log.py — new module

from dataclasses import dataclass

HAIKU_4_5_RATES = {
    # USD per 1M tokens (Claude Haiku 4.5 pricing as of 2026-04)
    "input": 1.00,
    "output": 5.00,
    "cache_read": 0.10,          # cached input tokens are ~10% of normal input
    "cache_creation": 1.25,      # cache-write is ~1.25x normal input
}

@dataclass
class CostRecord:
    call_id: str
    doc_count: int
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    cost_usd: float
    ts: str             # ISO8601 UTC
    season: int
    week: int

def compute_cost_usd(
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> float: ...

class CostLog:
    def __init__(self, base_dir: Optional[Path] = None) -> None: ...
    def write_record(self, record: CostRecord) -> Path: ...
    def running_total_usd(self, season: int, week: int) -> float: ...
```

Prompt caching shape (per CONTEXT.md "specifics"):

```python
# The Messages API call built by _call_claude_batch
client.messages.create(
    model=self.model,
    max_tokens=_MAX_TOKENS_BATCH,  # NEW: 4096 for batched extraction
    system=[
        {
            "type": "text",
            "text": _SYSTEM_PREFIX,                  # static; cached
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"ACTIVE PLAYERS:\n{roster_block}",  # cached weekly
            "cache_control": {"type": "ephemeral"},
        },
    ],
    messages=[{
        "role": "user",
        "content": batched_user_prompt,   # per-batch; NOT cached
    }],
)
```

Cost log path (matches CONTEXT.md "data/ops/llm_costs/season=YYYY/week=WW/llm_costs_TIMESTAMP.parquet"):

```
data/ops/llm_costs/season=2025/week=17/llm_costs_20260424_123456.parquet
```

**Fixture SHA determinism contract (from Plan 71-02):** For tests/benchmarks that exercise SHA-keyed fixture replay, the extractor MUST be instantiated with `roster_provider=lambda: []` (empty list). The recorded fixture `prompt_sha` values were computed with an empty roster; dynamic roster contents would break SHA matching across machines/dates. Production instantiation uses the real roster provider and would produce different SHAs (acceptable — prod doesn't hit fixtures).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build CostLog Parquet sink with cost math</name>
  <files>src/sentiment/processing/cost_log.py, tests/sentiment/test_cost_log.py</files>
  <read_first>
    - src/sentiment/processing/extractor.py (existing module; understand existing module-level path constants pattern)
    - src/sentiment/enrichment/llm_enrichment.py (existing _PROJECT_ROOT pattern for tmp-tree-friendly paths)
    - .claude/rules/nfl-data-conventions.md (S3 key pattern + Parquet conventions)
  </read_first>
  <behavior>
    - `compute_cost_usd(input_tokens=1_000_000, output_tokens=0) == 1.00`
    - `compute_cost_usd(input_tokens=0, output_tokens=1_000_000) == 5.00`
    - `compute_cost_usd(input_tokens=0, output_tokens=0, cache_read_input_tokens=1_000_000) == 0.10`
    - `compute_cost_usd(input_tokens=0, output_tokens=0, cache_creation_input_tokens=1_000_000) == 1.25`
    - Mixed: `compute_cost_usd(1000, 500, 500, 100)` computes the additive sum correctly to ~6 decimal precision
    - `CostLog().write_record(CostRecord(...))` writes a Parquet file under `data/ops/llm_costs/season=YYYY/week=WW/llm_costs_YYYYMMDD_HHMMSS.parquet` with the 10 fields from CostRecord
    - `CostLog.running_total_usd(season, week)` reads all parquet files for that partition, sums `cost_usd`, returns float
    - `CostLog.running_total_usd(season, week)` returns `0.0` when no files exist (no exception)
    - `CostLog(base_dir=tmp_path)` respects constructor override for tests
  </behavior>
  <action>
    Create `src/sentiment/processing/cost_log.py`:
    1. Module docstring explaining LLM-04 cost tracking.
    2. Import: `json`, `uuid`, `pandas as pd`, `pyarrow as pa`, `pyarrow.parquet as pq` (prefer pandas.to_parquet which calls pyarrow under the hood — match project convention; check the daily pipeline for precedent).
    3. `_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent` (matches llm_enrichment.py pattern).
    4. `_DEFAULT_BASE_DIR = _PROJECT_ROOT / "data" / "ops" / "llm_costs"`.
    5. Export `HAIKU_4_5_RATES` dict, `CostRecord` dataclass, `compute_cost_usd()` function, `CostLog` class per `<interfaces>` block.
    6. `compute_cost_usd` math: `(input_tokens/1e6)*HAIKU_4_5_RATES["input"] + (output_tokens/1e6)*HAIKU_4_5_RATES["output"] + (cache_read_input_tokens/1e6)*HAIKU_4_5_RATES["cache_read"] + (cache_creation_input_tokens/1e6)*HAIKU_4_5_RATES["cache_creation"]`. Return `round(value, 6)`.
    7. `CostLog.write_record`: timestamp is `datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")`. Path: `{base}/season={season}/week={week:02d}/llm_costs_{ts}.parquet`. Create parent dir. Build a 1-row DataFrame from the CostRecord and write via `df.to_parquet(path, index=False)`. Return the path.
    8. `CostLog.running_total_usd`: `glob` the week dir for `llm_costs_*.parquet`, read each with `pd.read_parquet`, concat, sum `cost_usd`. Return `0.0` on empty/missing dir (no raise).
    9. Add a `fail_open_write` pattern — if PyArrow not installed, log a warning and return `None` without raising (the daily cron must never hard-fail per CONTEXT.md D-06).
    Create `tests/sentiment/test_cost_log.py`:
    - 8 tests covering the behaviour bullets; use `tmp_path` fixture and `CostLog(base_dir=tmp_path)` everywhere.
    - Use `assert round(compute_cost_usd(1000, 500), 6) == round(0.001 + 0.0025, 6)` and similar precise asserts.
    - One test for `running_total_usd(2099, 99) == 0.0` (no partition exists).
    - One test that writes 3 records and `running_total_usd` returns their sum.
    Why: LLM-04 mandates cost tracking with per-call data; CONTEXT.md specifies exact columns; the Parquet layout matches existing `data/ops/` conventions.
  </action>
  <acceptance_criteria>
    - `grep -nE "^class (CostLog|CostRecord)" src/sentiment/processing/cost_log.py` returns 2 hits
    - `grep -n "HAIKU_4_5_RATES" src/sentiment/processing/cost_log.py` returns at least 1 hit
    - `grep -n "def compute_cost_usd" src/sentiment/processing/cost_log.py` returns 1 hit
    - `python -c "from src.sentiment.processing.cost_log import compute_cost_usd, HAIKU_4_5_RATES; assert round(compute_cost_usd(1_000_000, 0), 4)==1.0; assert round(compute_cost_usd(0, 1_000_000), 4)==5.0"` exits 0
    - `python -m pytest tests/sentiment/test_cost_log.py -v` all pass
    - Directory structure: after running one test, `find {tmp_path}/season=* -name "llm_costs_*.parquet"` returns at least 1 file
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_cost_log.py -v</automated>
  </verify>
  <done>CostLog writes Parquet per the S3 key convention; math matches Haiku 4.5 rate table; running_total_usd sums correctly; fail-open on missing PyArrow.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement batched Claude primary extraction with prompt caching</name>
  <files>src/sentiment/processing/extractor.py, tests/sentiment/test_batched_claude_extractor.py</files>
  <read_first>
    - src/sentiment/processing/extractor.py (Plans 71-01 additions applied; legacy extract/extract_batch still present)
    - tests/sentiment/fakes.py (FakeClaudeClient from 71-02)
    - tests/fixtures/claude_responses/offseason_batch_w17.json (Claude response shape)
    - tests/fixtures/claude_responses/offseason_batch_w18.json (Claude response shape)
    - tests/fixtures/bronze_sentiment/offseason_w17_w18.json (input docs)
    - src/sentiment/processing/cost_log.py (just built in Task 1)
    - .planning/phases/71-llm-primary-extraction/71-CONTEXT.md (Prompt Design & Batching, Downstream Integration)
  </read_first>
  <behavior>
    - Test: `ClaudeExtractor(client=fake, roster_provider=lambda: ["Patrick Mahomes", "Travis Kelce"])` accepts a DI-injected fake client and roster provider without reading `ANTHROPIC_API_KEY`
    - Test: When `client` is None and `ANTHROPIC_API_KEY` is unset, `extract_batch_primary([...docs...])` returns `({}, [])` (fail-open) and logs a warning — does NOT raise
    - Test: Given 16 Bronze docs and `batch_size=8`, `extract_batch_primary` issues exactly 2 calls to `client.messages.create` (verified via `fake.call_log`)
    - Test: Each `messages.create` call has `system=[{..cache_control=ephemeral..}, {..cache_control=ephemeral..}]` — 2-element system list with cache_control markers on both entries
    - Test: The second system entry contains `"ACTIVE PLAYERS:"` followed by the player names from `roster_provider()`
    - Test: Using `FakeClaudeClient.from_fixture_dir("tests/fixtures/claude_responses/")` and Bronze docs from `tests/fixtures/bronze_sentiment/offseason_w17_w18.json`, `extract_batch_primary(docs_w17, season=2025, week=17)` (with `roster_provider=lambda: []` to match fixture-SHA determinism contract) returns >= 5 PlayerSignal objects total across all docs, each with `extractor == "claude_primary"` (the PlayerSignal.extractor default is "rule" — primary path MUST override it)
    - Test: Items with `player_name: null` in the Claude response are NOT returned in the by_doc_id dict; they appear in the second return value `non_player_items` as dicts with `team_abbr` populated
    - Test: Malformed JSON in Claude response (use `fake.register_response(sha, "not json!")`) results in a warning log for that batch and an empty signals list for those docs; no exception raised
    - Test: When `cost_log` is provided, one `CostRecord` is written per `messages.create` call with `doc_count` set to the batch size and `cost_usd` computed from the token fields in the fake response's `.usage`
    - Test: `extract_batch_primary` with no `cost_log` does NOT write any files (backward-compat)
    - Test: `batch_size` parameter honored — setting `batch_size=3` on 10 docs produces 4 calls (sizes 3,3,3,1)
  </behavior>
  <action>
    1. Open `src/sentiment/processing/extractor.py`. Import `Callable, Tuple` from typing, `uuid`, `datetime`, `timezone`. Import `CostRecord`, `CostLog`, `compute_cost_usd` from `src.sentiment.processing.cost_log`.
    2. Add module-level constants:
       ```python
       _MAX_TOKENS_BATCH = 4096   # Larger output budget for batched extraction
       _SYSTEM_PREFIX = """You are an NFL news analyst for a fantasy football product.
       Extract structured signals from NFL articles about specific players.
       For each player mentioned, return JSON with: player_name (or null for non-player subjects),
       team_abbr (3-letter NFL team code, optional),
       sentiment (-1.0 to +1.0 for fantasy value),
       confidence (0.0 to 1.0),
       category (one of: injury, usage, trade, weather, motivation, legal, general),
       events (dict of boolean flags; see list below),
       summary (<= 200 chars, 1 sentence),
       source_excerpt (<= 500 chars verbatim from article).

       Event flag keys: is_ruled_out, is_inactive, is_questionable, is_suspended, is_returning,
       is_traded, is_released, is_signed, is_activated, is_usage_boost, is_usage_drop, is_weather_risk.

       Return a JSON array. For non-player subjects (coach/reporter/team news),
       set player_name to null but populate team_abbr.

       Respond with JSON only; no prose, no markdown fences."""
       ```
    3. Extend `ClaudeExtractor.__init__` signature per `<interfaces>`. The new parameters — `client`, `roster_provider`, `cost_log`, `batch_size` — all default to None / BATCH_SIZE. Back-compat: when `client is None`, fall back to the existing `self._build_client()` path (so legacy `extract()` still works in `"claude"` mode).
    4. Add method `_build_batched_prompt(self, batch_docs: List[Dict]) -> str`: constructs the per-batch user message body. Format:
       ```
       Extract signals for the following articles.

       --- DOC 1 (external_id=xxx) ---
       TITLE: ...
       BODY: ...<truncated to 2000 chars>...

       --- DOC 2 (external_id=yyy) ---
       ...

       Return a single JSON array where each item includes a "doc_id" field matching the external_id from the header. This lets us map signals back to source docs.
       ```
    5. Add method `_get_roster_block(self) -> str`: if `self.roster_provider` is None, returns `""`. Otherwise calls it, returns up to first 1000 names joined by `", "`. If the provider raises, log a warning and return `""`.
    6. Add method `_call_claude_batch(self, batch_docs: List[Dict]) -> Tuple[str, Any]`: builds the Messages API call per the caching shape in `<interfaces>`. When `roster_block == ""`, drop the second system entry and log a one-time warning. Returns `(response_text, usage_object)` where `usage_object` has `.input_tokens`, `.output_tokens`, `.cache_read_input_tokens`, `.cache_creation_input_tokens`. If the client SDK does not return cache fields (older SDK), default them to 0.
    7. Add method `_parse_batch_response(self, raw: str, batch_docs: List[Dict]) -> Tuple[Dict[str, List[PlayerSignal]], List[Dict]]`: strips markdown fences using the same code path as the existing `_parse_response`. Expects a JSON array where each item optionally has `doc_id` matching the `external_id` of one of `batch_docs`. If `doc_id` is missing or not in the batch, log a debug message and drop the item. Items with `player_name: null` (or empty) get bucketed into the non_player list. Items with valid `player_name` get converted via a helper `_item_to_claude_signal(item, excerpt)` that: (a) re-uses the existing `_item_to_signal` logic for event flags / sentiment clamping / category validation, and (b) sets `extractor="claude_primary"`, `summary=item.get("summary","")[:200]`, `source_excerpt=item.get("source_excerpt","")[:500]`, `team_abbr=item.get("team_abbr")`.
    8. Add the main entry point `extract_batch_primary(self, docs: List[Dict], season: int, week: int) -> Tuple[Dict[str, List[PlayerSignal]], List[Dict]]`:
       - If `self._client is None` (no DI + no API key), log a warning and return `({}, [])`.
       - Slice docs into batches of `self.batch_size`.
       - For each batch, call `_call_claude_batch`, then `_parse_batch_response`, then accumulate.
       - After each call, if `self.cost_log` is set, compute cost via `compute_cost_usd(...)` from the usage fields and write a `CostRecord` with a fresh `call_id=uuid.uuid4().hex[:8]`, `ts=datetime.now(timezone.utc).isoformat()`, `doc_count=len(batch)`, `season=season`, `week=week`.
       - If a batch call raises ANY exception, log an error, leave those docs' signals empty, AND re-raise to the caller — upstream pipeline (Plan 71-04) is responsible for the per-doc soft fallback to RuleExtractor. Clarify: parse errors happen inside `_parse_batch_response` and are already swallowed via "empty list" — they never propagate up. Only actual API errors from `_call_claude_batch` propagate.
    Create `tests/sentiment/test_batched_claude_extractor.py`:
    - 10+ tests covering the behaviour bullets above. Use `FakeClaudeClient` from Plan 71-02 via DI (never `_build_client`). Use `tmp_path` for CostLog.
    - For the SHA-keyed fixture test: instantiate the extractor with `roster_provider=lambda: []` (per the fixture SHA determinism contract), compute the SHA via the `prompt_sha` helper from `tests.sentiment.fakes`, register responses under that SHA, call `extract_batch_primary`, assert >=5 signals. Update the fixture files' `prompt_sha` fields from `_PENDING_WAVE_2_SHA` to the real computed SHAs (using the empty roster) as part of this task (you now know the exact prompt structure).
    Why: CONTEXT.md D-01/D-02/D-04 all land here. The prompt-caching shape saves 70-90% of input-token cost on week-over-week reuse, which is the heart of LLM-04. Exception re-raise to the pipeline preserves the per-doc soft fallback contract (the pipeline catches and substitutes RuleExtractor — Plan 71-04).
  </action>
  <acceptance_criteria>
    - `grep -n "def extract_batch_primary" src/sentiment/processing/extractor.py` returns 1 hit
    - `grep -n "def _call_claude_batch\|def _build_batched_prompt\|def _parse_batch_response\|def _get_roster_block" src/sentiment/processing/extractor.py` returns 4 hits
    - `grep -n "cache_control" src/sentiment/processing/extractor.py` returns at least 2 hits (cache marker on static prefix + cache marker on roster block)
    - `grep -n "_MAX_TOKENS_BATCH\s*=" src/sentiment/processing/extractor.py` returns 1 hit
    - `grep -n "from src.sentiment.processing.cost_log" src/sentiment/processing/extractor.py` returns 1 hit
    - Fixture SHAs populated: `python -c "import json; d=json.load(open('tests/fixtures/claude_responses/offseason_batch_w17.json')); assert d['prompt_sha'] != '_PENDING_WAVE_2_SHA' and len(d['prompt_sha']) == 64"` exits 0
    - `python -m pytest tests/sentiment/test_batched_claude_extractor.py -v` all pass (10+ tests)
    - Back-compat: `python -m pytest tests/sentiment/ -v` entire suite passes
    - DI without API key: `python -c "from src.sentiment.processing.extractor import ClaudeExtractor; from tests.sentiment.fakes import FakeClaudeClient; e=ClaudeExtractor(client=FakeClaudeClient()); assert e._client is not None"` exits 0 (even without ANTHROPIC_API_KEY)
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_batched_claude_extractor.py tests/sentiment/ -v</automated>
  </verify>
  <done>ClaudeExtractor gains extract_batch_primary with prompt-cached system+roster, batching at BATCH_SIZE=8, non-player capture, cost logging via DI'd CostLog, fail-open on missing client, SHA-keyed fixture replay tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Benchmark stub — prove 5x signal lift on offseason W17/W18 fixture</name>
  <files>tests/sentiment/test_extractor_benchmark.py</files>
  <read_first>
    - tests/sentiment/fakes.py
    - tests/fixtures/bronze_sentiment/offseason_w17_w18.json
    - tests/fixtures/claude_responses/offseason_batch_w17.json
    - tests/fixtures/claude_responses/offseason_batch_w18.json
    - src/sentiment/processing/extractor.py (extract_batch_primary just built)
    - src/sentiment/processing/rule_extractor.py (RuleExtractor — produces 0 signals on offseason content)
    - .planning/phases/71-llm-primary-extraction/71-CONTEXT.md (LLM-03 benchmark description)
  </read_first>
  <behavior>
    - `test_claude_5x_rule_on_offseason`: loads the 30-doc offseason Bronze fixture, runs both RuleExtractor (real) and ClaudeExtractor(client=FakeClaudeClient.from_fixture_dir(...), roster_provider=lambda: []).extract_batch_primary against it, and asserts `signals_claude / max(signals_rule, 1) >= 5.0`
    - Also asserts `signals_claude >= 10` absolute floor (so a degenerate 0-rule / 0-claude case still fails)
    - Prints per-extractor counts to stdout for the Plan 71-05 benchmark summary harvest
  </behavior>
  <action>
    Create `tests/sentiment/test_extractor_benchmark.py`:
    1. Load the 30-doc Bronze fixture.
    2. Run `RuleExtractor().extract(doc)` on every doc and accumulate total signal count. RuleExtractor on offseason draft/trade/coaching content will produce ~0 signals — this is the core motivator.
    3. Build `FakeClaudeClient.from_fixture_dir(Path("tests/fixtures/claude_responses"))`.
    4. Instantiate `ClaudeExtractor(client=fake, roster_provider=lambda: [])` **— CRITICAL**: the `roster_provider=lambda: []` MUST match what was used when recording fixture SHAs (per Plan 71-02 Task 2 roster-determinism contract). If the benchmark uses a non-empty roster, the computed prompt SHA will differ from the fixture's `prompt_sha` and `FakeClaudeClient` (strict mode) will raise AssertionError. Register `FakeClaudeClient.register(...)` with a `prompt_sha` matching what `_build_batched_prompt` produces with `roster_provider=lambda: []`.
    5. Call `extract_batch_primary(docs, season=2025, week=17)` for W17 docs and the same for W18 docs. Sum the total signal counts.
    6. Assert `claude_total / max(rule_total, 1) >= 5.0` — this IS the LLM-03 test.
    7. Assert `claude_total >= 10` — absolute floor.
    8. Print `f"BENCHMARK: rule={rule_total} claude={claude_total} ratio={claude_total/max(rule_total,1):.2f}x"` for Plan 71-05 to grep from pytest output.
    Why: LLM-03 requires the 5x lift be measured and committed. This test is both the verifier and the regression guard against prompt drift. CONTEXT.md: "The benchmark test acts as both LLM-03 verifier and a regression guard for prompt drift." The empty-roster invariant is what makes SHAs deterministic across CI machines and dates.
  </action>
  <acceptance_criteria>
    - `test -f tests/sentiment/test_extractor_benchmark.py` exits 0
    - `grep -n "test_claude_5x_rule_on_offseason" tests/sentiment/test_extractor_benchmark.py` returns 1 hit
    - `grep -nE "roster_provider\s*=\s*lambda:\s*\[\]" tests/sentiment/test_extractor_benchmark.py` returns at least 1 hit (empty-roster determinism invariant)
    - `python -m pytest tests/sentiment/test_extractor_benchmark.py -v -s` passes; output contains the line matching `BENCHMARK: rule=\d+ claude=\d+ ratio=` with ratio >= 5.00
    - `python -m pytest tests/sentiment/test_extractor_benchmark.py -v 2>&1 | grep -E "ratio=[0-9]+\.[0-9]+x"` returns at least 1 match
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_extractor_benchmark.py -v -s</automated>
  </verify>
  <done>Benchmark test passes with claude/rule ratio >= 5.0 on the recorded offseason W17+W18 fixture; ratio line printed for Plan 71-05 to capture into SUMMARY.md.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| extractor → Claude API | Bronze doc text crossed as prompt; API key crossed via env |
| extractor → filesystem | Cost log Parquet written to local data/ops/ partition |
| extractor → test DI | FakeClaudeClient replaces real SDK without env-var leakage |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-71-03-01 | Information disclosure | Claude prompt contains Bronze article text | accept | Bronze is public NFL news; no PII concern |
| T-71-03-02 | Tampering | Malformed JSON from Claude could inject unexpected PlayerSignal fields | mitigate | `_parse_batch_response` whitelists keys; category clamped to _VALID_CATEGORIES; sentiment/confidence clamped; unknown event flags ignored |
| T-71-03-03 | Denial of Service | Runaway batch size blowing up output_tokens | mitigate | _MAX_TOKENS_BATCH=4096 caps output; BATCH_SIZE=8 default caps input size |
| T-71-03-04 | Repudiation | Cost overrun without audit trail | mitigate | Every call writes a CostRecord to Parquet with call_id, ts, usage breakdown |
| T-71-03-05 | Spoofing | Test calling real API bypass | mitigate | DI via `client` parameter; benchmark test uses FakeClaudeClient; README documents prohibition |
| T-71-03-06 | Elevation of privilege | API key leaked through logs | mitigate | Reuse existing fail-open `_build_client` pattern (never log the key); no change to existing env handling |
</threat_model>

<verification>
- `python -m pytest tests/sentiment/ -v` — entire sentiment suite green including new test_cost_log, test_batched_claude_extractor, test_extractor_benchmark
- `grep -n "cache_control" src/sentiment/processing/extractor.py` returns >= 2 hits
- Benchmark ratio >= 5.0 printed from pytest -s
- Cost log Parquet files created in tmp_path by test harness
</verification>

<success_criteria>
- `ClaudeExtractor.extract_batch_primary` batched extraction works end-to-end with FakeClaudeClient
- Prompt caching markers present on both static prefix and active-roster block
- Cost log module writes per-call Parquet records with all 10 columns
- Non-player items captured via second return value (ready for Plan 71-04 to bucket)
- Benchmark test passes with ratio >= 5x (LLM-03 verified)
- No regression in the existing 6 sentiment test files
</success_criteria>

<output>
After completion, create `.planning/phases/71-llm-primary-extraction/71-03-SUMMARY.md`. Include the claude/rule signal ratio from the benchmark test output.
</output>
