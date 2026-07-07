# Production-Ready Website: Top 3 Critical Actions (2026-07-06)

Goal: a website users **pay** to use. Season starts ~Sept 10; draft season (peak
willingness-to-pay) is August. Working backward from "credit card entered":

1. Users pay for **fresh, correct data** → today the data pipeline cannot publish
   (AWS creds expired), the backend is a free HF Space refreshed by a manual
   CACHE_BUST hack, and the 6-workflow cron chain has never been verified
   end-to-end. **If data goes stale, paying users churn on day one.**
2. Users need a **way to pay** → Clerk is in `web/frontend/package.json` but
   unwired (no ClerkProvider anywhere); API auth is one shared `API_KEY` env
   var, optional. No Stripe, no per-user anything.
3. Users need a **reason to pay** vs free FantasyPros → the differentiator we
   already built (v8.0): connect YOUR Sleeper league, get advice under YOUR
   scoring with YOUR roster. Engine modules exist and are tested
   (`src/roster_optimizer.py`, `src/league_scoring.py`, `src/sleeper_*.py`);
   `web/api/routers/sleeper_user.py` and `dashboard/leagues/` are stubs of it.

Priority order is deliberate: **freshness → payments → premium feature.**
A paid product with stale data is a refund machine; a premium feature without
a paywall is free labor.

Each plan below is scoped for a **lower-tier subagent** (Sonnet for 1 and 3,
Sonnet/Haiku for 2's mechanical parts): explicit context files, numbered steps,
acceptance criteria, out-of-scope guardrails, and user-owned prerequisites
called out so the agent never blocks silently.

---

## PLAN 1 — Data Freshness You Can Sell (reliability + monitoring)

**Why #1:** The June incident (CMC ranked RB118 from a 42-day-old file) already
proved the failure mode. SANITY-M6 gate exists, but the publish path is broken:
GHA weekly-pipeline needs AWS creds, and the HF bridge only refreshes via manual
CACHE_BUST bumps.

**User-owned prerequisites (surface these FIRST, agent cannot do them):**
- [ ] Refresh AWS credentials → add `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
      / `AWS_REGION` to GitHub repo secrets (weekly-pipeline.yml consumes them)
- [ ] HF Spaces write token (`HF_TOKEN`) as a GitHub secret so CI can bump the
      bridge automatically

**Subagent brief (suggested: general-purpose, Sonnet):**

Context to read first: `.github/workflows/` (all 6 workflows),
`scripts/check_pipeline_health.py`, `scripts/sanity_check_projections.py`,
`web/DEPLOYMENT.md`, memory file `project_audit_2026_06_12.md` NEXT STEPS
(dress-rehearsal list), `project_matchups_news_shipped_2026_07_02.md`
(CACHE_BUST mechanics, py3.9 constraint on the bridge).

Steps:
1. Inventory the 6 workflows (weekly-pipeline, grading, sanity, odds-capture,
   sunday-refresh, daily-sentiment, deploy-web, weekly-external-projections —
   consolidate the actual list from `.github/workflows/`). For each: what it
   needs (secrets, data paths), what it publishes, and what breaks silently if
   it fails. Write the matrix to `.planning/WORKFLOW_READINESS.md`.
2. Automate the HF bridge refresh: replace the manual CACHE_BUST bump with a CI
   step (in deploy-web or a new workflow) that commits the bump + pushes to the
   HF Space whenever Gold data changes. Respect the py3.9 constraint.
3. Add a freshness endpoint: `GET /api/health/freshness` in `web/api/` returning
   age-in-hours of newest projections/predictions/rankings artifacts + a
   `stale: bool` per dataset (thresholds: projections 7d preseason / 26h
   in-season Tue, odds 26h). Unit-test with tmp fixture files.
4. Add an external freshness monitor: a tiny GHA cron (every 6h) that curls the
   freshness endpoint on the LIVE backend and opens a GitHub issue (pattern
   already exists in weekly-pipeline.yml) when anything is stale. This catches
   "cron ran but site serves old data" — the class of bug that burned us.
5. Dress rehearsal runbook: `workflow_dispatch` each workflow once (only the
   ones whose secrets exist; SKIP and report the ones blocked on user
   prerequisites). Record pass/fail + logs links in WORKFLOW_READINESS.md.

Acceptance criteria:
- WORKFLOW_READINESS.md exists with all workflows, secret deps, and rehearsal results
- Freshness endpoint live locally with tests green (`python -m pytest tests/web/ -v`)
- CI bridge-refresh step merged; manual CACHE_BUST documented as fallback only
- Monitoring cron merged and produces an issue when pointed at a stale fixture
- Zero regressions: full test suite passes

Out of scope: model changes, new data sources, frontend work, paid infra
migrations (staying on HF free tier is fine for launch — revisit at >100 users).

---

## PLAN 2 — Auth + Payments (Clerk + Stripe, free/premium tiers)

> **STATUS 2026-07-06: DEFERRED by George** — "I want things to be perfect
> before we start worrying about payment." Plan 3 was amended to ship ungated
> (localStorage league connections, no Clerk dependency). Revisit once Plans
> 1 + 3 are live and polished.

**Why #2:** No accounts = no revenue and no user identity for personalization
(Plan 3 depends on this). Clerk dep already present; task is wiring, not design.

**User-owned prerequisites:**
- [ ] Create Clerk app → `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` + `CLERK_SECRET_KEY`
      into Vercel env (`vercel env add`)
- [ ] Create Stripe account + one Product ("Premium", suggest $7.99/mo with
      7-day trial) → `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
      `NEXT_PUBLIC_STRIPE_PRICE_ID` into Vercel env
- [ ] Decide the free/premium split (recommended below, confirm or amend)

**Recommended tier split** (aligns with what's uniquely ours):
- FREE: projections top-50 per position, game predictions, accuracy dashboard,
  news feed. (Acquisition + proof of model quality — the "we beat Sleeper
  consensus" page is the marketing.)
- PREMIUM: full projections + floor/ceiling/conformal bands, AI advisor,
  league-sync tools (Plan 3), lineup optimizer, draft tools, custom-scoring
  re-ranks, rankings multi-compare.

**Subagent brief (suggested: code-implementation-specialist, Sonnet; UI
polish steps can go to Haiku):**

Context: `web/frontend/` (Next.js App Router, Clerk deps in package.json),
`web/frontend/src/app/dashboard/` (12 routes to gate), `web/api/main.py`
(api_key_auth middleware), Vercel skills (`vercel:nextjs`, `vercel:env-vars`).

Steps:
1. Wire Clerk: `ClerkProvider` in `layout.tsx`, middleware protecting
   `/dashboard/*` premium routes, sign-in/up pages, user button in nav. Free
   routes stay public (SEO + acquisition).
2. Stripe subscription: checkout session route handler, customer portal link,
   webhook handler (`checkout.session.completed`,
   `customer.subscription.updated/deleted`) that stamps `premium: true` into
   Clerk `publicMetadata` (single source of truth; no new DB table needed
   at this scale).
3. Gating: server-side check of `publicMetadata.premium` in premium
   layouts/route handlers (never client-only). Free-tier views of premium pages
   show a blurred preview + upgrade CTA (conversion pattern), not a hard 404.
4. Backend: keep the existing X-API-Key middleware as the frontend→backend
   service key (set `API_KEY` on the HF Space + Vercel). Per-user backend auth
   is NOT needed yet — the Next.js layer is the gate. Document this decision in
   `web/DEPLOYMENT.md`.
5. Pricing page at `/pricing` + upgrade CTAs. Use existing WC26 design tokens
   (`--wc-*`) — no new design system.
6. Tests: Playwright e2e — anonymous → free content visible, premium blurred;
   signed-in non-premium → upgrade CTA; (mock) premium → content visible.
   Stripe webhook unit tests with stripe-cli fixtures.

Acceptance criteria:
- Sign-up → checkout (Stripe test mode) → premium unlock works e2e locally
- Webhook cancel/downgrade removes access
- No premium data reachable via client-side bypass (check network tab: premium
  API responses must not be sent to non-premium sessions)
- Existing free pages unchanged for anonymous users; test suite + build green

Out of scope: teams/seats, annual pricing, referral codes, per-user backend API
keys, migrating off the shared service key.

---

## PLAN 3 — League Sync: the Feature Worth Paying For

**Why #3:** "Generic rankings" are free everywhere. "YOUR roster, YOUR scoring,
who to start/drop/target THIS week" is what converts. All hard parts are already
built and tested in `src/` (v8.0 Phases 85-91); this plan is exposure + UI.

**User-owned prerequisites:** none beyond Plan 2 being merged (needs user
identity to persist league connections). Can be built in parallel behind a flag
using a hardcoded test league (use league `1378522447686402048` — George's real
MANTIS league — as the dev fixture).

**Subagent brief (suggested: code-implementation-specialist, Sonnet):**

Context: `src/roster_optimizer.py` (optimal lineup + drop candidates, exact
Sleeper roster_positions), `src/league_scoring.py::score_with_settings`,
`src/sleeper_player_map.py`, `src/sleeper_draft.py`,
`web/api/routers/sleeper_user.py` (existing stub — extend, don't duplicate),
`web/frontend/src/app/dashboard/leagues/page.tsx` (stub page),
`web/api/routers/lineups.py` (existing lineup endpoint patterns).

Steps:
1. Backend endpoints (extend `sleeper_user.py` router):
   - `GET /api/league/{league_id}/overview` — league settings, scoring summary,
     user's roster with projections re-scored via `score_with_settings`
   - `GET /api/league/{league_id}/roster-report?user_id=` — optimal lineup +
     drop candidates via `roster_optimizer` (mirror the logic
     `scripts/draft_live.py --roster-report` already uses; refactor shared
     logic into `src/` if any lives only in the script)
   - `GET /api/league/{league_id}/waivers?user_id=` — top free agents by
     league-scored projection minus user's current starter at that slot
   All read-only Sleeper API calls (no OAuth needed — Sleeper is public), cached
   15 min in-process; validate league_id format; graceful 404 for bad leagues.
2. Persist connections: store connected league_ids + sleeper user_id in Clerk
   `publicMetadata.leagues` (no DB migration; cap 3 leagues/user).
3. Frontend `/dashboard/leagues`: connect flow (enter Sleeper username → pick
   league → confirm roster), then league home = roster report card (optimal
   lineup, bench, drop candidates), waiver targets table, "re-scored under your
   league settings" badge. Premium-gated per Plan 2. WC26 tokens, no new deps.
4. Season-mode switch: preseason shows draft-prep view (keeper value, rookie
   ADP); in-season shows weekly start/sit + waivers. Key off schedule data the
   API already serves.
5. Tests: pytest for the 3 endpoints with recorded Sleeper JSON fixtures (use
   the MANTIS league snapshot — never live-call Sleeper in CI); Playwright for
   the connect flow with mocked API.

Acceptance criteria:
- Connect MANTIS test league → roster report renders with league-scored
  projections matching what `scripts/draft_live.py --roster-report` prints for
  the same inputs (±0.1 pt)
- Waiver targets exclude all rostered players in the league
- Works for a league with custom scoring (TE premium fixture) — numbers differ
  from default PPR, proving `score_with_settings` is actually applied
- All tests green; no live Sleeper calls in CI

Out of scope: Yahoo/ESPN league sync (adapters exist but defer), live draft
mode in the browser (the CLI co-pilot stays the draft-night tool this season),
push notifications, trade analyzer.

---

## Sequencing & delegation summary

| # | Plan | Agent tier | Depends on | Target |
|---|------|-----------|------------|--------|
| 1 | Data freshness + monitoring | general-purpose (Sonnet) | AWS creds + HF token (user) | mid-July |
| 2 | Clerk + Stripe paywall | code-implementation-specialist (Sonnet, Haiku for UI polish) | Clerk/Stripe keys (user) | late July |
| 3 | League sync premium feature | code-implementation-specialist (Sonnet) | Plan 2 merged (or feature-flagged) | early Aug — before draft season |

Run 1 and 2 in parallel (disjoint files). Start 3 behind a flag as soon as 2's
Clerk wiring lands. All three done by early August = paywall live exactly when
fantasy players are drafting and most willing to subscribe.
