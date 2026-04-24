# Phase 71: LLM-Primary Extraction - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Convert `src/sentiment/processing/extractor.py` from a deprecated/legacy single-doc enrichment helper into a first-class **Claude-primary** extraction path that produces structured `{player_name, event_type, sentiment_score, summary, event_flags}` signals from raw Bronze docs. RuleExtractor remains the deterministic fallback (zero-cost, dev-mode, API-outage). Phase 71 ships the producer; Phase 72 expands the event-flag vocabulary on top of it.

</domain>

<decisions>
## Implementation Decisions

### Routing & Mode Naming

- New `extractor_mode = "claude_primary"` added to `SentimentPipeline._build_extractor()`. Existing `"auto"` (rule), `"rule"`, `"claude"` (legacy single-doc) values preserved.
- Per-doc soft fallback: when the Claude call raises or returns malformed JSON, the pipeline catches the error, increments a `claude_failed_count` metric on `PipelineResult`, and falls back to `RuleExtractor` for that single doc. Batches never hard-fail (matches Phase 61 D-06 fail-open contract).
- `ENABLE_LLM_ENRICHMENT` env var is reused (already wired on Railway + GHA) to gate the new mode; no new env var introduced. Module docstring documents the expanded meaning ("controls extraction primacy, not just sidecar enrichment").
- Mode selection: both `--extractor-mode claude_primary` on `scripts/process_sentiment.py` and `EXTRACTOR_MODE` env var read by `SentimentPipeline()` default. CLI arg wins when both are set. `daily-sentiment.yml` GHA workflow gets `EXTRACTOR_MODE=claude_primary` env when `ENABLE_LLM_ENRICHMENT=true`.

### Prompt Design & Batching

- Prompts are batched 5–10 docs per Claude call (configurable via `BATCH_SIZE` constant; default 8). Hits LLM-04 cost gate (<$5/week at 80 docs/day daily cron).
- The canonical active-roster player list (resolved from latest `data/bronze/players/rosters/season=YYYY/week=WW/`) is injected at the top of every prompt with `cache_control: {"type": "ephemeral"}` so it is cached across all docs in a week. Fallback to no-list mode if rosters file is missing (logged warning).
- Output schema EXTENDED, not replaced: each item gains `summary` (≤ 200 chars, 1 sentence) and `source_excerpt` (≤ 500 chars). Existing `{player_name, sentiment, confidence, category, events}` keys preserved exactly. Phase 72 will add new keys to `events` dict (no schema-break for Phase 71).
- Non-player items: Claude is allowed to return objects with `player_name: null` and a new `team_abbr` field. Phase 71 captures these into a new `non_player_items: List[Dict]` list on `PipelineResult` and logs them under `data/silver/sentiment/non_player_pending/`. Phase 72 (EVT-02) decides downstream routing.

### Cost, Budgets & Deterministic Testing

- Per-call cost tracking: tokens-in × tokens-out × Haiku 4.5 rate, written to `data/ops/llm_costs/season=YYYY/week=WW/llm_costs_TIMESTAMP.parquet` with columns `{call_id, doc_count, input_tokens, output_tokens, cached_tokens, cost_usd, ts}`. Per-run total is logged at INFO; if running total > $5/week a WARNING is emitted (no hard halt — daily cron must never be killed; overspending by $2 beats missing a day).
- Test fixtures: VCR-style recorded Claude JSON arrays under `tests/fixtures/claude_responses/{name}.json`. A `FakeClaudeClient` in `tests/sentiment/fakes.py` replays them keyed by SHA-256(prompt). Tests inject the fake client via constructor DI (no monkeypatching `_build_client`). Zero live API calls in CI per LLM-05.
- Benchmark for LLM-03: a new `tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason` runs both extractors on the recorded 2025 W17+W18 Bronze fixture batch (≥ 30 docs) and asserts `signals_claude / max(signals_rule, 1) ≥ 5.0`. Counts are written to `71-SUMMARY.md` on phase completion.
- Model: stay on `claude-haiku-4-5` (`_CLAUDE_MODEL` constant). Easy flip later if LLM-03 misses by > 20%.

### Downstream Integration

- `PlayerNameResolver` is unchanged in Phase 71. When `resolve()` returns null for a Claude-extracted name, the pipeline increments a `unresolved_player_count` metric on `PipelineResult` and writes the unresolved record under `data/silver/sentiment/unresolved_names/` for human review. Phase 72 will design the proper attribution.
- `LLMEnrichment` (`src/sentiment/enrichment/llm_enrichment.py`) becomes a no-op when the active extractor is `claude_primary`. Implementation: pipeline sets `is_claude_primary` bool on `PipelineResult` and the `enrich_silver_records()` orchestrator early-returns when it sees that flag. Module is preserved (still works in `auto` / `rule` modes).
- Silver schema gains an optional `extractor` field per signal record: `"rule" | "claude_primary" | "claude_legacy"`. Default `"rule"` for back-compat with prior runs. Non-breaking. PlayerSignal dataclass also gets the matching field.
- Bronze schema is untouched. All processing state stays in `data/silver/sentiment/processed_ids.json` and the Silver output. Bronze immutability preserved.

### Claude's Discretion

- Prompt wording for the batched extraction: free-form within the cache-friendly structure (static prefix → cached player list → cached preamble → per-doc body block).
- Concrete batch size within 5–10: pick what keeps p99 latency under 8 seconds; default 8.
- Choice of unit-test scaffolding (pytest fixtures vs class-based) within project conventions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/sentiment/processing/extractor.py` — current `ClaudeExtractor`, `PlayerSignal` dataclass, `EXTRACTION_PROMPT`. Single-doc, deprecated for model path. Will be promoted/refactored.
- `src/sentiment/processing/rule_extractor.py` — deterministic fallback path, must keep behavior identical.
- `src/sentiment/processing/pipeline.py` — `SentimentPipeline._build_extractor()` is the routing seam (lines 128-160). New `claude_primary` branch slots in alongside existing `"auto" | "rule" | "claude"`.
- `src/sentiment/enrichment/llm_enrichment.py` — `LLMEnrichment` class, `_VALID_CATEGORIES`, prompt template — pattern for env-key/SDK-import safety. Re-use the fail-open `_build_client()` shape.
- `src/player_name_resolver.py` — `PlayerNameResolver` already wired into pipeline; no change needed.
- `data/bronze/players/rosters/season=2026/week=*/` — newly committed (2026-04-24). Source for the cached player list.
- `scripts/process_sentiment.py` — existing CLI; extend with `--extractor-mode` arg.
- `.github/workflows/daily-sentiment.yml` — daily cron; will get `EXTRACTOR_MODE=claude_primary` env.

### Established Patterns
- Module-level constants for tunables (e.g., `_CLAUDE_MODEL`, `_MAX_TOKENS`, `_VALID_CATEGORIES`); pattern preserved.
- Fail-open env+SDK guard in `_build_client()` (returns `None`, logs warning). Reuse identical shape for new batched client.
- Dataclasses for results (`PipelineResult`, `PlayerSignal`); add new fields, never remove or rename.
- pytest fixtures for hermetic file-tree tests; monkeypatched `_PROJECT_ROOT` constants. Mirror this for cost-log Parquet writes.
- D-06 graceful failure on every ingestor — applied to extractor too: never raise from `extract_batch()`.

### Integration Points
- `SentimentPipeline.__init__()` — new `extractor_mode="claude_primary"` accepted.
- `SentimentPipeline.run()` — emits new metrics: `claude_failed_count`, `unresolved_player_count`, `non_player_count`, `is_claude_primary`.
- `enrich_silver_records()` — short-circuits when `is_claude_primary` true.
- New Parquet sink: `data/ops/llm_costs/season=YYYY/week=WW/`.
- New JSON sinks: `data/silver/sentiment/non_player_pending/`, `data/silver/sentiment/unresolved_names/`.

</code_context>

<specifics>
## Specific Ideas

- Use Anthropic prompt-caching: structure each batched call as `[cached_system_prefix, cached_player_list, per_doc_user_block]` with `cache_control` markers on the first two elements. First-week cost will be higher; subsequent weeks pay only the per-doc tokens.
- Cost log columns mirror Anthropic Messages API response fields directly (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) so future dashboarding is trivial.
- The benchmark test acts as both LLM-03 verifier and a regression guard for prompt drift.
- `--extractor-mode` is also accepted as `--mode` short alias on the CLI (matches existing `process_sentiment.py` arg conventions).

</specifics>

<deferred>
## Deferred Ideas

- Sonnet/Opus upgrade — only if Haiku misses LLM-03 gate by > 20%; revisit data in Phase 72.
- Dynamic prompt-caching of historical signal context (last 7 days of player events) — could improve coherence but adds storage churn; defer until Phase 72 needs it for event-flag deduplication.
- Streaming responses — unnecessary for batch processing; revisit if latency becomes user-facing.
- Per-source prompts (RSS vs Sleeper vs Reddit have different conventions) — start with one prompt; specialize only if LLM-03 reveals systematic source bias.
- Multi-user / per-league personalization at extraction layer — out of scope; user customization belongs in Phase 74.

</deferred>
