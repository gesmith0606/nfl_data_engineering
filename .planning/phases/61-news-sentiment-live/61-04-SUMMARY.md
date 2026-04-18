---
phase: 61-news-sentiment-live
plan: 04
subsystem: ops-orchestration
tags: [cron, github-actions, sentiment, resilience, d-06, d-04, rule-first]

# Dependency graph
requires:
  - file: "scripts/daily_sentiment_pipeline.py"
    provides: "Existing orchestrator with 3 source steps + extraction + aggregation (shipped pre-61-04)"
  - file: "scripts/ingest_sentiment_rotowire.py"
    provides: "main(argv) RSS ingestor with --season/--dry-run/--verbose (shipped in 61-01)"
  - file: "scripts/ingest_sentiment_pft.py"
    provides: "main(argv) RSS ingestor for Pro Football Talk (shipped in 61-01)"
  - file: "src/sentiment/processing/pipeline.py::SentimentPipeline"
    provides: "extractor auto-fallback (Claude if available, else RuleExtractor)"
  - file: "src/sentiment/processing/rule_extractor.py::RuleExtractor"
    provides: "Rule-first extractor — D-06 authoritative path for model signals"
provides:
  - "scripts/daily_sentiment_pipeline.py: 5-source orchestrator with enable_llm_enrichment flag reserved for 61-06"
  - ".github/workflows/daily-sentiment.yml: cron hardened for D-06 + D-04 feature flag"
  - "tests/sentiment/test_daily_pipeline_resilience.py: 7 regression tests covering rule-first + isolation contract"
affects:
  - "Plan 61-05 news page UI now has +2 sources (RotoWire + PFT) of real articles to display"
  - "Plan 61-06 can wire ENABLE_LLM_ENRICHMENT to the new enable_llm_enrichment arg without workflow changes"
  - "Daily cron next scheduled run (12:00 UTC) will ingest all 5 free sources and commit new Bronze files"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "StepResult wrapper pattern: try/except around sub-script main(), capture exit code, surface via StepResult"
    - "D-06 isolation: every ingestion wrapper catches Exception and logs 'non-fatal, D-06' warning; pipeline continues"
    - "Rule-first log discriminator: isinstance(pipeline.extractor, RuleExtractor) identifies the D-06 path explicitly in stdout"
    - "GitHub Actions feature flag pattern: vars.ENABLE_LLM_ENRICHMENT || 'false' makes toggle a non-secret repo variable"
    - "Health summary emits ::notice:: annotations (non-secret only) so reviewers can see which path was authoritative"
    - "CLI parameter: reserved --enable-llm-enrichment no-op flag documents the D-04 boundary without shipping wiring"

key-files:
  created:
    - "tests/sentiment/test_daily_pipeline_resilience.py"
    - ".planning/phases/61-news-sentiment-live/61-04-SUMMARY.md"
  modified:
    - "scripts/daily_sentiment_pipeline.py"
    - ".github/workflows/daily-sentiment.yml"

key-decisions:
  - "Rule-first log line uses isinstance(extractor, RuleExtractor) rather than 'not extractor.is_available'.  RuleExtractor.is_available is always True (it has no external dependency), so the original check in the pre-61-04 code would never fire; the type check is the only way to reliably identify the D-06 path"
  - "enable_llm_enrichment is a CLI + run_pipeline parameter today but is a pure no-op (logs once when True).  Wiring lives in plan 61-06 so the Haiku enrichment step can land behind the same flag without another workflow edit"
  - "Step labels renumbered from 1/6..6/6 to 1/8..8/8 to signal the expanded surface area in stdout logs — ops visibility over backward compatibility"
  - "Health summary step uses if: always() so the ::notice:: annotations fire even when the pipeline exits non-zero — makes every run auditable at a glance"
  - "Per-wrapper logger.warning (not logger.error) for D-06 graceful-failure path.  Keeps failure notifications surfaced but signals this is expected resilience behaviour rather than a genuine error"

patterns-established:
  - "Adding a new free source to the daily cron = 1 new wrapper function (~30 lines) + 1 skip flag + 1 step insertion in run_pipeline.  No workflow change needed once this plan ships."

requirements-completed: [NEWS-01]

# Metrics
duration: 27min
completed: 2026-04-18
---

# Phase 61 Plan 04: Daily Cron Resilience & D-06 Guarantee Summary

**Wired RotoWire + PFT ingestion into the daily sentiment cron and cemented the D-06 guarantee: the pipeline always runs rule-based extraction regardless of ANTHROPIC_API_KEY, per-source failures are isolated, and ENABLE_LLM_ENRICHMENT defaults to false at the GHA boundary for plan 61-06 to flip later.**

## Performance

- **Duration:** ~27 min (1 TDD cycle + 1 workflow hardening + SUMMARY)
- **Started:** 2026-04-18T14:56:34Z
- **Completed:** 2026-04-18T15:23:43Z
- **Tasks:** 2 (both shipped, all 7 tests green)
- **Files created:** 2 (1 test file + this SUMMARY)
- **Files modified:** 2 (`scripts/daily_sentiment_pipeline.py`, `.github/workflows/daily-sentiment.yml`)

## The 8 Pipeline Steps As-Shipped

| # | Step                | Module                                        | Skip flag            | D-06 status                    |
| - | ------------------- | --------------------------------------------- | -------------------- | ------------------------------ |
| 1 | RSS Ingestion       | `scripts/ingest_sentiment_rss.py`             | `--skip-rss`         | try/except → warning + continue |
| 2 | Reddit Ingestion    | `scripts/ingest_sentiment_reddit.py`          | `--skip-reddit`      | try/except → warning + continue |
| 3 | Sleeper Ingestion   | `scripts/ingest_sentiment_sleeper.py`         | `--skip-sleeper`     | try/except → warning + continue |
| 4 | RotoWire Ingestion  | `scripts/ingest_sentiment_rotowire.py` (NEW)  | `--skip-rotowire`    | try/except → warning + continue |
| 5 | PFT Ingestion       | `scripts/ingest_sentiment_pft.py` (NEW)       | `--skip-pft`         | try/except → warning + continue |
| 6 | Signal Extraction   | `src.sentiment.processing.pipeline`           | (always runs)        | RuleExtractor ALWAYS available |
| 7 | Player Aggregation  | `src.sentiment.aggregation.weekly`            | (always runs)        | Operates on whatever Silver exists |
| 8 | Team Aggregation    | `src.sentiment.aggregation.team_weekly`       | (always runs)        | Operates on whatever Gold exists |

## Accomplishments

### Task 1 — RotoWire + PFT steps added to orchestrator (SHIPPED)

- Added `_run_rotowire_ingestion(season, dry_run, verbose)` and `_run_pft_ingestion(season, dry_run, verbose)` wrappers that mirror `_run_reddit_ingestion` verbatim. Each imports its sub-script's `main`, builds argv, captures return code into a `StepResult`, and converts any raised exception into a `success=False` result with a `(non-fatal, D-06)` warning log.
- Extended `run_pipeline(...)` signature with three new parameters: `skip_rotowire`, `skip_pft`, `enable_llm_enrichment` (all default `False`). The latter is a no-op placeholder reserved for plan 61-06 wiring; when `True` it logs "reserved for 61-06; no-op today" once at pipeline start.
- Inserted the new steps between Sleeper (step 3/8) and Signal Extraction (step 6/8). Step labels rebranded from `1/6..6/6` to `1/8..8/8` for accurate ops visibility.
- CLI: added `--skip-rotowire`, `--skip-pft`, `--enable-llm-enrichment` argparse flags wired through `main()` to `run_pipeline(...)`.
- Signal Extraction step now logs the D-06 rule-first path explicitly: `Event-only path: ANTHROPIC_API_KEY unset, using RuleExtractor (rule-first per D-06)` when `isinstance(pipeline.extractor, RuleExtractor)`. It also embeds the extractor class name in `StepResult.detail` so the summary table shows `[extractor=RuleExtractor]` vs `[extractor=ClaudeExtractor]` for post-hoc log diffing.
- 7 regression tests in `tests/sentiment/test_daily_pipeline_resilience.py`: extraction runs without API key, single-source failure isolation, `skip_rotowire`, `skip_pft`, `any_success` semantics, `skip_ingest` downstream-only, and step-list contains RotoWire + PFT by default.

### Task 2 — .github/workflows/daily-sentiment.yml hardened for D-06 + D-04 (SHIPPED)

- Replaced the 3-line "API key is optional" comment with an 8-line D-06 / D-04 block that names the guarantee (pipeline NEVER fails because this key is missing), references the phase CONTEXT, and explains the enrichment toggle.
- Added `ENABLE_LLM_ENRICHMENT: ${{ vars.ENABLE_LLM_ENRICHMENT || 'false' }}` to the pipeline step's `env:` block. It reads from a GitHub repo variable (`Settings → Secrets and variables → Actions → Variables`), defaults to `'false'`, and can be flipped to `'true'` without a workflow edit once plan 61-06 ships.
- Added a new `Log pipeline health summary` step with `if: always()` that emits two GitHub Actions `::notice::` annotations: one confirming the rule-first path is authoritative, and one echoing only the non-secret `ENABLE_LLM_ENRICHMENT` value. The step never touches `ANTHROPIC_API_KEY` (T-61-04-01 mitigation).
- Added an inline comment block documenting the 5 sources ingested by the orchestrator with their corresponding `--skip` flags. No logic change — makes the workflow self-documenting for ops readers.
- Preserved everything else: cron schedule (`0 12 * * *`), concurrency group, Python setup, AWS credentials block, the refresh_rosters step (still non-fatal), the commit-and-push step (existing glob already covers `data/bronze/sentiment/` so RotoWire + PFT subdirs are picked up automatically), the artifact upload, and the `notify-failure` job.

## Task Commits

1. **Task 1 RED:** `ff8ec21` — `test(61-04): add failing resilience tests for daily sentiment pipeline`
2. **Task 1 GREEN:** `c1b5bd6` — `feat(61-04): add RotoWire + PFT steps to daily sentiment pipeline`
3. **Task 2:** `e096860` — `ci(61-04): harden daily-sentiment.yml for D-06 + D-04 feature flag`

## Files Created/Modified

### Created

- `tests/sentiment/test_daily_pipeline_resilience.py` (+421 lines after black) — 7 regression tests with an `autouse` fixture that monkeypatches the extraction + aggregation modules to lightweight no-ops so no disk/resolver work runs during the resilience suite. Runs in ~0.6 seconds.

### Modified

- `scripts/daily_sentiment_pipeline.py` (+261 / -92 lines after black) — added two wrappers, extended signature with three new parameters, rebranded step labels to 8/8, added rule-first log discriminator, exposed extractor type in `StepResult.detail`. Docstring at the top lists all 8 steps and cites D-06.
- `.github/workflows/daily-sentiment.yml` (+33 / -2 lines) — D-06/D-04 comment block, `ENABLE_LLM_ENRICHMENT` env var, health-summary step with `if: always()`, source list comment.

## Mock Dry-Run Log (Excerpt)

Captured from `ANTHROPIC_API_KEY= python scripts/daily_sentiment_pipeline.py --dry-run --verbose --season 2025 --week 1`:

```
============================================================
Daily Sentiment Pipeline | season=2025 week=1 | dry_run=True
============================================================
--- Step 1/8: RSS Ingestion ---                              [OK  36.4s]
--- Step 2/8: Reddit Ingestion ---                           [OK  47.7s]
--- Step 3/8: Sleeper Ingestion ---                          [OK  34.5s]
--- Step 4/8: RotoWire Ingestion ---                         [OK  35.1s]
--- Step 5/8: PFT Ingestion ---                              [OK  35.3s]
--- Step 6/8: Signal Extraction ---
INFO: Event-only path: ANTHROPIC_API_KEY unset, using RuleExtractor (rule-first per D-06)
                                                             [OK  33.2s]
--- Step 7/8: Player Aggregation ---                         [OK   0.0s]
--- Step 8/8: Team Aggregation ---                           [OK   0.0s]
============================================================
PIPELINE SUMMARY (DRY RUN)
============================================================
  [  OK] RSS Ingestion          36.4s  completed
  [  OK] Reddit Ingestion       47.7s  completed
  [  OK] Sleeper Ingestion      34.5s  completed
  [  OK] RotoWire Ingestion     35.1s  completed
  [  OK] PFT Ingestion          35.3s  completed
  [  OK] Signal Extraction      33.2s  46 processed, 619 skipped, 0 signals [extractor=RuleExtractor]
  [  OK] Player Aggregation      0.0s  30 players
  [  OK] Team Aggregation        0.0s  0 teams
Result: 8/8 steps succeeded
```

The `[extractor=RuleExtractor]` suffix and the preceding D-06 log line are both captured in GHA stdout on every run where the API key is absent — making the rule-first takeover trivially visible to any reviewer scanning the run log.

## D-04 Feature Flag: Confirmation of Default

The repo variable `ENABLE_LLM_ENRICHMENT` is NOT set in this repository. The GitHub Actions expression `${{ vars.ENABLE_LLM_ENRICHMENT || 'false' }}` therefore evaluates to the literal string `'false'` at workflow parse time, which becomes the value of the `ENABLE_LLM_ENRICHMENT` environment variable in the pipeline step. The `Log pipeline health summary` step will emit the annotation `::notice::LLM enrichment: false` on the next scheduled run.

To flip the flag when plan 61-06 ships:

1. Navigate to `Settings → Secrets and variables → Actions → Variables` in the repo.
2. Click `New repository variable`.
3. Name: `ENABLE_LLM_ENRICHMENT`, value: `true`.
4. No workflow edit or redeploy required — the expression picks up the new value on the next scheduled or manual run.

## Decisions Made

See the `key-decisions` block in the frontmatter for the full list. Summary:

- **Rule-first log line uses isinstance(...) not is_available check.** `RuleExtractor.is_available` returns `True` unconditionally (rules have no external dependency), so the original pre-61-04 check `if not pipeline.extractor.is_available` would never fire. The `isinstance(pipeline.extractor, RuleExtractor)` check is the only reliable way to identify the D-06 path at log time.
- **enable_llm_enrichment is a no-op placeholder today.** The wiring lives in plan 61-06 so the Haiku enrichment sub-step can land behind the same flag without another workflow edit.
- **Step labels renumbered 1/6..6/6 → 1/8..8/8.** Accurate stdout ops visibility is worth the log-grep breakage for anyone scraping the previous format.
- **logger.warning (not logger.error) for D-06 graceful-failure path.** Signals "expected resilience behaviour" rather than "genuine error" — keeps alerting thresholds calibrated for real failures.
- **Health summary uses if: always().** Ensures the `::notice::` annotations fire even on partial failures, making every run auditable at a glance.

## Deviations from Plan

**None.** Plan executed exactly as written. All 7 RED tests went green on the first GREEN commit (after black formatting); no Rule 1/2/3 deviations triggered; no Rule 4 architectural checkpoints reached. The plan's verification commands all pass:

- `python -m pytest tests/sentiment/test_daily_pipeline_resilience.py -v` → 7 passed, 0 failed (0.61 s)
- `python scripts/daily_sentiment_pipeline.py --dry-run --verbose` → exit 0, 8/8 steps OK
- `grep -n "rotowire\|pft\|D-06" scripts/daily_sentiment_pipeline.py` → 23 matches
- `python -c "import yaml; y=yaml.safe_load(open('.github/workflows/daily-sentiment.yml')); assert 'ENABLE_LLM_ENRICHMENT' in str(y); print('OK')"` → OK
- `grep -c "D-06\|D-04" .github/workflows/daily-sentiment.yml` → 3 (≥2 required)
- `grep -cE "rotowire|pft|DynastyFF|skip" .github/workflows/daily-sentiment.yml` → 5

## Issues Encountered

- **Black reformatting round-trip.** After the GREEN commit, `python -m black scripts/daily_sentiment_pipeline.py tests/sentiment/test_daily_pipeline_resilience.py` collapsed `patch.object(...)` chains to black's preferred multi-line style. Tests still passed post-format. Committed together with the GREEN feat commit. Non-issue.
- **Dry-run wall-clock ~4 min.** The live dry-run takes ~4 minutes because each sub-script's `main()` still boots `PlayerNameResolver` (14,524-player index) even with `--dry-run`. Known from 61-01; tests mock the sub-scripts entirely so the resilience suite itself runs in 0.6 s. Documented here for ops budgeting in the daily cron (cron should finish well under the 6-hour GitHub Actions job limit even accounting for extraction work on real Bronze data).

## Deferred Issues

None new. Pre-existing items outside this plan's scope:

- 2025 roster data not yet ingested (resolver cannot map 2025 rookies). Tracked in MEMORY.md blockers list.
- `ANTHROPIC_API_KEY` not set in Railway/GitHub Secrets — that is now explicitly the supported state per D-06; no action required.

## Known Stubs

- `enable_llm_enrichment` CLI flag and `run_pipeline` parameter are shipped as no-ops today. They log "reserved for 61-06; no-op today" when `True`. This is intentional per the plan's `<interfaces>` block and D-04; plan 61-06 will wire the flag to the Haiku enrichment sub-step without requiring another workflow edit.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`:

- **T-61-04-01** (Information Disclosure via GHA log) — **mitigated.** The `Log pipeline health summary` step only echoes `ENABLE_LLM_ENRICHMENT` (non-secret toggle) and a static message. It never references `ANTHROPIC_API_KEY` by name or value.
- **T-61-04-02** (Denial of Service from upstream RSS) — **mitigated.** Every `_run_*_ingestion` wrapper catches `Exception` and continues. The 7-test resilience suite pins this contract.
- **T-61-04-03** (Tampering via bot-pushed commits) — **accept.** Commits remain scoped to `data/bronze/sentiment/**`, `data/silver/sentiment/**`, `data/gold/sentiment/**`, `data/gold/projections/**`. Existing commit-step glob unchanged.
- **T-61-04-04** (Repudiation via silent LLM fallback) — **mitigated.** The rule-first log line fires explicitly when RuleExtractor is used, and the extractor class name is embedded in the `StepResult.detail` summary line.

## User Setup Required

**None required for D-06 compliance.** The pipeline now runs correctly in both configurations:

- **ANTHROPIC_API_KEY unset (current state):** rule-first path takes over, logs the D-06 line, exit 0.
- **ANTHROPIC_API_KEY set:** Claude extractor boots for sentiment extraction; rule-first log does NOT fire; extraction still succeeds.

**Optional for plan 61-06 future work:**

1. Set `ENABLE_LLM_ENRICHMENT=true` as a repo variable (`Settings → Secrets and variables → Actions → Variables`) to opt into website enrichment once plan 61-06 ships.

## Verification Evidence

Run from `/Users/georgesmith/repos/nfl_data_engineering/`, venv activated:

- `python -m pytest tests/sentiment/test_daily_pipeline_resilience.py -v` → **7 passed, 0 failed** in 0.61 s
- `ANTHROPIC_API_KEY= python scripts/daily_sentiment_pipeline.py --dry-run --verbose --season 2025 --week 1` → **exit 0, 8/8 steps OK, extractor=RuleExtractor**
- `env -u ANTHROPIC_API_KEY python -c "from scripts.daily_sentiment_pipeline import _run_extraction; r=_run_extraction(2025,1,True,True); print(r.success, r.detail)"` → **True, 46 processed, 619 skipped, 0 signals [extractor=RuleExtractor]**, and the D-06 log line `Event-only path: ANTHROPIC_API_KEY unset, using RuleExtractor (rule-first per D-06)` was captured in INFO-level logs.
- `python -c "import yaml; y=yaml.safe_load(open('.github/workflows/daily-sentiment.yml')); assert 'ENABLE_LLM_ENRICHMENT' in str(y); print('YAML_OK')"` → **YAML_OK**
- `grep -c "D-06\|D-04" .github/workflows/daily-sentiment.yml` → **3**
- `grep -cE "rotowire|pft|DynastyFF|skip" .github/workflows/daily-sentiment.yml` → **5**
- `wc -l tests/sentiment/test_daily_pipeline_resilience.py` → **421** (plan's `min_lines: 120` satisfied)

## Next Phase Readiness

- **Plan 61-05** (news page UI) now has +2 Bronze sources to display (`data/bronze/sentiment/rotowire/` and `data/bronze/sentiment/pft/`). The daily cron's next scheduled run (`0 12 * * *` UTC) will commit the first RotoWire + PFT envelopes back to `main`; Railway + Vercel auto-deploy from `main` so the news page picks them up immediately.
- **Plan 61-06** (optional Haiku enrichment) can:
  1. Add the enrichment sub-step inside `scripts/daily_sentiment_pipeline.py` behind `if enable_llm_enrichment:` (flag already exists).
  2. Read `ENABLE_LLM_ENRICHMENT` from the sub-script's environment (GHA already exports it).
  3. Flip the repo variable to `true` when ready — no workflow edit required.
- **Daily cron ship gate:** the next `0 12 * * *` UTC scheduled run will exercise the full 8-step pipeline end-to-end on live data. Expected outcome: 8/8 steps succeed, `::notice::` annotations log `LLM enrichment: false` and `Rule-first path is authoritative (D-06)`, and a follow-up `data(daily): sentiment + roster refresh` commit lands on `main`.

## Self-Check: PASSED

- FOUND: scripts/daily_sentiment_pipeline.py (modified — 5 sources wired, D-06 log line, enable_llm_enrichment flag)
- FOUND: .github/workflows/daily-sentiment.yml (modified — D-06 comment, ENABLE_LLM_ENRICHMENT env, health summary)
- FOUND: tests/sentiment/test_daily_pipeline_resilience.py (created — 421 lines, 7 tests all passing)
- FOUND: commit ff8ec21 (test 61-04 RED)
- FOUND: commit c1b5bd6 (feat 61-04 GREEN)
- FOUND: commit e096860 (ci 61-04 workflow hardening)
- FOUND: 3 occurrences of "D-06|D-04" in workflow (≥2 required)
- FOUND: 5 occurrences of "rotowire|pft|DynastyFF|skip" in workflow
- FOUND: "rotowire", "pft", "D-06" all present in daily_sentiment_pipeline.py
- FOUND: `extractor=RuleExtractor` in StepResult.detail when API key absent
- FOUND: `Event-only path: ... rule-first per D-06` log line in direct _run_extraction invocation

---
*Phase: 61-news-sentiment-live*
*Completed: 2026-04-18*
