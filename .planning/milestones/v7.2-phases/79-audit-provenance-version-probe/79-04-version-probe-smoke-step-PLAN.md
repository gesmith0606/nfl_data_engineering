---
phase: 79-audit-provenance-version-probe
plan: 04
type: execute
wave: 2
depends_on: [79-03]
files_modified:
  - .github/workflows/deploy-web.yml
autonomous: true
requirements: [DQ-02]
must_haves:
  truths:
    - "After every push that triggers deploy-web.yml, a smoke step polls Railway /api/version until the returned git_sha equals GITHUB_SHA, or 5 minutes elapse"
    - "The smoke step is warn-only (continue-on-error: true) — it MUST NOT block deploys at this stage (D-07)"
    - "The smoke step runs in the deploy-backend job AFTER the existing 120s Railway-redeploy wait"
    - "The smoke step writes a clear ::warning:: annotation when git_sha never matches within the budget — Phase 84 promotes this to ::error:: + remove continue-on-error"
    - "The smoke step uses the existing GITHUB_TOKEN via implicit context — no new repo secret needed (auth happens at the Railway endpoint via X-API-Key from secrets.RAILWAY_API_KEY if API_KEY is set on Railway)"
  artifacts:
    - path: ".github/workflows/deploy-web.yml"
      provides: "New smoke step in deploy-backend job that polls Railway /api/version asserting git_sha == github.sha (warn-only, 5-minute budget)"
      contains: "Probe Railway /api/version for SHA match"
  key_links:
    - from: ".github/workflows/deploy-web.yml::deploy-backend job"
      to: "Railway /api/version endpoint"
      via: "curl polling loop with jq-based git_sha extraction"
      pattern: "RAILWAY_GIT_COMMIT_SHA|/api/version"
    - from: "GitHub Actions context ${{ github.sha }}"
      to: "smoke step"
      via: "shell var GITHUB_SHA in run: block"
      pattern: "github.sha"
---

<objective>
Add a smoke step to `.github/workflows/deploy-web.yml` that polls Railway `/api/version` after every redeploy and asserts the returned `git_sha` equals `${{ github.sha }}` (the just-pushed 40-char commit SHA).

Per CONTEXT D-06: this IS the asymmetry-detection capability. Phase 84 DEPLOY-02 inherits the same probe and promotes it to fail-on-mismatch.

Per CONTEXT D-07: warn-only, 5-minute budget. The 5-minute window matches Railway's observed p95 redeploy time during v7.0 hotfixes (Phase 66). Tail-latency cases beyond that are real freezes (the v7.1 silent-freeze sat at infinity). Warn-only ships now so Phase 84 can promote it to a hard gate after the probe is proven stable in production.

Output: one new step in the `deploy-backend` job that polls /api/version and emits a clear ::warning:: when SHA never matches.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md
@.github/workflows/deploy-web.yml

<interfaces>
<!-- Existing deploy-backend job (lines 161-172) -->

```yaml
deploy-backend:
  name: Wait for Railway auto-deploy
  runs-on: ubuntu-latest
  needs: quality-gate
  steps:
    - name: Wait for Railway webhook to redeploy
      run: |
        echo "Railway auto-deploys https://nfldataengineering-production.up.railway.app"
        echo "from the main branch via its own GitHub webhook (no GHA action needed)."
        echo "Sleeping 120s to let the new image start serving before live-gate probes."
        sleep 120
        echo "Railway should be serving the new commit by now."
```

<!-- /api/version endpoint shape (after Plan 79-03 ships) -->

```json
{
  "version": "0.1.0",
  "git_sha": "<full 40-char SHA from RAILWAY_GIT_COMMIT_SHA, or 'unknown'>",
  "build_id": "<RAILWAY_DEPLOYMENT_ID>",
  "deployed_at": "<ISO-8601>",
  "llm_enrichment_ready": true,
  "has_team_events_route": true,
  "has_player_badges_route": true
}
```

<!-- Existing pattern reference: deploy-frontend uses `id: pre` + outputs and a curl-based probe. Mirror that style. -->

<!-- GitHub-Actions context for the just-pushed SHA -->

`${{ github.sha }}` -- 40-char SHA of the commit that triggered the workflow. On `push` events this equals HEAD on `main`.

<!-- Auth note: /api/version is NOT in _AUTH_EXEMPT_PATHS in web/api/main.py (line 55 lists only /api/health, /api/docs, /api/openapi.json). Smoke step must send X-API-Key when API_KEY is set on Railway. -->

<!-- Existing secrets/vars patterns in the file (line 210): -->
```yaml
env:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  ENABLE_LLM_ENRICHMENT: ${{ vars.ENABLE_LLM_ENRICHMENT || 'false' }}
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add Probe-Railway-/api/version-for-SHA-match step to deploy-backend job</name>
  <files>.github/workflows/deploy-web.yml</files>
  <read_first>
    - .github/workflows/deploy-web.yml (FULL FILE — focus on lines 161-172, the deploy-backend job)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-06 smoke step, D-07 5-minute warn-only budget)
    - web/api/main.py (after Plan 79-03 ships — confirm /api/version response shape)
  </read_first>
  <behavior>
    - The smoke step runs in the existing `deploy-backend` job, AFTER the 120s `sleep` step
    - It polls `https://nfldataengineering-production.up.railway.app/api/version` every 15s
    - Polling continues until either: (a) the JSON body's `git_sha` field equals `${{ github.sha }}`, or (b) 5 minutes (300s) elapse from the start of the smoke step
    - Match → step exits 0 with a clear "::notice::SHA match" message and prints elapsed time
    - Timeout → step emits `::warning::` describing the asymmetry (expected SHA vs last-seen SHA), then exits 0 (warn-only per D-07)
    - When the API_KEY env on Railway is set, the smoke step uses `secrets.RAILWAY_API_KEY` for the `X-API-Key` header (same pattern as audit_event_coverage.py / live-gate-blocking)
    - The step uses ONLY `curl` and `jq` (both available on `ubuntu-latest`) — no new actions, no new dependencies
  </behavior>
  <action>
    Edit `.github/workflows/deploy-web.yml`. The existing `deploy-backend` job (lines 161-172) currently has ONE step:

    ```yaml
    deploy-backend:
      name: Wait for Railway auto-deploy
      runs-on: ubuntu-latest
      needs: quality-gate
      steps:
        - name: Wait for Railway webhook to redeploy
          run: |
            echo "Railway auto-deploys https://nfldataengineering-production.up.railway.app"
            echo "from the main branch via its own GitHub webhook (no GHA action needed)."
            echo "Sleeping 120s to let the new image start serving before live-gate probes."
            sleep 120
            echo "Railway should be serving the new commit by now."
    ```

    Append a NEW second step immediately after the `Wait for Railway webhook to redeploy` step (before the `live-gate-blocking` job that follows). The new step is named EXACTLY `Probe Railway /api/version for SHA match` (the acceptance grep below depends on this literal string):

    ```yaml
        - name: Probe Railway /api/version for SHA match
          # Phase 79 D-06 / D-07: warn-only asymmetry probe.
          # Phase 84 DEPLOY-02 promotes this to fail-on-mismatch by:
          #   1. removing `continue-on-error: true`
          #   2. flipping the timeout branch from ::warning:: to ::error:: + exit 1
          # The 5-minute budget mirrors Railway's observed p95 redeploy time
          # during v7.0 hotfixes (Phase 66). Tail-latency beyond that = real freeze.
          continue-on-error: true
          env:
            EXPECTED_SHA: ${{ github.sha }}
            RAILWAY_API_KEY: ${{ secrets.RAILWAY_API_KEY }}
          run: |
            set -uo pipefail
            BASE_URL="https://nfldataengineering-production.up.railway.app"
            VERSION_URL="${BASE_URL}/api/version"
            BUDGET_SECONDS=300
            POLL_INTERVAL=15

            HEADER_ARGS=()
            if [ -n "${RAILWAY_API_KEY:-}" ]; then
              HEADER_ARGS=(-H "X-API-Key: ${RAILWAY_API_KEY}")
            fi

            echo "Phase 79 D-06 asymmetry probe"
            echo "  Expected git_sha: ${EXPECTED_SHA}"
            echo "  URL: ${VERSION_URL}"
            echo "  Budget: ${BUDGET_SECONDS}s, poll every ${POLL_INTERVAL}s"
            echo ""

            START=$(date -u +%s)
            LAST_SEEN_SHA="<never_seen>"
            LAST_HTTP="<never>"
            ATTEMPT=0
            while :; do
              ATTEMPT=$((ATTEMPT + 1))
              NOW=$(date -u +%s)
              ELAPSED=$((NOW - START))
              if [ "${ELAPSED}" -gt "${BUDGET_SECONDS}" ]; then
                echo "::warning title=Railway /api/version SHA asymmetry::Expected ${EXPECTED_SHA} after ${BUDGET_SECONDS}s; last seen git_sha=${LAST_SEEN_SHA} (last HTTP ${LAST_HTTP}, ${ATTEMPT} attempts). Phase 84 DEPLOY-02 promotes this to a hard gate."
                echo "Probe outcome: TIMEOUT (warn-only per Phase 79 D-07)"
                exit 0
              fi

              # -m gives curl a per-request timeout so a hung Railway can't eat the whole budget.
              HTTP=$(curl -s -o response.json -m 10 -w "%{http_code}" "${HEADER_ARGS[@]}" "${VERSION_URL}" || echo "000")
              LAST_HTTP="${HTTP}"

              if [ "${HTTP}" = "200" ]; then
                # jq -r returns "null" when the field is absent; coerce to a stable sentinel.
                SEEN_SHA=$(jq -r '.git_sha // "missing"' response.json 2>/dev/null || echo "parse_error")
                LAST_SEEN_SHA="${SEEN_SHA}"
                if [ "${SEEN_SHA}" = "${EXPECTED_SHA}" ]; then
                  echo "::notice title=Railway /api/version SHA match::git_sha=${SEEN_SHA} after ${ELAPSED}s (${ATTEMPT} attempts)"
                  echo "Probe outcome: MATCH"
                  exit 0
                fi
                echo "  attempt ${ATTEMPT} t+${ELAPSED}s: HTTP ${HTTP}, git_sha=${SEEN_SHA} (waiting for ${EXPECTED_SHA})"
              else
                echo "  attempt ${ATTEMPT} t+${ELAPSED}s: HTTP ${HTTP} (expected 200; will retry)"
              fi

              sleep "${POLL_INTERVAL}"
            done
    ```

    Notes for the executor:
    - The step name MUST be the literal string `Probe Railway /api/version for SHA match` — Plan 84 will grep for this when promoting it
    - `continue-on-error: true` is the warn-only switch (D-07). Phase 84 deletes this line as part of DEPLOY-02
    - The polling loop uses `-uo pipefail` (NOT `-euo`) — `set -e` would abort on the first non-zero curl exit and prevent retries
    - Use `secrets.RAILWAY_API_KEY` ONLY if it already exists as a repo secret. If the smoke step gets 401 in production because the secret is unset on the runner, that is OK — the timeout path handles it as a warning. Do NOT add a new repo secret as part of this plan; that is operator territory
    - Do NOT reduce the 120s sleep that precedes this step — the existing live-gate-blocking job (line 185) depends on Railway being serving by then
    - Do NOT add the smoke step to the deploy-frontend or live-gate-blocking jobs; it lives in deploy-backend by design
  </action>
  <verify>
    <automated>python -c "import yaml; doc = yaml.safe_load(open('.github/workflows/deploy-web.yml')); steps = doc['jobs']['deploy-backend']['steps']; names = [s.get('name') for s in steps]; assert 'Probe Railway /api/version for SHA match' in names, names; idx = names.index('Probe Railway /api/version for SHA match'); assert idx > 0, 'Probe step must come AFTER the 120s wait step'; step = steps[idx]; assert step.get('continue-on-error') is True, 'Phase 79 D-07 requires warn-only'; assert 'github.sha' in step.get('env', {}).get('EXPECTED_SHA', ''), step.get('env'); assert '/api/version' in step['run']; assert 'BUDGET_SECONDS=300' in step['run'] or '300' in step['run']; print('OK', names)"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "Probe Railway /api/version for SHA match" .github/workflows/deploy-web.yml` returns exactly one match
    - `grep -nE "continue-on-error: true" .github/workflows/deploy-web.yml` shows the new smoke step has it (warn-only per D-07)
    - `grep -n "BUDGET_SECONDS=300" .github/workflows/deploy-web.yml` returns one match (5-minute budget per D-07)
    - `grep -n 'github\.sha' .github/workflows/deploy-web.yml` shows EXPECTED_SHA env var sourcing from `${{ github.sha }}`
    - `grep -n "/api/version" .github/workflows/deploy-web.yml` returns at least one match
    - The YAML parses cleanly: `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-web.yml'))"` exits 0
    - The new step lives inside the `deploy-backend` job (the python verify step above asserts this)
    - The smoke step is positioned AFTER the existing `Wait for Railway webhook to redeploy` step (verified by `idx > 0` in the python check)
    - The existing `live-gate-blocking` job is unmodified — `grep -nE "Live Site Gate \(Blocking\)" .github/workflows/deploy-web.yml` still shows the same line content
  </acceptance_criteria>
  <done>
    The deploy-web.yml deploy-backend job has a new "Probe Railway /api/version for SHA match" step with warn-only behaviour, 5-minute budget, 15-second polling interval, ::notice::-on-match / ::warning::-on-timeout output, and X-API-Key auth when secrets.RAILWAY_API_KEY is set. Phase 84 DEPLOY-02 will promote this by removing `continue-on-error: true` and flipping the timeout branch.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions runner → Railway public endpoint | Outbound HTTPS over the public internet to /api/version. |
| GitHub-Actions secret `RAILWAY_API_KEY` → curl X-API-Key header | Standard secret-injection pattern; the secret is masked in logs. |
| github.sha context → shell EXPECTED_SHA | GitHub-managed value; not user-controllable mid-run. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-79-12 | I (Information Disclosure) — secret in logs | RAILWAY_API_KEY in curl invocation | mitigate | Secret is sourced via `${{ secrets.RAILWAY_API_KEY }}` so GitHub Actions automatically masks it in any echoed line. The shell script never `echo`s `$RAILWAY_API_KEY` directly — it is passed via the `-H` flag in an array. The `curl -s` flag suppresses progress output. |
| T-79-13 | D (Denial of Service) — runaway smoke loop | The polling while-loop | mitigate | Hard 300s wall-clock budget enforced with `date -u +%s` arithmetic. Per-request `curl -m 10` so a hung Railway endpoint cannot wedge a single iteration. `sleep 15` between attempts caps the request rate. |
| T-79-14 | T (Tampering) — wrong-job placement breaks pipeline | Step inserted into wrong job | mitigate | Acceptance criterion uses Python YAML parse + index check to assert the step lives in `deploy-backend` AFTER the 120s wait. The `live-gate-blocking` job's `needs: [deploy-frontend, deploy-backend]` plus `if: always() && (...)` guard means a smoke-step warning does not affect downstream gating (warn-only). |
| T-79-15 | R (Repudiation) — silent failure | Smoke step swallows asymmetry | mitigate | Timeout branch emits `::warning::` with structured fields (expected SHA, last seen SHA, last HTTP, attempt count). The warning is visible on the workflow summary page. Phase 84 promotes the same branch to `::error::` + `exit 1`. |
| T-79-16 | E (Elevation of Privilege) — token scope creep | New repo secret needed? | accept | Plan does NOT add a new repo secret. `RAILWAY_API_KEY` is reused if already configured (per the planning_context "no new PAT"). `GITHUB_TOKEN` is not used by this step. |
</threat_model>

<verification>
- The smoke step parses as valid YAML
- It lives in the `deploy-backend` job, AFTER the 120s wait
- `continue-on-error: true` is set (warn-only per D-07)
- 5-minute / 300s budget is enforced
- The ${{ github.sha }} context is wired through EXPECTED_SHA
- The probe URL is `/api/version`
- The step does NOT run in any other job
- The existing live-gate-blocking job is unmodified — no behavioral regression
</verification>

<success_criteria>
- After every push that triggers deploy-web.yml, the smoke step runs and either (a) emits `::notice::SHA match` within ~5 minutes or (b) emits `::warning::SHA asymmetry` after the 5-minute budget
- The smoke step never blocks deploys (warn-only). Phase 84 promotes it.
- The step name is the exact literal string `Probe Railway /api/version for SHA match` so Phase 84 can grep-and-promote it
- No new repo secrets created; `RAILWAY_API_KEY` is consumed only if already set
- The full file remains valid YAML and the existing live-gate-blocking + auto-rollback jobs continue to work
</success_criteria>

<output>
After completion, create `.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-04-SUMMARY.md` capturing:
- Step name + position in deploy-backend
- Polling parameters (interval, budget)
- continue-on-error status and Phase 84 promotion path
- Any deviations from action text (with rationale)
- Confirmation that no new secrets were added
</output>
