---
phase: 63-ai-advisor-hardening
plan: 01
subsystem: api
tags: [advisor, audit, httpx, fastapi, railway, probe]

# Dependency graph
requires:
  - phase: 62-advisor-mvp
    provides: Initial FastAPI backend + 12 advisor tools in web/frontend/src/app/api/chat/route.ts
provides:
  - Baseline TOOL-AUDIT.md table (PASS/WARN/FAIL + failure category) for all 12 advisor tools
  - Re-runnable `scripts/audit_advisor_tools.py` probe (deterministic, idempotent)
  - Precise root-cause catalogue for 63-02/03/04 fix work
affects: [63-02-schema-fixes, 63-03-missing-routes, 63-04-data-gaps, 63-05-ship-gate]

# Tech tracking
tech-stack:
  added: [httpx (transitive via anthropic==0.92.0, no new requirements.txt entry)]
  patterns:
    - "Frozen-dataclass TOOL_REGISTRY with per-tool validators"
    - "Category-based failure classification (7 buckets) for targeted remediation"
    - "warn_on_empty flag for off-season-tolerant tools"

key-files:
  created:
    - scripts/audit_advisor_tools.py
    - .planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.md
  modified: []

key-decisions:
  - "httpx over requests — already in env via anthropic, supports async + sync clients, first-class timeout semantics"
  - "TOOL_REGISTRY is a plain ast.Assign (no type annotation) so the plan's AST verification can find it"
  - "warn_on_empty flag separates off-season empties from genuine bugs — keeps the SHIP gate meaningful"
  - "compareExternalRankings empty → FAIL (not WARN) because it signals the external source is unreachable, not off-season"

patterns-established:
  - "Probe-and-categorize: transport error → BACKEND_DOWN, 4xx/5xx → HTTP_ERROR, schema issue → SCHEMA_MISMATCH, empty payload → EMPTY_PAYLOAD (demoted to WARN when warn_on_empty)"
  - "Markdown audit report has: metadata block, status table, failure-detail section, warning-detail section, raw stdout block"

requirements-completed: [ADVR-01]

# Metrics
duration: 4min
completed: 2026-04-18
---

# Phase 63 Plan 01: AI Advisor Tool Audit Baseline Summary

**Deterministic httpx probe of all 12 advisor tools against live Railway produced `TOOL-AUDIT.md` with 4 PASS / 3 WARN / 5 FAIL — five precise root causes now available for wave-2 targeting.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-18T00:36:55Z
- **Completed:** 2026-04-18T00:40:14Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- `scripts/audit_advisor_tools.py` implements a single-file probe for all 12 advisor tools with per-tool validators, failure categorization, and a markdown writer
- `TOOL-AUDIT.md` baseline written against `https://nfldataengineering-production.up.railway.app` — no auth header (Railway API_KEY not required in current env)
- Five distinct failure modes identified, each tied to a specific tool → wave 2 fix scope is now measurable, not speculative

## Baseline Counts

- **PASS (4):** `getPlayerProjection`, `compareStartSit`, `searchPlayers`, `getPositionRankings`
- **WARN (3):** `getNewsFeed`, `getPlayerNews`, `getTeamSentiment` — all off-season empty payloads, acceptable
- **FAIL (5):** see table below

| Tool | Category | Root Cause | Wave-2 Scope |
|------|----------|------------|--------------|
| `getGamePredictions` | HTTP_ERROR (404) | No prediction data for 2026 wk 1 (preseason) | 63-04 data-gap (ingest predictions OR decide tool should tolerate 404 as "no games yet") |
| `getTeamRoster` | HTTP_ERROR (404) | No lineup data for KC 2026 wk 1 (preseason) | 63-04 data-gap (preseason lineup fallback OR 404→empty contract) |
| `compareExternalRankings` | HTTP_ERROR (404) | Route `/api/rankings/compare` returns `{"detail":"Not Found"}` — router registered but probably empty table | 63-03 missing route (verify `rankings.router` path registration and source=sleeper query handling) |
| `getDraftBoard` | SCHEMA_MISMATCH | Backend returns `{session_id, players, ...}`; tool expects `{board}` | 63-02 schema contract (rename `players` → `board` in backend OR update chat route.ts to read `players`) |
| `getSentimentSummary` | SCHEMA_MISMATCH | Backend returns `{total_docs, top_positive, top_negative, sentiment_distribution}`; tool expects `{total_articles, bullish_players, bearish_players}` | 63-02 schema contract (align field names or add aliases) |

## Task Commits

1. **Task 1: audit script** — `6900ad5` (feat)
2. **Task 2: baseline audit run** — `d13351d` (docs)

Plan metadata commit will follow after STATE.md + ROADMAP.md updates.

## Files Created/Modified

- `scripts/audit_advisor_tools.py` — 12-probe httpx audit with per-tool validators, failure categorization, markdown writer, --dry-run
- `.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.md` — baseline table + failure-detail section + raw stdout

## Decisions Made

- **httpx chosen** — already available transitively via anthropic==0.92.0, no new dependency. The plan said "add to requirements if not already present"; it is present transitively, so no requirements change.
- **TOOL_REGISTRY declared without type annotation** — the plan's AST verification looks for `ast.Assign`, not `ast.AnnAssign`. Comment explains this choice inline.
- **`warn_on_empty` flag on news/sentiment tools** — preseason 2026 data simply does not exist yet; an empty news feed is expected. Ship gate in wave 3 should NOT block on these. `compareExternalRankings` explicitly does NOT use warn_on_empty because empty players → external source unreachable (a real bug).
- **Did not attempt any fixes** — the plan is explicitly measurement-only. All failures documented, none patched.

## Deviations from Plan

None — plan executed exactly as written. The only non-trivial decision was choosing a plain assignment for `TOOL_REGISTRY` instead of an annotated one, which was required to pass the plan's own AST-based verification command. This is a plan-specified constraint, not a deviation.

## Issues Encountered

- `python -m black` reformatted the file once after initial write. Re-verified TOOL_REGISTRY still resolves via `ast.Assign` after reformat — OK.
- No network issues. Railway responded to every probe within 1.1s.

## Wave-2 Scoping (for 63-02 / 03 / 04 planners)

- **63-02 (schema contracts, 2 tools):** `getDraftBoard`, `getSentimentSummary` — backend response shapes do not match what `web/frontend/src/app/api/chat/route.ts` destructures. Pick one side (either rename backend fields or update tool expectations) and codify the contract.
- **63-03 (missing route, 1 tool):** `compareExternalRankings` → 404. Either the `rankings.router` is not reaching `/api/rankings/compare` (check prefix) or the `source=sleeper` path has no data row. Probe with `--verbose` on a dev server to confirm which.
- **63-04 (data gaps, 2 tools):** `getGamePredictions` + `getTeamRoster` return 404 for season=2026 week=1. Decide if the tools should: (a) tolerate empty / 404 during preseason and return a friendly "not yet available" to the LLM, OR (b) the pipeline should be updated so 2026 wk1 has at least stub data. Option (a) is faster and lower-risk.

## Probe-Script Limitations

- Runs unauthenticated. If Railway later enables `API_KEY` env var, set `RAILWAY_API_KEY` locally and the probe automatically sends the `X-API-Key` header.
- Probe is deterministic but single-shot — no retries. A flaky transient 500 would be recorded as HTTP_ERROR. Re-run to distinguish flaky from persistent.
- Validators enforce schema at the top-level only; deep-field validation (e.g. numeric ranges, enum membership) is out of scope for the baseline. Wave-3 ship gate can extend validators if needed.
- No frontend→Vercel probe: the probe targets the Railway backend directly, mirroring what the Next.js server-side route calls via `fastapiGet()`. This matches the real tool data path — Vercel's chat route is a thin proxy over the same endpoints.

## Next Phase Readiness

- Wave 2 (`63-02`, `63-03`, `63-04`) can read `TOOL-AUDIT.md`, pick a FAIL row, fix the root cause, and re-run `python scripts/audit_advisor_tools.py` to verify.
- Wave 3 (`63-05`) re-runs the same script as a SHIP gate: must reach 12 PASS (or 12 PASS+WARN for preseason tolerances) before advisor hardening closes.

## Self-Check: PASSED

- [x] `scripts/audit_advisor_tools.py` exists (verified: file present, parses with AST, dry-run succeeds)
- [x] `.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.md` exists (verified: file present, 14 pipe-prefixed rows covering 12 tools)
- [x] All 12 tool names present in audit markdown (verified by grep)
- [x] Commit `6900ad5` exists (Task 1)
- [x] Commit `d13351d` exists (Task 2)

---
*Phase: 63-ai-advisor-hardening*
*Completed: 2026-04-18*
