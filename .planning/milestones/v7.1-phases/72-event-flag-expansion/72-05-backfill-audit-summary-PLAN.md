---
phase: 72
plan: 05
type: execute
wave: 5
depends_on: [72-01, 72-02, 72-03, 72-04]
files_modified:
  - scripts/audit_event_coverage.py
  - scripts/audit_advisor_tools.py
  - .planning/phases/72-event-flag-expansion/audit/event_coverage.json
  - .planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json
  - .planning/phases/72-event-flag-expansion/72-SUMMARY.md
  - .planning/STATE.md
  - .planning/ROADMAP.md
  - .planning/REQUIREMENTS.md
autonomous: false
requirements:
  - EVT-04
  - EVT-05
tags: [backfill, audit, evt-04, evt-05, railway-live, ship-or-skip-gate, phase-summary]
must_haves:
  truths:
    - "Plans 72-01..04 are deployed to Railway (backend) and Vercel (frontend) — auto-deploy via existing GHA on commit to main"
    - "scripts/audit_event_coverage.py exists; default base URL is Railway production; supports --local for developer-mode pre-Railway smoke testing only"
    - "Audit JSON file at .planning/phases/72-event-flag-expansion/audit/event_coverage.json was generated against RAILWAY LIVE (base_url == https://nfldataengineering-production.up.railway.app) and shows >= 15 of 32 teams with at least one non-zero count across the 19-flag union (12 existing + 7 new) OR coach_news_count + team_news_count > 0"
    - "scripts/audit_advisor_tools.py extended (or sibling script) returns non-empty getPlayerNews + getTeamSentiment results for >= 20 teams against Railway LIVE"
    - "Audit JSON file at .planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json was generated against RAILWAY LIVE and shows EVT-05 PASS"
    - "Local 2025 W17 + W18 backfill executed against ingested Bronze content; Silver non_player_news + Silver signals envelopes contain new-flag + subject_type records"
    - "72-SUMMARY.md committed; STATE.md updated to reflect Phase 72 SHIPPED; ROADMAP.md Phase 72 row marked Complete; REQUIREMENTS.md EVT-01..05 all marked [x] with evidence pointers"
  artifacts:
    - path: "scripts/audit_event_coverage.py"
      provides: "EVT-04 audit CLI; HTTPS GET /api/news/team-events; counts teams with non-zero coverage in the 19-flag union; emits JSON + writes markdown summary; default target Railway live; --local is dev-mode smoke only"
      contains: "audit_event_coverage"
      contains_2: "/api/news/team-events"
    - path: "scripts/audit_advisor_tools.py"
      provides: "extended TOOL_REGISTRY entries OR new sibling script that asserts getPlayerNews + getTeamSentiment return non-empty for >= 20 teams"
      contains: "TOOL_REGISTRY"
    - path: ".planning/phases/72-event-flag-expansion/audit/event_coverage.json"
      provides: "EVT-04 evidence snapshot — committed after RAILWAY LIVE run shows >= 15/32 teams (base_url field MUST be the Railway URL, not localhost)"
    - path: ".planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json"
      provides: "EVT-05 evidence snapshot — committed after RAILWAY LIVE run shows >= 20/32 teams (base_url field MUST be the Railway URL)"
    - path: ".planning/phases/72-event-flag-expansion/72-SUMMARY.md"
      provides: "phase-level summary linking to audit JSONs + plan SUMMARYs + benchmark/cost metrics"
  key_links:
    - from: "scripts/audit_event_coverage.py"
      to: "https://nfldataengineering-production.up.railway.app/api/news/team-events"
      via: "httpx.GET with default RAILWAY_API_URL env override; --local is dev-mode only and produces NON-shippable JSON"
      pattern: "RAILWAY_API_URL"
    - from: ".planning/phases/72-event-flag-expansion/audit/event_coverage.json"
      to: "EVT-04 ship-or-skip gate (CONTEXT D-04)"
      via: "phase merges only when this file is committed showing pass against Railway live; base_url field is the load-bearing audit anchor"
      pattern: "teams_with_events"
    - from: ".planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json"
      to: "EVT-05 ship-or-skip gate (CONTEXT D-04)"
      via: "phase merges only when this file is committed showing pass against Railway live"
      pattern: "non_empty_teams"
---

<objective>
Close Phase 72 with a verified production deployment: backfill 2025 W17 + W18 against ingested Bronze, then prove EVT-04 (≥15/32 teams with non-zero events on `/api/news/team-events`) and EVT-05 (≥20 teams via advisor tools) by hitting Railway LIVE. Commit audit JSON files as ship-or-skip evidence per CONTEXT D-04, then write the phase SUMMARY + propagate REQUIREMENTS / STATE / ROADMAP updates.

Purpose: Plans 72-01..04 are pure code; without backfill + a live audit they don't ship. This plan is the gate that forces Phase 72 into production behaviour, proves the user-visible contract, and writes the evidence trail that future audits + retrospectives can reference.

Output: Two audit scripts, two committed JSON evidence files (both with `base_url` set to the Railway production URL), phase SUMMARY, STATE / ROADMAP / REQUIREMENTS sync. Ship-or-skip gate honoured per CONTEXT D-04: phase merges only when both audits PASS against Railway live. There is no fallback path to localhost — `--local` is a developer-mode smoke flag, not a shippable gate.
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
@.planning/phases/72-event-flag-expansion/72-01-SUMMARY.md
@.planning/phases/72-event-flag-expansion/72-02-SUMMARY.md
@.planning/phases/72-event-flag-expansion/72-03-SUMMARY.md
@.planning/phases/72-event-flag-expansion/72-04-SUMMARY.md
@.planning/phases/71-llm-primary-extraction/71-SUMMARY.md
@CLAUDE.md
@scripts/audit_advisor_tools.py
@scripts/process_sentiment.py

<interfaces>
<!-- LOCKED contracts. -->

From scripts/audit_advisor_tools.py (Phase 63 final — verified by reading):

```python
DEFAULT_BASE_URL = "https://nfldataengineering-production.up.railway.app"
DEFAULT_TIMEOUT = 15.0
DEFAULT_OUTPUT_PATH = ...  # phase directory default

@dataclass(frozen=True)
class ToolProbe:
    tool_name: str
    endpoint: str
    params: dict[str, str] = field(default_factory=dict)
    validator: Validator = field(default=lambda body: (True, "ok"))
    warn_on_empty: bool = False

# 12 existing entries:
TOOL_REGISTRY = [..., ToolProbe(tool_name="getPlayerNews", ...), ToolProbe(tool_name="getTeamSentiment", ...), ...]

# Existing CLI flags (verified by reading lines 580-640):
#   --dry-run         : sanity-check TOOL_REGISTRY without network I/O
#   --output PATH     : write TOOL-AUDIT.md (default DEFAULT_OUTPUT_PATH)
# RAILWAY_API_URL env var overrides DEFAULT_BASE_URL
# RAILWAY_API_KEY env var supplies optional auth header

def probe(client, tool_probe) -> dict[str, Any]: ...
def run_audit(base_url, api_key) -> list[dict[str, Any]]: ...
def write_audit_markdown(results, out_path, *, base_url, auth_header_present) -> None: ...
def main(argv) -> int: ...
```

From web/api/routers/news.py:

```python
@router.get("/team-events", response_model=List[TeamEvents])
def get_team_events(season: int, week: int) -> List[TeamEvents]: ...
# Always returns 32 rows (zero-filled when no data).
# After Plan 72-04: each row carries coach_news_count, team_news_count, staff_news_count.

@router.get("/feed", response_model=List[NewsItem])
def get_news_feed(season, week=None, source=None, team=None, player_id=None, limit=50, offset=0): ...
# After Plan 72-04: each item carries subject_type + team_abbr top-level + the 7 new
# flag labels in event_flags: List[str].
```

From scripts/process_sentiment.py (Phase 71 CLI):

```text
# Run claude_primary backfill:
python scripts/process_sentiment.py --season 2025 --week 17 --extractor-mode claude_primary
python scripts/process_sentiment.py --season 2025 --week 18 --extractor-mode claude_primary
```

CONTEXT D-04 (LOCKED, NON-NEGOTIABLE):
- "Backfill runs only 2025 W17 + W18 — same fixture/data window as the Phase 71 benchmark."
- "EVT-04 gate: ≥ 15 of 32 teams have at least one non-zero event category on a freshly-backfilled W17+W18 run."
- "EVT-05 gate: Advisor news tools (getPlayerNews, getTeamSentiment) return non-empty results for ≥ 20 teams."
- **"Ship-or-skip gate: phase merges only when the audit JSON files are committed showing both gates passed against Railway live."** This is non-negotiable. Local-only validation is NOT acceptable as a ship gate. If Railway data is hard to provision, the operator pauses execution and resumes later — they do NOT downgrade the gate.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Run backfill (2025 W17 + W18) against ingested Bronze + persist Silver/Gold</name>
  <read_first>
    - scripts/process_sentiment.py (full — confirm CLI args + roster_provider behaviour against ingested Bronze)
    - scripts/ingest_sentiment_rss.py (full — confirm Bronze ingestion entrypoint for offseason content)
    - scripts/ingest_sentiment_sleeper.py (full)
    - data/bronze/sentiment/ (ls — confirm ingested W17 + W18 content exists; if not, ingest first)
  </read_first>
  <files>(no source files modified — execution only; commits are the data + audit JSON)</files>
  <action>
    Per CONTEXT D-04 (locked):

    1. Verify ingested Bronze sentiment exists for 2025 W17 + W18:
       Run `ls data/bronze/sentiment/{rss,sleeper,reddit,pft,rotowire}/season=2025/ 2>/dev/null`. If empty for W17 or W18, run the ingestion CLIs first using `python scripts/ingest_sentiment_rss.py --weeks 17 18` and `python scripts/ingest_sentiment_sleeper.py --weeks 17 18`. Note: if these scripts only support a date-driven offset rather than week-driven backfill, document the approximation used in the SUMMARY.

    2. Confirm `ANTHROPIC_API_KEY` is set: `test -n "$ANTHROPIC_API_KEY" || (set -a; source .env; set +a; test -n "$ANTHROPIC_API_KEY")`.

    3. Run the claude_primary extraction for both weeks: `python scripts/process_sentiment.py --season 2025 --week 17 --extractor-mode claude_primary` then `python scripts/process_sentiment.py --season 2025 --week 18 --extractor-mode claude_primary`. Each run produces:
       - Silver signals envelope at `data/silver/sentiment/signals/season=2025/week=17/signals_*.json` (with `is_claude_primary: true` in envelope)
       - Silver non_player_pending envelope (leftover items)
       - Silver non_player_news envelope (coach + team + reporter items per Plan 72-03)
       - Cost-log Parquet under `data/ops/llm_costs/season=2025/week=17/`

       Verify post-run: `ls data/silver/sentiment/non_player_news/season=2025/week=17/` and the W18 equivalent. Both directories should contain at least one envelope JSON file.

    4. Run the weekly aggregator + team_weekly aggregator for both weeks. Use a small inline Python invocation (one file per call):

       `source venv/bin/activate; python -c "from src.sentiment.aggregation.weekly import WeeklyAggregator; from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator; [(WeeklyAggregator().aggregate(season=2025, week=w), TeamWeeklyAggregator().aggregate(season=2025, week=w)) for w in (17, 18)]"`

       Expected: Gold parquets at `data/gold/sentiment/season=2025/week={17,18}/` AND `data/gold/sentiment/team_sentiment/season=2025/week={17,18}/`. Team parquets must contain `coach_news_count`, `team_news_count`, `staff_news_count` columns (per Plan 72-03).

    5. Commit: `data(72-05): backfill 2025 W17 + W18 sentiment + non_player_news + team rollup`. Commit only the Silver + Gold artifacts — DO NOT commit `data/bronze/` (Bronze immutability rule from .claude/rules/nfl-data-conventions.md). Use `git add data/silver/sentiment/ data/gold/sentiment/ data/ops/llm_costs/`.
  </action>
  <verify>
    <automated>source venv/bin/activate && ls data/silver/sentiment/non_player_news/season=2025/week=17/*.json data/silver/sentiment/non_player_news/season=2025/week=18/*.json && python scripts/audit_event_coverage.py --local --skip-write 2>/dev/null || echo "audit script not yet created — Task 2 builds it"</automated>
  </verify>
  <done>
    Bronze ingestion confirmed (or ran successfully). Silver non_player_news envelopes exist for both weeks. Gold team_sentiment parquets exist with the 3 new count columns populated. Single data commit lands. No data/bronze/ writes occurred.
  </done>
</task>

<task type="auto">
  <name>Task 2: Build scripts/audit_event_coverage.py + extend audit_advisor_tools.py with EVT-05 probes</name>
  <read_first>
    - scripts/audit_advisor_tools.py (full — verify the existing CLI flags before extending: `--dry-run` and `--output PATH` exist; `--local` does NOT exist; pattern: env var `RAILWAY_API_URL` overrides default)
    - web/api/services/news_service.py NFL_TEAM_ABBRS constant (32-tuple) — must match exactly
    - .planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.md (any existing — confirm output format conventions)
  </read_first>
  <files>scripts/audit_event_coverage.py, scripts/audit_advisor_tools.py</files>
  <action>
    Per CONTEXT D-04 ship-or-skip gates (locked):

    1. Create `scripts/audit_event_coverage.py` (mirror structure of `scripts/audit_advisor_tools.py` — same httpx + dataclass + main() entry). Module docstring should explain: "EVT-04 audit — verify /api/news/team-events coverage on a fresh backfill. Fetches team-events for both W17 and W18, unions per-team event counts, counts how many of the 32 NFL teams have at least one non-zero event signal across the 19-flag union (positive_event_count + negative_event_count + neutral_event_count OR coach_news_count + team_news_count > 0). Gate: >= 15. Exit 0 pass / 1 fail. Default base URL is Railway production; --local flag exists for developer-mode pre-Railway smoke testing only and PRODUCES NON-SHIPPABLE JSON (the ship-or-skip gate per CONTEXT D-04 requires Railway-live audit JSON committed)."

       Implementation outline:
       - Constants: `DEFAULT_BASE_URL = "https://nfldataengineering-production.up.railway.app"`; `LOCAL_BASE_URL = "http://localhost:8000"`; `EVT_04_GATE = 15`; `WEEKS = (17, 18)`; `SEASON = 2025`
       - argparse: `--local` (developer-mode flag, NOT a shippable target — emit a stderr warning when used: "WARNING: --local mode produces non-shippable JSON. CONTEXT D-04 ship gate requires Railway-live audit."), `--json-out`, `--md-out`, `--season`, `--weeks` (override comma-list), `--skip-write` (verify-mode flag for use in this plan's verify automation)
       - For each week: `client.get("/api/news/team-events", params={"season": S, "week": W})`. Validate response is exactly 32 rows.
       - Union per-team counts across both weeks. Sum `positive_event_count + negative_event_count + neutral_event_count + coach_news_count + team_news_count` per team_abbr.
       - For each team: `has_events = sum_above > 0`
       - `teams_with_events = sum(has_events for all 32)`
       - `passed = teams_with_events >= EVT_04_GATE`
       - Write JSON to `--json-out` (default `.planning/phases/72-event-flag-expansion/audit/event_coverage.json`) with this shape:
         - `audited_at`: ISO 8601 UTC string
         - `base_url`: string (load-bearing — Task 3 ship gate inspects this field; if it equals LOCAL_BASE_URL the file is NOT shippable)
         - `season`: 2025
         - `weeks`: [17, 18]
         - `gate`: 15
         - `teams_with_events`: int
         - `passed`: bool
         - `per_team`: list of 32 dicts each with `{team, positive, negative, neutral, coach, team_count, has_events}`
       - Write a markdown summary to `--md-out` (default `.planning/phases/72-event-flag-expansion/audit/event_coverage.md`).
       - Exit 0 if `passed`, else 1.

    2. Extend `scripts/audit_advisor_tools.py` for EVT-05:
       - Add a new validator `_validate_news_per_team(body, *, min_teams: int = 20) -> Tuple[bool, str]` that asserts the response is a list AND extracts unique `team` values where `len(item.get("event_flags", [])) > 0` OR any of the 5 top-level bool keys (is_ruled_out / is_inactive / is_questionable / is_suspended / is_returning) is True. Return `(False, f"empty:{N}_lt_20")` when fewer than 20 teams have content. Note: per CONTEXT Phase 72 Schema Note, the 7 new flags surface as STRINGS in `event_flags`, not as top-level bools — so checking `event_flags` length is the correct gate.
       - Add a new ToolProbe entry: `getPlayerNewsCoverage` calling `/api/news/feed` with `season=2025&limit=200` and the new validator (warn_on_empty=False so EVT-05 hard-fails when below gate).
       - Add another ToolProbe entry: `getTeamSentimentCoverage` calling `/api/news/team-sentiment?season=2025&week=17` AND `week=18`, unioning teams with non-zero `signal_count`.
       - Add `--out-72` flag to `scripts/audit_advisor_tools.py::main` that writes a JSON-only summary to `.planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json` containing: `audited_at`, `base_url`, `evt_05_gate=20`, `non_empty_teams_player_news`, `non_empty_teams_team_sentiment`, `evt_05_passed` (both >= 20), `tool_results` (existing per-tool dicts). The `base_url` field MUST record the actual probe target so the Task 3 ship gate can inspect it.

    3. Test both scripts in `--local` mode against the dev server (after starting it with `uvicorn web.api.main:app --port 8000 &`). This is a SMOKE test of the audit machinery, NOT a ship gate.
       - `python scripts/audit_event_coverage.py --local --json-out /tmp/test_evt04.json`
       - `RAILWAY_API_URL=http://localhost:8000 python scripts/audit_advisor_tools.py --out-72 /tmp/test_evt05.json`

       Inspect both JSONs to confirm shape. EVT-04 gate may legitimately fail locally if backfill in Task 1 used limited Bronze content; that's expected. The Railway run in Task 3 is the load-bearing run.

    4. Commit: `feat(72-05): add EVT-04 + EVT-05 audit scripts (event coverage + advisor tool extensions)`
  </action>
  <verify>
    <automated>source venv/bin/activate && python scripts/audit_event_coverage.py --local --json-out /tmp/audit_test.json && test -f /tmp/audit_test.json && python scripts/audit_advisor_tools.py --out-72 /tmp/audit_72_test.json 2>&1 | head -5</automated>
  </verify>
  <done>
    `scripts/audit_event_coverage.py` exists with the documented CLI surface; `--local` prints a non-shippable warning. `scripts/audit_advisor_tools.py` has the 2 new ToolProbe entries + `--out-72` flag (smoke-tested against /tmp). Local --local runs of both scripts produce well-formed JSON (with `base_url` reflecting the actual target). Single feat commit lands.
  </done>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 3: HARD GATE — Push to main → Railway deploys → trigger W17/W18 backfill on Railway → run audits against Railway LIVE → commit audit JSONs (HUMAN-MEDIATED, single path only)</name>
  <what-built>
    Plans 72-01..04 ship code. Backend (FastAPI) auto-deploys to Railway on push to main; frontend (Next.js) auto-deploys to Vercel on push to main. Plan 72-05 Tasks 1+2 produce local audit machinery. This task is the SHIP GATE: the audit JSON files committed under `.planning/phases/72-event-flag-expansion/audit/` MUST be generated against Railway LIVE per CONTEXT D-04.

    There is NO fallback path. CONTEXT D-04 says (locked, NON-NEGOTIABLE):

    > "Ship-or-skip gate: phase merges only when the audit JSON files are committed showing both gates passed against Railway live."

    If Railway data sync is hard, the operator pauses execution and resumes later. Do NOT downgrade the gate by committing a `--local` JSON. Do NOT commit a `base_url: http://localhost:8000` audit file as evidence. The `--local` flag exists for developer-mode pre-Railway smoke testing only.

    What needs human action:
    a) Push the Plan 72-01..04 commits to main (so Railway redeploys with the new schema + service code)
    b) Confirm Railway deploys cleanly (no missing env, no migration failure)
    c) Confirm Vercel rebuilds cleanly
    d) Trigger the W17/W18 backfill ON RAILWAY via `gh workflow run daily-sentiment.yml` (or whatever GHA dispatch the daily cron uses) so Railway's filesystem / persistent layer holds the freshly-extracted Silver non_player_news data
    e) Run BOTH audits with the default Railway base URL (no `--local` flag)
    f) Confirm BOTH `passed`/`evt_05_passed` are true and `base_url` records the Railway production URL
    g) Commit the resulting JSON files as ship-gate evidence

    If step (d) is blocked (e.g., Railway lacks the writable filesystem the daily cron writes to, or AWS creds are missing for S3 sync, or the GHA workflow doesn't accept manual dispatch), the operator PAUSES this task and resolves the blocker — they do NOT proceed by running `--local` and committing a downgraded audit. The gate is locked.
  </what-built>
  <how-to-verify>
    1. Push the Plan 72-01..04 commits to main if not already pushed: `git push origin main`. Wait for the Railway deploy + Vercel deploy to complete (~3-5 min each — visible in dashboards).

    2. Check Railway health: `curl -s https://nfldataengineering-production.up.railway.app/api/health | python -m json.tool`. Confirm `status: ok` and that `llm_enrichment_ready: true` (it should be — set in Phase 71).

    3. Check Vercel: visit https://frontend-jet-seven-33.vercel.app/news — confirm the page renders without console errors (open dev tools).

    4. Trigger the W17/W18 backfill on Railway (so Railway-side Silver/Gold contains real non_player_news data — without this step, the EVT-04 audit will return zero-filled rows and FAIL the gate, which is the correct behaviour):
       `gh workflow run daily-sentiment.yml -f season=2025 -f weeks=17,18 -f extractor-mode=claude_primary`
       (Adjust flag names to match the actual workflow inputs — see `.github/workflows/daily-sentiment.yml`.)
       Wait for the workflow to complete (visible via `gh run list --workflow=daily-sentiment.yml --limit 1` then `gh run view <id>`).

       If the workflow does not accept manual dispatch with these inputs, OR Railway has no path to receive Silver data the audit can read, PAUSE here and resolve the blocker. Acceptable resolutions: (i) wait for the next daily cron to populate Silver naturally, (ii) sync local Silver via whatever mechanism Railway reads from (S3 if AWS creds are refreshed, or commit + redeploy if Railway reads from the repo's `data/` tree). Do NOT proceed past this step with `--local` audits — the gate is locked.

    5. Run the EVT-04 audit AGAINST RAILWAY (no `--local` flag):
       `python scripts/audit_event_coverage.py --json-out .planning/phases/72-event-flag-expansion/audit/event_coverage.json --md-out .planning/phases/72-event-flag-expansion/audit/event_coverage.md`
       Confirm exit 0 (PASS — teams_with_events >= 15). If exit 1, investigate the gap (insufficient backfill content? aggregator bug? Silver data not on Railway disk?) and resolve — do NOT downgrade.
       Inspect the JSON: `cat .planning/phases/72-event-flag-expansion/audit/event_coverage.json | python -m json.tool | grep -E 'base_url|passed|teams_with_events'` — confirm `base_url` is the Railway production URL.

    6. Run the EVT-05 audit AGAINST RAILWAY (no localhost env override):
       `python scripts/audit_advisor_tools.py --out-72 .planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json`
       Confirm `evt_05_passed: true` in the output JSON AND `base_url` is the Railway production URL.

    7. Inspect both JSON files: confirm `base_url`, `audited_at`, `passed`/`evt_05_passed`, and per-team counts look sensible. The `base_url` field is the load-bearing audit anchor — it MUST equal `https://nfldataengineering-production.up.railway.app` in BOTH files.

    8. Commit both audit files: `git add .planning/phases/72-event-flag-expansion/audit/ && git commit -m "audit(72-05): EVT-04 + EVT-05 evidence (Railway live — pass)"`.
  </how-to-verify>
  <resume-signal>Type "approved" to confirm the deploy + Railway-live audit JSON files are committed and BOTH gates passed (with `base_url` set to the Railway production URL). Type "blocked: <reason>" to escalate (e.g., Railway data sync blocker, GHA dispatch failure, gate failed against real Railway data) — DO NOT downgrade by committing a `--local` audit. Type "modified: <details>" only if the Railway URL itself changed since CONTEXT was written.</resume-signal>
</task>

<task type="auto">
  <name>Task 4: Write Phase 72 SUMMARY + sync STATE / ROADMAP / REQUIREMENTS</name>
  <read_first>
    - .planning/phases/71-llm-primary-extraction/71-SUMMARY.md (mirror phase SUMMARY structure)
    - .planning/phases/72-event-flag-expansion/72-{01,02,03,04}-SUMMARY.md (consolidate metrics)
    - .planning/phases/72-event-flag-expansion/audit/event_coverage.json (extract teams_with_events + base_url for the SUMMARY — both must reflect Railway live)
    - .planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json (extract evt_05 numbers + base_url)
    - .planning/STATE.md (update Position + Last Activity + Decisions appendix)
    - .planning/ROADMAP.md (update Phase 72 row + summary checklist)
    - .planning/REQUIREMENTS.md (mark EVT-01..05 [x] with evidence)
  </read_first>
  <files>.planning/phases/72-event-flag-expansion/72-SUMMARY.md, .planning/STATE.md, .planning/ROADMAP.md, .planning/REQUIREMENTS.md</files>
  <action>
    Pre-requisite: Task 3 must have completed with both audit JSON files committed AND each carrying `base_url == https://nfldataengineering-production.up.railway.app`. If either file's base_url is localhost, STOP — Task 3 must be re-run, the gate is not satisfied.

    1. Write `.planning/phases/72-event-flag-expansion/72-SUMMARY.md` mirroring `71-SUMMARY.md` structure. Include:
       - Frontmatter listing all 5 plans + `requirements-completed: [EVT-01, EVT-02, EVT-03, EVT-04, EVT-05]`
       - Phase Goal Recap section
       - Shipped Plans table (5 rows linking to 72-01..05 SUMMARYs)
       - Requirements Coverage table (EVT-01..05 each with status DONE + evidence pointer)
       - Backfill metrics: docs ingested W17 + W18, signals produced, non_player_news records produced, coach/team/reporter splits
       - EVT-04 evidence: `teams_with_events: N` (from audit JSON) — quote the JSON path AND the `base_url` field (must be the Railway URL)
       - EVT-05 evidence: `non_empty_teams_player_news: M`, `non_empty_teams_team_sentiment: K` (from audit JSON) — quote `base_url` (must be the Railway URL)
       - Files Changed (consolidated across all 5 plans)
       - Operational Notes section explaining how the daily cron now produces non_player_news automatically
       - Risks & Watchouts: cold-cache cost spike on prompt drift (Plan 72-01 risk lineage), Railway data sync requirement for future audit re-runs, reporter byline disambiguation deferred
       - Threat Flags (consolidated from per-plan)
       - Self-Check: PASSED checklist including "Audit base_url == Railway production URL ✓"

    2. Update `.planning/STATE.md`:
       - Set `status: Phase 72 shipped — ready for Phase 73 ∥ 74 ∥ 75`
       - Update `stopped_at: ...` with Phase 72 completion details (5/5 plans, EVT-01..05 closed, Railway-live audit gates passed)
       - Update `last_updated` to current ISO timestamp
       - Update `last_activity` to current date
       - Update `progress.completed_phases` to 2 (was 1) and other counters
       - Update Current Position section: `Phase: 72 → 73`, set Status to "Phase 72 shipped"
       - Append to Decisions: `[72-05]: EVT-04 + EVT-05 ship-or-skip gates passed against Railway live (audit JSON files at .planning/phases/72-event-flag-expansion/audit/, base_url=https://nfldataengineering-production.up.railway.app)`
       - Update Pending Todos: remove Phase 72 references, leave Phase 73-75 work
       - Update Session Continuity: `Resume with: /gsd:discuss-phase 73`

    3. Update `.planning/ROADMAP.md`:
       - Find the Phase 72 entry under "🚧 v7.1 Draft Season Readiness"
       - Change `[ ]` to `[x]` on the Phase 72 summary checklist line
       - Update the Phase Details "Phase 72" block: add `**Plans:** 5/5 plans complete` and a list of the 5 plans with `[x]` checkmarks
       - Update the bottom progress table: change Phase 72 row to `5/5 | Complete | YYYY-MM-DD`

    4. Update `.planning/REQUIREMENTS.md`:
       - Mark EVT-01 [x] with evidence `Plans 72-01 + 72-02 — extractor/prompt/fixture re-record`
       - Mark EVT-02 [x] with evidence `Plan 72-03 — _route_non_player_items + non_player_news Silver channel`
       - Mark EVT-03 [x] with evidence `Plan 72-03 — WeeklyAggregator.last_null_player_count tracked`
       - Mark EVT-04 [x] with evidence `Plan 72-05 — audit/event_coverage.json (base_url=Railway) shows teams_with_events=N >= 15`
       - Mark EVT-05 [x] with evidence `Plan 72-05 — audit/advisor_tools_72.json (base_url=Railway) shows non_empty_teams >= 20`
       - Update the Traceability Table EVT row from `Pending` to the dated completion entry mirroring the LLM row format

    5. Run final sentiment + web suite to confirm no regression: `python -m pytest tests/sentiment/ tests/web/ --tb=no -q`. Expected count >= 213.

    6. Commit: `docs(72-05): close Phase 72 — SUMMARY + STATE/ROADMAP/REQUIREMENTS updates`
  </action>
  <verify>
    <automated>test -f .planning/phases/72-event-flag-expansion/72-SUMMARY.md && test -f .planning/phases/72-event-flag-expansion/audit/event_coverage.json && test -f .planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json && python -c "
import json
for p in ('.planning/phases/72-event-flag-expansion/audit/event_coverage.json', '.planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json'):
    d = json.load(open(p))
    bu = d.get('base_url', '')
    assert 'railway.app' in bu, f'{p} base_url must be Railway live, got {bu!r}'
    print(f'OK: {p} base_url={bu}')
" && grep -q "Phase 72 shipped" .planning/STATE.md && grep -q "EVT-01.*\[x\]" .planning/REQUIREMENTS.md && grep -q "EVT-05.*\[x\]" .planning/REQUIREMENTS.md</automated>
  </verify>
  <done>
    Both audit JSON files exist AND carry `base_url` containing `railway.app` (the load-bearing ship-gate proof). Phase 72 SUMMARY exists with audit numbers + 5 plan refs. STATE.md says "Phase 72 shipped". ROADMAP.md Phase 72 row marked complete. REQUIREMENTS.md EVT-01..05 all checked with evidence (each EVT-04 + EVT-05 entry references the Railway base_url). Single docs commit lands.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Local audit script → Railway live API | HTTPS GET; httpx timeout=15s; X-API-Key header optional |
| Audit JSON files → ship gate | Committed JSON is the load-bearing evidence; humans + tooling read these to verify gate compliance; `base_url` field is the audit anchor |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-72-05-01 | Denial of Service | Railway live API during audit | accept | httpx timeout=15s + retries=0 (existing pattern from audit_advisor_tools.py); audit script exits non-zero on transport error and the operator re-runs. No retry storms. |
| T-72-05-02 | Information Disclosure | RAILWAY_API_KEY env in scripts | mitigate | Audit scripts read from env only; never log the key; CLI `--api-key` flag absent (env-only contract). Pre-commit hook blocks accidental commits. |
| T-72-05-03 | Tampering | Committed audit JSON files | mitigate | JSON includes `audited_at` ISO timestamp + `base_url` so tamper attempts (e.g., backdating a fail, claiming a `--local` JSON satisfies the gate) are visible in git history; Task 4 verify automation explicitly asserts `base_url` contains `railway.app`. |
| T-72-05-04 | Repudiation | Ship-gate compliance | mitigate | Task 3 + Task 4 both inspect `base_url` and refuse non-Railway evidence. Task 3 resume-signal does not allow a downgrade path; the operator must "approved" (Railway live), "blocked" (escalate), or "modified" (different Railway URL). There is no "approved (path-B)" option as in earlier drafts of this plan. |
| T-72-05-05 | Spoofing | Bronze ingestion data quality | accept | Phase 72 backfill consumes whatever Bronze data exists; if ingestion content is sparse, EVT-04 may legitimately miss the >= 15 gate. The CONTEXT explicitly limits backfill to W17 + W18, so this risk is accepted — but the audit failure surfaces as a real gate failure, not a downgrade. |
</threat_model>

<verification>
- `ls data/silver/sentiment/non_player_news/season=2025/week=17/*.json | wc -l` >= 1 (Task 1 output)
- `ls data/silver/sentiment/non_player_news/season=2025/week=18/*.json | wc -l` >= 1 (Task 1 output)
- `python -c "import pandas as pd; from pathlib import Path; df = pd.read_parquet(sorted(Path('data/gold/sentiment/team_sentiment/season=2025/week=17/').glob('*.parquet'))[-1]); print(df[['team','coach_news_count','team_news_count','staff_news_count']].head())"` runs without error and shows the 3 new columns
- `python scripts/audit_event_coverage.py --skip-write 2>&1 | grep -E "EVT_04_GATE|teams_with_events"` shows the constants (do not require `--dry-run` — that flag is not part of this script's surface)
- `python scripts/audit_advisor_tools.py --dry-run | wc -l` >= 14 (12 existing + 2 new probes)
- `test -f .planning/phases/72-event-flag-expansion/audit/event_coverage.json && python -c "import json; d=json.load(open('.planning/phases/72-event-flag-expansion/audit/event_coverage.json')); assert d.get('passed') is True; assert 'railway.app' in d.get('base_url', ''); print(f'EVT-04 PASS — teams_with_events={d[\"teams_with_events\"]} base_url={d[\"base_url\"]}')"` exits 0
- `test -f .planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json && python -c "import json; d=json.load(open('.planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json')); assert d.get('evt_05_passed') is True; assert 'railway.app' in d.get('base_url', ''); print(f'EVT-05 PASS — base_url={d[\"base_url\"]}')"` exits 0
- `grep -E "Phase 72.*shipped|stopped_at.*Phase 72" .planning/STATE.md` returns at least 1 line
- `grep -E "EVT-0[1-5].*\[x\]" .planning/REQUIREMENTS.md | wc -l` returns 5
</verification>

<success_criteria>
- 2025 W17 + W18 backfill executed with claude_primary mode; Silver non_player_news + Gold team_sentiment artifacts committed
- `scripts/audit_event_coverage.py` exists and produces JSON evidence; `--local` is dev-mode only and emits a non-shippable warning
- `scripts/audit_advisor_tools.py` extended with 2 new probes + `--out-72` flag
- Audit JSON files at `.planning/phases/72-event-flag-expansion/audit/` show EVT-04 + EVT-05 PASS AGAINST RAILWAY LIVE (`base_url` field contains `railway.app` in both files)
- 72-SUMMARY.md captures all metrics with audit numbers + Railway base_url references
- STATE.md, ROADMAP.md, REQUIREMENTS.md synced
- Phase 72 marked SHIPPED; ready for Phase 73 ∥ 74 ∥ 75 parallel work per ROADMAP
- Final sentiment + web test suite >= 213 passed, 0 failed
</success_criteria>

<output>
After completion, create `.planning/phases/72-event-flag-expansion/72-SUMMARY.md` mirroring `71-SUMMARY.md`, plus the two audit JSON files under `.planning/phases/72-event-flag-expansion/audit/` (both with `base_url` set to the Railway production URL).
</output>
</content>
</invoke>