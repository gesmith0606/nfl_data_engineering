---
phase: 61-news-sentiment-live
plan: 06
subsystem: sentiment-enrichment
tags: [llm, claude-haiku, feature-flag, d-02, d-04, d-06, fail-open, news]

# Dependency graph
requires:
  - file: "scripts/daily_sentiment_pipeline.py"
    provides: "8-step orchestrator + reserved --enable-llm-enrichment CLI + ENABLE_LLM_ENRICHMENT env surface from 61-04"
  - file: "web/api/models/schemas.py::NewsItem.summary"
    provides: "Reserved NewsItem.summary field from 61-05 ready to receive enrichment"
  - file: "src/sentiment/processing/extractor.py::ClaudeExtractor"
    provides: "Existing Anthropic client construction pattern that the new module reuses"
  - file: "src/sentiment/processing/pipeline.py::SentimentPipeline"
    provides: "Auto-mode extractor selection point that now locks to RuleExtractor per D-02"
provides:
  - "src/sentiment/enrichment/llm_enrichment.py: LLMEnrichment class + enrich_silver_records() batch driver"
  - "src/sentiment/enrichment/__init__.py: package with LLMEnrichment + enrich_silver_records exports"
  - "scripts/daily_sentiment_pipeline.py::_run_llm_enrichment: Step 6.5/8 wrapper gated on enable_llm_enrichment"
  - "scripts/daily_sentiment_pipeline.py: --enable-llm-enrichment flag wired (was a no-op) + ENABLE_LLM_ENRICHMENT env fallback in main()"
  - "web/api/services/news_service.py::_load_enriched_summary_index + _apply_enrichment: sidecar merge plumbing"
  - "web/api/services/news_service.py::get_news_feed + get_player_news: auto-merge summary + refined_category when sidecar exists"
  - "tests/sentiment/test_llm_enrichment_optional.py: 6 tests locking in fail-open + non-destructive contracts"
affects:
  - "Phase 61 closes out: NEWS-02 enriched cards shippable once the ENABLE_LLM_ENRICHMENT repo variable is flipped to true AND ANTHROPIC_API_KEY is set in Railway"
  - "SentimentPipeline auto-mode now uses RuleExtractor even when ANTHROPIC_API_KEY is set (D-02) — any external caller relying on the old 'auto means Claude' behaviour needs to opt in with extractor_mode='claude'"
  - "web/api/services/news_service reads a NEW directory (signals_enriched/) that the daily cron only populates when enrichment is toggled on"

# Tech tracking
tech-stack:
  added: []  # re-uses existing anthropic==0.92.0 dependency
  patterns:
    - "Feature-flagged module boundary: ENABLE_LLM_ENRICHMENT + ANTHROPIC_API_KEY must BOTH be set; either absent -> module returns records unchanged"
    - "Fail-open in three places: _build_client (ImportError/Exception), enrich() (SDK exception -> unchanged record), enrich_silver_records (per-record try/except)"
    - "Deferred import: anthropic SDK only imported on _build_client() — disabled pipelines never trigger the import path"
    - "Non-destructive sidecar pattern: signals/ files are NEVER touched; enriched records land in signals_enriched/season=YYYY/week=WW/enriched_{batch_id}_{ts}.json"
    - "Immutable event flags: enrich() adds optional summary + refined_category but never overrides rule-extracted events (T-61-06-05 mitigation)"
    - "Log-hygiene invariant: every startup line logs bool(os.environ.get('ANTHROPIC_API_KEY')) — never the value (T-61-06-01 mitigation)"
    - "Step-label convention: insertion fraction (Step 6.5/8) signals 'optional sub-step' without renumbering neighbouring labels"

key-files:
  created:
    - "src/sentiment/enrichment/__init__.py"
    - "src/sentiment/enrichment/llm_enrichment.py (~370 lines post-black)"
    - "tests/sentiment/test_llm_enrichment_optional.py (~290 lines, 6 tests)"
    - ".planning/phases/61-news-sentiment-live/61-06-SUMMARY.md"
  modified:
    - "scripts/daily_sentiment_pipeline.py (+85 lines — Step 6.5 wrapper, CLI wiring, env var fallback)"
    - "src/sentiment/processing/extractor.py (+21 lines — deprecation docstring; no behaviour change)"
    - "src/sentiment/processing/pipeline.py (+7 lines — auto-mode locks to RuleExtractor per D-02)"
    - "web/api/services/news_service.py (+123 lines — sidecar loader + merge plumbing in both feed endpoints)"

key-decisions:
  - "Default off + double-gated: ENABLE_LLM_ENRICHMENT and ANTHROPIC_API_KEY must BOTH be set for enrichment to fire. Either alone yields a clean no-op exit."
  - "Deferred anthropic SDK import inside _run_llm_enrichment: import only happens when the step is enabled, so disabled pipelines never pay the import cost or surface SDK install warnings."
  - "Auto-mode in SentimentPipeline locks to RuleExtractor (D-02) even when ANTHROPIC_API_KEY is set. 'claude' mode still works for explicit callers (comparison tests) but the default production path is now rule-first regardless of key presence."
  - "Non-destructive sidecar writes to signals_enriched/ (separate sub-tree) rather than mutating signals/. Keeps the model-path data pristine; if enrichment ever regresses or gets disabled, the news-service silently degrades to raw rule data."
  - "refined_category overrides the raw rule category on display in the news card; original category remains available on the Silver record (not mutated)."
  - "CLI flag --enable-llm-enrichment uses action='store_true' with default=None so we can distinguish 'user explicitly passed --enable-llm-enrichment' from 'user did not pass the flag' when resolving against the env var in main()."
  - "Per-record enrichment still fails open even inside enrich_silver_records — the outer try/except is belt-and-braces because enrich() itself already returns unchanged on any exception."
  - "Clamp summary to 200 chars and validate refined_category against the existing _VALID_CATEGORIES allow-list (T-61-06-02 mitigation for prompt injection + category poisoning)."

patterns-established:
  - "Optional LLM sub-step pattern: any future 'nice-to-have LLM polish' in this codebase should follow the same double-gated env var + graceful degrade + sidecar-write shape (model path untouched)."
  - "Sidecar-merge pattern in news_service: read-time LOOKUP + in-place merge lets the service silently pick up new decorations without schema changes."

requirements-completed: [NEWS-02]

# Metrics
duration: 17min
completed: 2026-04-19
---

# Phase 61 Plan 06: Optional LLM Enrichment Summary

**Claude Haiku enrichment shipped as a strictly optional, double-gated post-processing step that adds website-only 1-sentence summaries + refined categories to NewsItem cards, never touches the model path, and degrades to a clean no-op when either ENABLE_LLM_ENRICHMENT or ANTHROPIC_API_KEY is unset.**

## Performance

- **Duration:** ~17 min (1 TDD cycle + 1 plumbing task + SUMMARY)
- **Started:** 2026-04-19T04:15:22Z
- **Completed:** 2026-04-19T04:32:20Z
- **Tasks:** 2 (both shipped, all 6 new + 7 existing resilience tests green)
- **Files created:** 4 (2 new source files + 1 test + this SUMMARY)
- **Files modified:** 4

## Accomplishments

### Task 1 — LLMEnrichment module + D-02 pipeline lock (SHIPPED)

- Created `src/sentiment/enrichment/llm_enrichment.py`: `LLMEnrichment` class with fail-open `_build_client()` (returns None on missing key / missing SDK / any exception), `enrich(record)` method that adds `summary` (≤ 200 chars) + `refined_category` (validated against the same `_VALID_CATEGORIES` allow-list used in the legacy extractor), and `enrich_silver_records(season, week, dry_run)` batch driver that walks Silver envelopes and writes non-destructive sidecar files.
- Sidecar path: `data/silver/sentiment/signals_enriched/season=YYYY/week=WW/enriched_{batch_id}_{ts}.json`. Original `signals/` files are NEVER touched.
- Demoted `ClaudeExtractor` in `src/sentiment/processing/extractor.py` by adding a deprecation block at the top of the class docstring pointing callers at the new module. The class itself still works for explicit `extractor_mode="claude"` callers / comparison tests — behavior is unchanged there.
- Locked `SentimentPipeline._build_extractor` auto-mode to `RuleExtractor` per D-02. The relevant log line: `"Using rule-based extractor in auto mode (Phase 61 D-02: rules are primary, LLM is optional enrichment via src.sentiment.enrichment)."` The prior behaviour of "use Claude if available, fall back to rules" is gone from the default path.
- 6 TDD tests in `tests/sentiment/test_llm_enrichment_optional.py` pin the contracts:
  1. `is_available` is `False` without `ANTHROPIC_API_KEY`.
  2. `enrich()` passthrough when unavailable (no `summary`, no `refined_category` added).
  3. `enrich()` catches any SDK exception and fails open.
  4. Success path populates both fields and clamps summary to 200 chars.
  5. `enrich_silver_records()` with no Silver files returns `0` and does not raise.
  6. Sidecar output lands in `signals_enriched/` and the original file is byte-for-byte unchanged.
- Broader regression: `python -m pytest tests/sentiment/` → 59/59 passed.

### Task 2 — Pipeline Step 6.5 + news_service sidecar merge (SHIPPED)

- Added `_run_llm_enrichment(season, week, enabled, dry_run, verbose)` wrapper in `scripts/daily_sentiment_pipeline.py`. Early-returns a `StepResult(success=True, detail="disabled (ENABLE_LLM_ENRICHMENT=false)")` when `enabled is False`. When enabled, defers the `from src.sentiment.enrichment import enrich_silver_records` import so disabled pipelines never touch the anthropic machinery. Any exception inside `enrich_silver_records()` becomes `success=False` but the pipeline continues to aggregation (D-06).
- Step 6.5/8 is inserted between extraction (Step 6/8) and player aggregation (Step 7/8). The startup log line `"LLM Enrichment: enabled=X, API key present=Y"` is emitted for every run — the key value itself is NEVER logged (T-61-06-01 mitigation).
- CLI flag `--enable-llm-enrichment` is now actually wired (no longer a no-op placeholder from 61-04). `main()` falls back to the env var `ENABLE_LLM_ENRICHMENT` (accepts `"true"`, `"1"`, `"yes"` — case-insensitive) when the CLI flag is not supplied. Default remains off.
- `web/api/services/news_service.py` gained `_load_enriched_summary_index(season, week)` + `_apply_enrichment(items, index)`. Both `get_news_feed` and `get_player_news` now call into these helpers after they finish assembling NewsItem dicts. When no sidecar exists, enrichment is a silent no-op — the feed renders exactly as it did before. When a sidecar is present, `NewsItem.summary` (reserved in Plan 61-05) is populated and `category` is replaced with `refined_category`. An info-level log line summarises `enrichment used=X (N items updated)` per request.
- When `week is None` (season-wide feed), the sidecar loader walks every `week=WW` subdirectory under `season=YYYY` and merges them all into a single lookup before applying.
- Regression: `python -m pytest tests/web/` → 15/15 passed; `tests/sentiment/test_daily_pipeline_resilience.py` → 7/7 still green; combined new + resilience + web suite → 28/28 passed.

## Enrichment Mode Matrix (D-04 behaviour table)

| `ENABLE_LLM_ENRICHMENT` | `ANTHROPIC_API_KEY` | Step 6.5 behaviour                                                                                 | Exit code |
| :---------------------- | :------------------ | :------------------------------------------------------------------------------------------------- | :-------- |
| `false` (default)       | unset               | Logged as `enabled=False, API key present=False`. StepResult OK, detail `"disabled (...)"`.        | 0         |
| `false` (default)       | set                 | Same as above — flag still off. SDK import never triggered.                                        | 0         |
| `true`                  | unset               | Enrichment module instantiated; `is_available=False` logs a warning; 0 records enriched, step OK.  | 0         |
| `true`                  | set                 | Enrichment runs for every Silver envelope; summary + refined_category added; sidecar files written. | 0         |
| `true`                  | set + SDK missing   | `_build_client` returns None (import fails), warning logged, 0 records enriched, step OK.           | 0         |
| `true`                  | set + API error     | Each `enrich()` fails open → record unchanged. Step remains OK. Batch continues.                    | 0         |

The pipeline exit code is NEVER affected by enrichment state — this is the D-06 guarantee that 61-04 established and this plan preserves.

## Auto-Mode Confirmation (D-02 lock)

`SentimentPipeline()` with `extractor_mode="auto"` (the default used everywhere in production including `scripts/daily_sentiment_pipeline.py`) now instantiates `RuleExtractor` regardless of whether `ANTHROPIC_API_KEY` is set. Log line on startup:

```
Using rule-based extractor in auto mode (Phase 61 D-02: rules are primary,
LLM is optional enrichment via src.sentiment.enrichment).
```

Previously that log line said `"Using Claude extractor (API key available)"` whenever the key happened to be set — a subtle correctness risk if the key ever reappeared in the environment. That path is gone from the default.

Explicit callers can still opt back in with `SentimentPipeline(extractor_mode="claude")`; this path is unchanged and is kept only for backward compatibility with the existing test suite.

## Cost Estimate

Target volume (per CONTEXT D-04): ~100 articles/day. Enrichment prompt + response:

- Prompt: title (~100 tokens) + body clamped to 1500 chars (~400 tokens) + instruction scaffolding (~100 tokens) ≈ **600 input tokens per article**.
- Response: JSON with summary (≤ 200 chars ~50 tokens) + category (1 token) ≈ **60 output tokens per article**.
- Claude Haiku 4.5 pricing (April 2026): ~$1/M input, ~$5/M output.
- Per day: 100 × (600 × $1/M + 60 × $5/M) = 100 × ($0.0006 + $0.0003) ≈ **$0.09/day**.
- **Monthly cost: ~$2.70** — well within the "$1–5/month" envelope called out in CONTEXT D-04.

Spikes to 500 articles/day would still run under $15/month. The 1500-char body clamp is the single biggest cost lever and can be tuned down if needed.

## Task Commits

| Task       | Commit   | Description                                                      |
| ---------- | -------- | ---------------------------------------------------------------- |
| 1 (RED)    | `88688f4` | `test(61-06): add failing tests for optional LLM enrichment module` |
| 1 (GREEN)  | `ec8ee43` | `feat(61-06): add optional LLMEnrichment module + demote ClaudeExtractor` |
| 2          | `85ef6a2` | `feat(61-06): wire optional LLM enrichment (Step 6.5) into daily cron + news service` |

## Files Created/Modified

### Created

- `src/sentiment/enrichment/__init__.py` — package entry with `LLMEnrichment` + `enrich_silver_records` exports.
- `src/sentiment/enrichment/llm_enrichment.py` — `LLMEnrichment` class (fail-open client build, `enrich(record)`, `_parse_response`) + batch driver `enrich_silver_records(season, week, dry_run)`. Module-level `_SILVER_SIGNALS_DIR` + `_SILVER_ENRICHED_DIR` constants are exposed for test monkeypatching.
- `tests/sentiment/test_llm_enrichment_optional.py` — 6 tests covering D-04 + D-06 contracts. Hermetic: monkeypatches `ANTHROPIC_API_KEY` + `_SILVER_*_DIR` constants + mocks the anthropic client — no real API calls, no real Silver files read.

### Modified

- `scripts/daily_sentiment_pipeline.py` — docstring lists Step 6.5, `_run_llm_enrichment` wrapper added, inserted into `run_pipeline()` between extraction and player aggregation, CLI flag wired (was a 61-04 no-op), `main()` resolves CLI → env var → `False`.
- `src/sentiment/processing/extractor.py` — class docstring gains a `DEPRECATED for model-facing extraction per Phase 61 D-02` block pointing callers at the new enrichment module. No behaviour change.
- `src/sentiment/processing/pipeline.py` — `_build_extractor("auto")` now returns `RuleExtractor()` unconditionally and logs a D-02 rationale line. `"claude"` mode still works for explicit callers.
- `web/api/services/news_service.py` — `_SILVER_ENRICHED_DIR` constant + `_find_enriched_files` + `_load_enriched_summary_index` + `_apply_enrichment` helpers + sidecar merge calls in `get_news_feed` and `get_player_news`.

## Decisions Made

See the `key-decisions` block in the frontmatter for the full list. Highlights:

- **Double-gated (flag AND key).** Either condition alone yields a clean no-op. Matches D-04 exactly.
- **Deferred anthropic SDK import.** Disabled pipelines never trigger the import; missing SDK causes `is_available=False` instead of a startup warning.
- **D-02 lock on auto-mode.** SentimentPipeline now always uses rules in auto-mode. Subtle but crucial — previously a stray `ANTHROPIC_API_KEY` would silently flip the model path to ClaudeExtractor.
- **Sidecar writes to `signals_enriched/`.** Original `signals/` tree is the authoritative model-facing record; the sidecar is display-only.

## Deviations from Plan

**None — plan executed exactly as written.** All 6 RED tests went green on the first GREEN commit. All done-criteria from the plan verified:

- `python -c "from src.sentiment.enrichment import LLMEnrichment; print(LLMEnrichment().is_available)"` → `is_available = False` (expected — no key in this env).
- `grep -n 'DEPRECATED' src/sentiment/processing/extractor.py` → line 200 match.
- `grep -n 'always use rules\|D-02' src/sentiment/processing/pipeline.py` → lines 147 + 153 match.
- `ENABLE_LLM_ENRICHMENT=false python scripts/daily_sentiment_pipeline.py --dry-run ...` → exit 0, "disabled (ENABLE_LLM_ENRICHMENT=false)" logged.
- `ENABLE_LLM_ENRICHMENT=true python scripts/daily_sentiment_pipeline.py --dry-run ...` (no key) → exit 0, "0 records enriched", warning logged.
- `grep -n "signals_enriched" web/api/services/news_service.py` → 2 matches (constant definition + sidecar path docstring).

No Rule 1/2/3 auto-fixes triggered; no Rule 4 architectural checkpoints.

## Issues Encountered

- **Black re-formatting round-trip.** After Task 1 GREEN, `python -m black src/sentiment/enrichment/ ...` reformatted two files (collapsed a two-line `"refined_category" not in out` assertion into one; collapsed a three-line `body = str(...)` statement). Tests still passed post-format. Non-issue.
- **DeprecationWarning for escape sequence.** Docstring contained backtick-escaped triple-backticks which black's rewriter flagged as an `\`` escape. Prefixed the docstring with `r"""` to silence the warning. Non-issue.

## Deferred Issues

None new. Inherited from prior plans:

- `ANTHROPIC_API_KEY` not set in Railway — explicitly the supported state per D-06. Flipping `ENABLE_LLM_ENRICHMENT=true` in the repo variable will cost 0 cents (step will run, log the warning, exit 0) until the key is also provisioned.
- 2025 roster data not fully ingested — unchanged by this plan.

## Known Stubs

None. Every field wired in this plan has a real implementation behind it:

- `NewsItem.summary` populates from the sidecar when available; falls to `None` (not a placeholder string) when absent.
- `refined_category` only overrides `category` when the sidecar exists; never coerced to a default value.

## Threat Flags

No new surface beyond the plan's `<threat_model>`:

- **T-61-06-01** (Information Disclosure via API key in logs) — **mitigated.** `_run_llm_enrichment` logs `bool(os.environ.get("ANTHROPIC_API_KEY"))` only; the value is never read into a format argument. Grep confirms no `%s.*ANTHROPIC_API_KEY` formatting anywhere.
- **T-61-06-02** (Tampering via prompt injection) — **mitigated.** `_parse_response` clamps `summary` to `_SUMMARY_MAX_CHARS=200` and validates `refined_category` against `_VALID_CATEGORIES`; unknown categories fall back to `"general"`. React rendering (Plan 61-05 components) already auto-escapes text content.
- **T-61-06-03** (DoS via Anthropic rate limits / API errors) — **mitigated.** Every exception path in `enrich()` returns the record unchanged; `_run_llm_enrichment` only marks itself failed if `enrich_silver_records` itself raises, which is belt-and-braces since the inner loop also fails open.
- **T-61-06-04** (Repudiation via silent enrichment drift) — **mitigated.** Every pipeline run logs the enrichment enabled/disabled state on one line at step start and the record count on the step completion line. `_apply_enrichment` logs used=bool + N per request.
- **T-61-06-05** (Elevation via LLM overwriting event flags) — **mitigated.** `enrich()` only adds `summary` + `refined_category`. The `events` dict is never read from the LLM response; test 4 pins this (`assert out["events"] == sample_silver_record["events"]`).

## User Setup Required

**None required for D-06 compliance.** The pipeline works in all four quadrants of the mode matrix above.

**Optional to activate enrichment** (all three must be true):

1. Set `ANTHROPIC_API_KEY` in Railway (and optionally locally for dev).
2. Set `ENABLE_LLM_ENRICHMENT=true` as a GitHub Actions repo variable (`Settings → Secrets and variables → Actions → Variables`). Plan 61-04 already wired the workflow to read this variable — no workflow edit required.
3. Wait for the next scheduled daily-sentiment cron run (`0 12 * * *` UTC) OR trigger a workflow_dispatch run manually.

Cost envelope under default scraping volume: **~$2.70/month** (see Cost Estimate section).

## Verification Evidence

Run from `/Users/georgesmith/repos/nfl_data_engineering/`, venv activated:

- `python -m pytest tests/sentiment/test_llm_enrichment_optional.py -v` → **6 passed** in 0.60s
- `python -m pytest tests/sentiment/` → **59 passed** in 139s (no regressions in the pre-existing 53 tests)
- `python -m pytest tests/web/` → **15 passed** in 1.22s (news router tests unaffected)
- `python -m pytest tests/sentiment/test_daily_pipeline_resilience.py tests/sentiment/test_llm_enrichment_optional.py tests/web/` → **28 passed** in 1.45s (combined suite)
- `ENABLE_LLM_ENRICHMENT=false python scripts/daily_sentiment_pipeline.py --dry-run --verbose --season 2025 --week 1 --skip-ingest` → **exit 0**, logs `LLM Enrichment: enabled=False, API key present=False` and `[  OK] LLM Enrichment   0.0s  disabled (ENABLE_LLM_ENRICHMENT=false)`.
- `ENABLE_LLM_ENRICHMENT=true python scripts/daily_sentiment_pipeline.py --dry-run --verbose --season 2025 --week 1 --skip-ingest` (no key) → **exit 0**, logs `LLM Enrichment: enabled=True, API key present=False` and `[  OK] LLM Enrichment   0.0s  0 records enriched` with the `LLMEnrichment: ANTHROPIC_API_KEY unset ...` warning.
- `grep -n "signals_enriched" web/api/services/news_service.py` → 2 matches (constant + docstring path).
- `grep -cE "ENABLE_LLM_ENRICHMENT|_run_llm_enrichment" scripts/daily_sentiment_pipeline.py` → 10 matches.
- `python -c "from src.sentiment.enrichment import LLMEnrichment, enrich_silver_records; print('imports OK')"` → **imports OK**.

## TDD Gate Compliance

This plan's Task 1 follows the RED/GREEN/REFACTOR cycle:

- **RED gate:** commit `88688f4` — `test(61-06): add failing tests for optional LLM enrichment module`. Tests imported `src.sentiment.enrichment` which did not exist; `pytest` failed at collection time with `ModuleNotFoundError`. Screenshot of failure captured in session log.
- **GREEN gate:** commit `ec8ee43` — `feat(61-06): add optional LLMEnrichment module + demote ClaudeExtractor`. All 6 tests passed on first run; black reformatting and a docstring raw-string fix followed without test regression.
- **REFACTOR gate:** not needed (no structural cleanup warranted).

## Next Phase Readiness

**Phase 61 is one plan away from closed.** 61-06 completes the D-02/D-04/D-06 architecture:

- Source expansion (61-01): 5 sources ingested, web-scraper-agent-friendly shape.
- Rule extractor expansion (61-02): 12 event flags, deterministic, production-path.
- Event-based projection adjustment (61-03): NOT in this plan — still the outstanding item before Phase 61 closes.
- Daily cron resilience (61-04): D-06 guarantee, 8-step pipeline, health-summary annotations.
- News UI (61-05): 32-team event density grid, player badges, NewsItem.summary reserved.
- **Optional Haiku enrichment (61-06, this plan): shipped.**

**To flip enrichment ON in production:** set `ENABLE_LLM_ENRICHMENT=true` as a repo variable + provision `ANTHROPIC_API_KEY` in Railway. No code change required; the next scheduled cron picks up both immediately. Website NewsPanel cards will start showing the 1-sentence summary on the first request after the cron writes its first sidecar.

**Ship gate criterion for flipping the flag:** live dry-run produces a sample sidecar with ≥ 10 non-empty `summary` values whose rendered length on the news card fits in the 200-char layout. Cost-tracking dashboard (Railway + Anthropic Console) should show ≤ $5/month after 7 days.

## Self-Check: PASSED

- FOUND: src/sentiment/enrichment/__init__.py
- FOUND: src/sentiment/enrichment/llm_enrichment.py
- FOUND: tests/sentiment/test_llm_enrichment_optional.py
- FOUND: .planning/phases/61-news-sentiment-live/61-06-SUMMARY.md
- FOUND: commit 88688f4 (test 61-06 RED)
- FOUND: commit ec8ee43 (feat 61-06 GREEN)
- FOUND: commit 85ef6a2 (feat 61-06 pipeline wiring + news service)
- FOUND: DEPRECATED annotation in src/sentiment/processing/extractor.py (line 200)
- FOUND: D-02 rationale log line in src/sentiment/processing/pipeline.py (lines 147 + 153)
- FOUND: `signals_enriched` references in web/api/services/news_service.py (2 matches)
- FOUND: ENABLE_LLM_ENRICHMENT + _run_llm_enrichment references in scripts/daily_sentiment_pipeline.py (10 matches)

---
*Phase: 61-news-sentiment-live*
*Completed: 2026-04-19*
