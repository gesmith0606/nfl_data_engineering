---
phase: 71-llm-primary-extraction
plan: 02
type: execute
wave: 2
depends_on:
  - 71-01
files_modified:
  - tests/sentiment/fakes.py
  - tests/fixtures/claude_responses/offseason_batch_w17.json
  - tests/fixtures/claude_responses/offseason_batch_w18.json
  - tests/fixtures/bronze_sentiment/offseason_w17_w18.json
  - tests/fixtures/claude_responses/README.md
  - tests/sentiment/test_fake_claude_client.py
autonomous: true
requirements:
  - LLM-05
  - LLM-03
must_haves:
  truths:
    - "A deterministic `FakeClaudeClient` exists that replays recorded Claude JSON responses keyed by SHA-256 of the prompt"
    - "A recorded 2025 W17+W18 offseason Bronze fixture batch of >= 30 documents exists"
    - "Recorded Claude response fixtures exist for each batch the tests will issue"
    - "The fake client exposes the same `.messages.create(...)` surface as `anthropic.Anthropic` so DI works through the ClaudeClient Protocol"
  artifacts:
    - path: "tests/sentiment/fakes.py"
      provides: "FakeClaudeClient with SHA-256 prompt keying, input/output/cache token counts, retry/exception hooks"
      exports: ["FakeClaudeClient", "FakeMessages", "FakeMessageResponse"]
      min_lines: 120
    - path: "tests/fixtures/bronze_sentiment/offseason_w17_w18.json"
      provides: "30+ Bronze docs scrubbed from real 2025 W17/W18 RSS + PFT + Reddit ingestions"
      min_lines: 30
    - path: "tests/fixtures/claude_responses/offseason_batch_w17.json"
      provides: "Recorded Claude JSON array response for W17 batches (>=5 signals)"
    - path: "tests/fixtures/claude_responses/offseason_batch_w18.json"
      provides: "Recorded Claude JSON array response for W18 batches (>=5 signals)"
    - path: "tests/fixtures/claude_responses/README.md"
      provides: "Documentation for re-recording fixtures; explains SHA-256 keying and why CI must never hit live API"
  key_links:
    - from: "tests/sentiment/fakes.py::FakeClaudeClient"
      to: "ClaudeClient Protocol in src/sentiment/processing/extractor.py"
      via: "structural duck-typing (exposes `.messages.create(...)`)"
      pattern: "class FakeClaudeClient"
    - from: "tests/sentiment/fakes.py"
      to: "tests/fixtures/claude_responses/*.json"
      via: "SHA-256(prompt_text) → fixture file lookup"
      pattern: "hashlib.sha256"
---

<objective>
Build the deterministic test harness that powers every Claude-related test in Plans 71-03..71-05. Produces (1) a `FakeClaudeClient` replaying recorded responses keyed by SHA-256 of the outgoing prompt and reporting realistic token counts, (2) a scrubbed 2025 W17+W18 Bronze fixture batch of at least 30 offseason documents, and (3) at least 2 recorded Claude response fixtures covering those batches. No live Anthropic calls in CI — ever.

Purpose: Per LLM-05, "Claude-extraction tests use recorded fixtures (VCR-style), not live API calls — deterministic CI." This plan ships the replay infrastructure so every subsequent test gets a stable input→output pair.
Output: `tests/sentiment/fakes.py`, fixture JSON files, and fixture-harness tests.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/71-llm-primary-extraction/71-CONTEXT.md
@src/sentiment/processing/extractor.py
@tests/sentiment/test_llm_enrichment_optional.py

<interfaces>
<!-- Shapes consumed by Plans 71-03 / 71-04 / 71-05 -->

The `FakeClaudeClient` is duck-typed to match `anthropic.Anthropic`. It MUST expose:

```python
class FakeMessageResponse:
    content: list  # [TextBlock(text="...json...")]
    usage: "FakeUsage"  # .input_tokens, .output_tokens, .cache_read_input_tokens, .cache_creation_input_tokens

class FakeMessages:
    def create(self, *, model: str, max_tokens: int,
               system=None, messages=None, **kwargs) -> FakeMessageResponse:
        # 1) Compute sha256 of a canonicalised string of (model, system, messages).
        # 2) Look up prebuilt response for that key.
        # 3) If not found AND strict=True → raise AssertionError with diagnostic.
        # 4) If not found AND strict=False → return a stub empty-array response.
        # 5) If key matches a registered "failure" spec → raise the recorded exception.

class FakeClaudeClient:
    messages: FakeMessages
    call_log: list  # Record of (sha256, model, max_tokens) for later assertion
    def register_response(self, prompt_key_or_sha: str, response_json: Any,
                          input_tokens: int = 500, output_tokens: int = 200,
                          cache_read_input_tokens: int = 0,
                          cache_creation_input_tokens: int = 0) -> None: ...
    def register_failure(self, prompt_key_or_sha: str, exc: Exception) -> None: ...
    @classmethod
    def from_fixture_dir(cls, fixture_dir: Path, strict: bool = True) -> "FakeClaudeClient": ...
```

The canonicalisation function for the SHA key MUST be:

```python
def prompt_sha(system: Any, messages: Any, model: str) -> str:
    payload = json.dumps(
        {"model": model, "system": system, "messages": messages},
        sort_keys=True, default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

Fixture JSON file shape for recorded responses:

```json
{
  "_comment": "Recorded Claude Haiku 4.5 response for 2025 W17 batch.",
  "prompt_sha": "abc123...",                // 64-hex SHA-256 of {model,system,messages}
  "model": "claude-haiku-4-5",
  "input_tokens": 1243,
  "output_tokens": 487,
  "cache_read_input_tokens": 1100,
  "cache_creation_input_tokens": 0,
  "response_text": "[{\"player_name\":\"Travis Kelce\",\"sentiment\":-0.3,...}]"
}
```

Bronze fixture file shape (matches real `data/bronze/sentiment/rss/season=2025/...` layout):

```json
{
  "items": [
    {
      "external_id": "pft-2025w17-001",
      "source": "rss_pft",
      "title": "Report: Giants could use first-round pick on a quarterback",
      "body_text": "The New York Giants are expected to explore trading up...",
      "published_at": "2025-12-29T14:23:00+00:00",
      "season": 2025,
      "week": 17
    },
    ...
  ]
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Build FakeClaudeClient with SHA-256 keying and token accounting</name>
  <files>tests/sentiment/fakes.py, tests/sentiment/test_fake_claude_client.py</files>
  <read_first>
    - src/sentiment/processing/extractor.py (ClaudeClient Protocol added in 71-01; legacy _call_claude for reference)
    - src/sentiment/enrichment/llm_enrichment.py lines 216-260 (real SDK call shape: `response.content[0].text`, `.usage.input_tokens`, `.usage.output_tokens`)
    - tests/sentiment/test_llm_enrichment_optional.py (existing mock pattern — we are UPGRADING from unittest.mock.MagicMock to a typed fake)
  </read_first>
  <behavior>
    - Test: `FakeClaudeClient()` instantiates with empty call_log and messages attribute
    - Test: `fake.register_response("sha-xyz", [{"player_name": "Test"}])` then `fake.messages.create(model="m", max_tokens=1, system="sys", messages=[{"role":"user","content":"x"}])` returns a response whose `content[0].text` is `"[{\"player_name\": \"Test\"}]"` — but ONLY if the SHA of `{model,system,messages}` matches `"sha-xyz"` OR if you explicitly register by computed SHA
    - Test: `fake.messages.create(...)` on an unregistered prompt raises `AssertionError` when `strict=True` (default) with a diagnostic including the computed SHA and the list of registered SHAs
    - Test: `fake.messages.create(...)` on a prompt registered via `register_failure("sha-abc", RuntimeError("boom"))` raises `RuntimeError("boom")`
    - Test: Response `.usage.input_tokens`, `.usage.output_tokens`, `.usage.cache_read_input_tokens`, `.usage.cache_creation_input_tokens` reflect the values passed to `register_response`
    - Test: `fake.call_log` is a list of tuples `(sha, model, max_tokens)` appended on every `.messages.create()` call
    - Test: `FakeClaudeClient.from_fixture_dir(tmp_path)` loads every `.json` file, uses the file's `prompt_sha` field as the key, reconstructs a response with the recorded `response_text` + token counts
  </behavior>
  <action>
    Create `tests/sentiment/fakes.py` with the classes exactly as shaped in `<interfaces>`. Implementation notes:
    1. Use `dataclasses.dataclass` for `FakeUsage`, `FakeTextBlock`, `FakeMessageResponse`.
    2. `prompt_sha(system, messages, model)` as a module-level helper (exported). Use the canonicalisation in `<interfaces>`.
    3. `register_response(prompt_key_or_sha, ...)` accepts either a 64-char hex SHA or any arbitrary string (tests may use either — the latter is useful when the test pre-computes the SHA itself). If the key is not 64-char hex, treat it as a pre-computed literal.
    4. `response_json` in `register_response` is either a Python list/dict (in which case `json.dumps` is applied) or a raw string (stored verbatim — useful for fixtures that contain markdown fences).
    5. `register_failure(prompt_key_or_sha, exc)` stores exception-by-key. On `.messages.create()`, check failures BEFORE looking up responses.
    6. `from_fixture_dir(path, strict=True)` walks `*.json` files, skips `README.md`, and calls `register_response` using the file's `prompt_sha` as key + `response_text` + the 4 token counts.
    7. `strict=True` default: unregistered prompts raise `AssertionError(f"No FakeClaudeClient response registered for sha={sha}. Registered: {sorted(self._responses.keys())}")`.
    8. `strict=False`: unregistered prompts return an empty-array response `"[]"` with zero token counts — useful in tests that care about fallback behaviour, not response content.
    Create `tests/sentiment/test_fake_claude_client.py` with 8 pytest tests corresponding to the behaviour bullets above. Use `tmp_path` for the `from_fixture_dir` test (write 1-2 JSON files into the tmp dir).
    Why this design: CONTEXT.md D-03 "Tests inject the fake client via constructor DI (no monkeypatching `_build_client`)" + "A FakeClaudeClient in tests/sentiment/fakes.py replays them keyed by SHA-256(prompt)." SHA keying is stable across reorderings because we `sort_keys=True` in the canonicalisation.
  </action>
  <acceptance_criteria>
    - `grep -nE "^class (FakeClaudeClient|FakeMessages|FakeMessageResponse|FakeUsage|FakeTextBlock)" tests/sentiment/fakes.py` returns 5 lines
    - `grep -n "def prompt_sha" tests/sentiment/fakes.py` returns 1 hit
    - `grep -n "hashlib.sha256" tests/sentiment/fakes.py` returns at least 1 hit
    - `grep -n "register_response\|register_failure\|from_fixture_dir" tests/sentiment/fakes.py` returns at least 3 hits
    - `python -m pytest tests/sentiment/test_fake_claude_client.py -v` all 8 tests pass
    - Structural compatibility: `python -c "from tests.sentiment.fakes import FakeClaudeClient; f=FakeClaudeClient(); assert hasattr(f, 'messages') and hasattr(f.messages, 'create')"` exits 0
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_fake_claude_client.py -v</automated>
  </verify>
  <done>FakeClaudeClient duck-types the Anthropic client surface; SHA-keyed replay works; strict mode and failure injection both work; fixture directory loader works; 8 tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Record offseason Bronze + Claude fixture set for W17/W18 2025</name>
  <files>tests/fixtures/bronze_sentiment/offseason_w17_w18.json, tests/fixtures/claude_responses/offseason_batch_w17.json, tests/fixtures/claude_responses/offseason_batch_w18.json, tests/fixtures/claude_responses/README.md</files>
  <read_first>
    - data/bronze/sentiment/rss/ (list contents — real W17/W18 2025 files may exist to copy scrubbed content from)
    - data/bronze/sentiment/pft/ (pro football talk fixtures — offseason-rich)
    - tests/sentiment/fakes.py (just built in Task 1 — consumers of this fixture)
    - .planning/phases/71-llm-primary-extraction/71-CONTEXT.md (LLM-03 benchmark: >=30 Bronze docs)
  </read_first>
  <behavior>
    - `tests/fixtures/bronze_sentiment/offseason_w17_w18.json` contains an envelope `{"items": [...]}` with >= 30 Bronze docs split roughly evenly between `season=2025 week=17` and `season=2025 week=18`, each with `external_id`, `source`, `title`, `body_text`, `published_at`, `season`, `week`
    - Offseason content skew: >= 15 of the 30 docs MUST contain draft / trade-rumor / coaching / rookie-buzz language (not pure injury reports) — these are the docs that rule-extraction produces 0 signals for and Claude will shine on
    - `tests/fixtures/claude_responses/offseason_batch_w17.json` contains recorded Claude output for a batch that covers the W17 subset of the Bronze fixture. The `response_text` MUST be a JSON array of >= 5 items with the 71-01 extended shape (`player_name`, `sentiment`, `confidence`, `category`, `events`, and optional `summary`, `source_excerpt`, `team_abbr`). At least 2 items should carry `team_abbr` and `player_name: null` to exercise the non-player path.
    - `tests/fixtures/claude_responses/offseason_batch_w18.json` follows same shape for W18, >= 5 items
    - `tests/fixtures/claude_responses/README.md` documents: what each file is, the canonicalisation used to compute `prompt_sha`, how to re-record (the helper script shipped in Plan 71-03), and the CI rule that live API calls are forbidden
    - **Fixture SHA determinism contract**: fixtures MUST be recorded with a frozen `roster_provider=lambda: []` (empty list) so the SHA computation depends only on the system prefix + docs (no dynamic roster contents). Plan 71-03's batched extractor tests and benchmark MUST use the same `roster_provider=lambda: []` when calling `extract_batch_primary` so the computed SHA matches the fixture's `prompt_sha`.
  </behavior>
  <action>
    1. Build the Bronze fixture by scrubbing real content from `data/bronze/sentiment/rss/season=2025/` and `data/bronze/sentiment/pft/season=2025/` if W17/W18 files exist. If not, synthesize plausible offseason content. For scrubbing: remove author names/emails, truncate body_text to <= 800 chars, keep player names and team abbreviations. Content MUST cover: draft prospects, trade rumors, coaching changes, rookie-buzz, alongside a few injury docs.
    2. Write `tests/fixtures/bronze_sentiment/offseason_w17_w18.json` with envelope `{"items": [...]}` and >= 30 docs. Split 15 W17 + 15 W18. Each doc MUST have keys: `external_id` (e.g. `"rss_pft_w17_001"`), `source`, `title`, `body_text`, `published_at`, `season=2025`, `week` (17 or 18). Title + body should include player names that appear in the real `data/bronze/players/rosters/` parquet so the resolver can match them later.
    3. For the Claude response fixtures: do NOT set `prompt_sha` to a real computed SHA yet — use the placeholder `"_PENDING_WAVE_2_SHA"` (Plan 71-03 will compute the actual SHA once the batched prompt function exists). This is acceptable because Task 3 below verifies structure, not SHA matching; Plan 71-03 will update the `prompt_sha` field post-implementation as part of its recording workflow.
    4. **Roster-provider determinism contract (CRITICAL — depends on by Plan 71-03):** Fixtures MUST be recorded with a frozen `roster_provider=lambda: []` so the SHA computation depends only on the static system prefix + the per-doc user block. Document this in `README.md` as a hard invariant: if the roster list varies across runs, SHA matching breaks. Plan 71-03's `_build_batched_prompt` and its benchmark test MUST call `extract_batch_primary` with a `roster_provider=lambda: []` for the test/benchmark paths; production-mode uses the real roster provider (different SHAs, different fixture set if needed in future).
    5. Each Claude response fixture must have: `model="claude-haiku-4-5"`, `input_tokens` (~1200-1800 for a batch of ~8 docs with cached player list), `output_tokens` (~400-800), `cache_read_input_tokens` (non-zero for W18, zero for W17 — simulates first-week cache miss vs second-week cache hit), `cache_creation_input_tokens` (~1100 for W17, 0 for W18), `response_text` as a JSON string encoding an array of >= 5 signal items. Include at least 2 non-player items (`player_name: null, team_abbr: "NYG"`) per file to cover EVT-02 prep.
    6. Write `tests/fixtures/claude_responses/README.md` with sections: "Purpose", "File Shape", "prompt_sha Computation", "Roster-Provider Determinism Contract" (document the `roster_provider=lambda: []` invariant), "Re-recording Procedure", "CI Prohibition on Live Calls (LLM-05)".
    Why this design: CONTEXT.md "tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason runs both extractors on the recorded 2025 W17+W18 Bronze fixture batch (>= 30 docs)." Offseason skew is what makes the 5x claim testable — rule-based produces near-zero signals on draft/trade content. The frozen empty-roster provider ensures fixture SHA determinism across machines, dates, and roster-parquet updates.
  </action>
  <acceptance_criteria>
    - `test -f tests/fixtures/bronze_sentiment/offseason_w17_w18.json` exits 0
    - `python -c "import json; d=json.load(open('tests/fixtures/bronze_sentiment/offseason_w17_w18.json')); items=d['items']; assert len(items) >= 30, len(items); assert sum(1 for i in items if i['week']==17) >= 10; assert sum(1 for i in items if i['week']==18) >= 10; assert all('external_id' in i and 'body_text' in i and i['season']==2025 for i in items)"` exits 0
    - `python -c "import json; d=json.load(open('tests/fixtures/claude_responses/offseason_batch_w17.json')); assert 'response_text' in d and 'input_tokens' in d and 'cache_creation_input_tokens' in d; arr=json.loads(d['response_text']); assert len(arr) >= 5; assert sum(1 for r in arr if r.get('player_name') is None) >= 2"` exits 0
    - Same validation on W18: `python -c "import json; d=json.load(open('tests/fixtures/claude_responses/offseason_batch_w18.json')); arr=json.loads(d['response_text']); assert len(arr) >= 5 and d['cache_read_input_tokens'] > 0"` exits 0
    - `test -f tests/fixtures/claude_responses/README.md && grep -qi "live" tests/fixtures/claude_responses/README.md && grep -qi "prompt_sha" tests/fixtures/claude_responses/README.md` exits 0
    - README documents the roster-provider determinism invariant: `grep -qiE "roster_provider.*lambda.*\[\]|empty.*roster|frozen.*roster" tests/fixtures/claude_responses/README.md` exits 0
    - Offseason keyword coverage: `python -c "import json; d=json.load(open('tests/fixtures/bronze_sentiment/offseason_w17_w18.json')); kws=['draft','trade','coach','rookie']; hits=sum(1 for i in d['items'] if any(k in (i['title']+i['body_text']).lower() for k in kws)); assert hits >= 15, hits"` exits 0
  </acceptance_criteria>
  <verify>
    <automated>python -c "import json; b=json.load(open('tests/fixtures/bronze_sentiment/offseason_w17_w18.json'))['items']; w17=json.load(open('tests/fixtures/claude_responses/offseason_batch_w17.json')); w18=json.load(open('tests/fixtures/claude_responses/offseason_batch_w18.json')); assert len(b)>=30 and len(json.loads(w17['response_text']))>=5 and len(json.loads(w18['response_text']))>=5; print('FIXTURES_OK')"</automated>
  </verify>
  <done>Bronze fixture contains >=30 offseason-skewed docs; two Claude response fixtures contain >=5 signals each including non-player items; README documents re-recording rules, LLM-05 CI prohibition, AND the `roster_provider=lambda: []` determinism invariant that Plan 71-03 must honor.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire FakeClaudeClient.from_fixture_dir to the recorded fixtures</name>
  <files>tests/sentiment/test_fake_claude_client.py</files>
  <read_first>
    - tests/sentiment/fakes.py (just built in Task 1)
    - tests/fixtures/claude_responses/offseason_batch_w17.json (from Task 2)
    - tests/fixtures/claude_responses/offseason_batch_w18.json (from Task 2)
  </read_first>
  <behavior>
    - Test: `FakeClaudeClient.from_fixture_dir(Path("tests/fixtures/claude_responses"))` loads both batch_w17 and batch_w18 JSON files, registering each with its `prompt_sha` key
    - Test: After loading, `fake.call_log == []` initially; after one `fake.messages.create(...)` with a registered SHA, `fake.call_log` has length 1
    - Test: The loader skips non-JSON files (e.g. `README.md`) without error
    - Test: If the placeholder `_PENDING_WAVE_2_SHA` is used, the loader still loads the file but a strict `.messages.create()` with a real SHA will raise (documents the two-phase workflow for Plan 71-03)
  </behavior>
  <action>
    Add the following tests to `tests/sentiment/test_fake_claude_client.py` (do not create a new file — append to the Task-1 test file):
    1. `test_from_fixture_dir_loads_offseason_batches` — points at `tests/fixtures/claude_responses/` and asserts both W17 and W18 fixtures are loaded (check `len(fake._responses) >= 2`).
    2. `test_from_fixture_dir_skips_readme` — in a tmp dir with one JSON + one `README.md`, asserts no exception and only 1 response registered.
    3. `test_placeholder_sha_is_loaded_but_unusable` — loads a fixture with `prompt_sha: "_PENDING_WAVE_2_SHA"`, then calls `.messages.create()` with a real computed SHA and asserts the expected AssertionError message mentions the registered placeholder.
    4. `test_call_log_grows_monotonically` — makes 3 `.messages.create()` calls against registered SHAs and asserts `len(fake.call_log) == 3` with correct tuple shape.
    Use `tmp_path` fixture for tests 2 and 3 to avoid polluting the real fixtures dir.
    Why: CONTEXT.md "A FakeClaudeClient in tests/sentiment/fakes.py replays them keyed by SHA-256(prompt)." Plan 71-03 depends on `from_fixture_dir` working against these fixture files — this task locks in that contract.
  </action>
  <acceptance_criteria>
    - `python -m pytest tests/sentiment/test_fake_claude_client.py -v` — all tests pass (>= 12 total when combined with Task 1)
    - `python -c "from pathlib import Path; from tests.sentiment.fakes import FakeClaudeClient; f=FakeClaudeClient.from_fixture_dir(Path('tests/fixtures/claude_responses')); assert len(f._responses) >= 2"` exits 0
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_fake_claude_client.py -v</automated>
  </verify>
  <done>Fixture loader integrates with recorded W17/W18 Claude responses; placeholder SHA workflow documented via test; call log grows as expected.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| fixture → CI | Recorded Claude responses drive deterministic tests; no network crossed |
| Bronze fixture → resolver | Player names may appear; no real PII beyond public names already in rosters parquet |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-71-02-01 | Information disclosure | Bronze fixture content | mitigate | Scrub author names/emails during copying from real data; body_text truncated to 800 chars; only public NFL content used |
| T-71-02-02 | Tampering | FakeClaudeClient returning empty array in non-strict mode | mitigate | Default `strict=True`; non-strict mode is opt-in and documented |
| T-71-02-03 | Denial of Service | Fixture JSON files growing unbounded over time | accept | One-time recording; files capped at 2 batches of ~8 docs each |
| T-71-02-04 | Spoofing | A test hitting the real API instead of the fake | mitigate | README.md documents LLM-05 CI prohibition; benchmark test in Plan 71-05 asserts fake client is used |
</threat_model>

<verification>
- `python -m pytest tests/sentiment/test_fake_claude_client.py -v` — all tests pass
- Bronze fixture has >= 30 docs with offseason keyword coverage >= 15
- Both Claude response fixtures have >= 5 signals, at least 2 non-player items each
- README.md documents re-recording procedure and live-API prohibition
</verification>

<success_criteria>
- `tests/sentiment/fakes.py` exports `FakeClaudeClient`, `prompt_sha`, registers-and-replays by SHA-256, supports failure injection, strict/non-strict modes, and fixture-directory loading
- >= 30 Bronze fixture docs covering W17 + W18 offseason content committed to git
- >= 2 Claude response fixtures with realistic token counts and non-player items committed to git
- `tests/fixtures/claude_responses/README.md` documents the rules
- 12+ tests in `test_fake_claude_client.py` all green
</success_criteria>

<output>
After completion, create `.planning/phases/71-llm-primary-extraction/71-02-SUMMARY.md`.
</output>
