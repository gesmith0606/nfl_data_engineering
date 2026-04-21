---
phase: 66
milestone: v7.0
status: human_needed
verified_at: "2026-04-21"
---

# Phase 66: P0 Deployment Hotfixes — Verification

## Status

**human_needed** — code changes are complete and committed; two external actions must land on Railway before the phase can be marked "passed":

1. Push these commits to the Railway-tracking branch (Railway auto-deploys on push).
2. Set `ANTHROPIC_API_KEY` in the Railway dashboard (HOTFIX-01 — cannot be done via code).

Once both actions land, the success criteria below can be verified.

---

## Commits in this phase

| Plan | Commit  | Summary |
|------|---------|---------|
| 66-01 | `c4c1640` | Dockerfile bundles Bronze schedules + rosters; `CACHE_BUST=2026-04-21-01` |
| 66-02 | `0782870` | Graceful defaulting on predictions / lineups / roster; `llm_enrichment_ready` on `/api/health`; 12 new tests |
| 66-03 | `1cf224e` | Frontend `useWeekParams` hook + nuqs binding on predictions and lineups pages |

All 44 web tests pass (32 existing + 12 new in `tests/web/test_graceful_defaulting.py`).

---

## Human Verification Checklist

### Step 1 — Deploy the image (Railway)

The Railway backend auto-deploys on push. Confirm the new image picked up the Dockerfile changes:

```bash
# 1. Wait ~2-5 minutes after push for Railway to rebuild.
# 2. Verify the redeploy succeeded:
curl -s https://nfldataengineering-production.up.railway.app/api/version | jq .
```

Look for a commit hash near the top of the list. The commit should match `c4c1640` or later (Dockerfile change).

### Step 2 — Set ANTHROPIC_API_KEY on Railway (HOTFIX-01)

**This is the one action I cannot automate.**

1. Go to https://railway.app → `nfldataengineering-production` project.
2. Navigate to the service's **Variables** tab.
3. Add a new variable:
   - **Name:** `ANTHROPIC_API_KEY`
   - **Value:** your production Anthropic API key (same one in `.env` locally if you have one, or generate a new one at https://console.anthropic.com/)
4. Railway will trigger a redeploy automatically when the variable is saved.

**Verify the key is set** (the value itself is never exposed by the API):

```bash
curl -s https://nfldataengineering-production.up.railway.app/api/health | jq .llm_enrichment_ready
# Expected: true
```

If this returns `false`, the env var did not land — re-check the Variables tab and confirm the redeploy completed.

### Step 3 — Verify all 6 HOTFIX success criteria

Run each of these and confirm the expected result:

**HOTFIX-02 (schedules in image):**
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://nfldataengineering-production.up.railway.app/api/teams/current-week
# Expected: 200
```

**HOTFIX-03 (rosters in image):**
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://nfldataengineering-production.up.railway.app/api/teams/ARI/roster
# Expected: 200 (not 503)
```

**HOTFIX-04 (predictions defaulting):**
```bash
# No-params path:
curl -s "https://nfldataengineering-production.up.railway.app/api/predictions" | jq '{defaulted, season, week, count: (.predictions | length)}'
# Expected: defaulted=true, season+week resolved to the latest slice

# With-params path:
curl -s "https://nfldataengineering-production.up.railway.app/api/predictions?season=2025&week=18" | jq '{defaulted, count: (.predictions | length)}'
# Expected: defaulted=false
```

**HOTFIX-05 (lineups defaulting):**
```bash
curl -s "https://nfldataengineering-production.up.railway.app/api/lineups" | jq '{defaulted, season, week, count: (.lineup | length)}'
# Expected: defaulted=true with well-shaped envelope (lineups + lineup keys both present)
```

**HOTFIX-06 (graceful no-query-string across all 3):** covered by the commands above — none should return 422.

**Frontend smoke (HOTFIX-04/05 visual):**
- Open https://frontend-jet-seven-33.vercel.app/dashboard/predictions — page should load data (not 422 in browser console); URL should carry `?season=...&week=...`.
- Open https://frontend-jet-seven-33.vercel.app/dashboard/lineups — page should prompt to select a team; once a team is selected, lineup renders.

---

## Acceptance

Phase 66 is **passed** when all six HOTFIX-* success criteria above return the expected results in production. Reply with:

- `approved` if all six pass.
- Paste failing curl output if any don't — I'll triage inline.

---

## Requirements → Success Criteria Mapping

| REQ | Test | File |
|-----|------|------|
| HOTFIX-01 | `curl /api/health \| jq .llm_enrichment_ready` == true after Railway env var set | Manual (Step 2) |
| HOTFIX-02 | `GET /api/teams/current-week` returns 200 | Manual (Step 3) |
| HOTFIX-03 | `GET /api/teams/ARI/roster` returns 200 | Manual (Step 3) |
| HOTFIX-04 | `GET /api/predictions` returns 200 + `defaulted:true` | `tests/web/test_graceful_defaulting.py::test_predictions_*` |
| HOTFIX-05 | `GET /api/lineups` returns 200 + well-shaped envelope | `tests/web/test_graceful_defaulting.py::test_lineups_*` |
| HOTFIX-06 | All 3 endpoints 200 with no query string | `tests/web/test_graceful_defaulting.py::test_*_accepts_no_query_string` |

## Dependencies Unblocked

Once phase 66 passes:

- **Phase 69 (Sentiment Backfill)** — unblocked by HOTFIX-01 (API key) + HOTFIX-02 (schedules for date-ranged news queries)
- **Phase 70 (Frontend Empty States)** — unblocked by HOTFIX-04/05/06 (backend stops 422-ing; defensive UX can rely on stable empty-envelope contract)
