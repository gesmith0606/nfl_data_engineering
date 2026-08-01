---
gsd_state_version: 1.0
milestone: launch-2026
milestone_name: Pre-August Paid Launch
status: active
stopped_at: Phase 81 live audit found 6 broken dashboard routes (draft CRASH + 5 suspended voids); P0 fixed in PR #73, remediation + advisor-tools + polish PRs in flight — merges pending user; billing go-live still user-owned.
last_updated: "2026-08-01T00:00:00.000Z"
last_activity: 2026-08-01
---

# Project State

> **Source of truth is `CLAUDE.md` (Status section) + git log.** This file is a
> thin launch-window snapshot; it went stale twice (2026-05-15, 2026-07-18
> reconciliations) when kept detailed — keep it thin.

## Project Reference

**Core value:** A rich, well-modeled NFL data lake powering fantasy projections
(beats Sleeper consensus overall), game predictions, and a production website +
AI advisor ecosystem — monetized at $7.99/mo (7-day trial) from August draft
season.

**Current focus:** Pre-August paid launch. Plan of record: launch-ready + paid
by **Aug 1**; full workflow dress rehearsal **~Aug 3–7** (post-HOF weekend,
runbook in `WORKFLOW_READINESS.md`).

## Current Position (2026-07-18)

- **Shipped:** v8.0 live draft co-pilot → v8.1 production launch (league sync,
  freshness monitor, sentiment in prod) → v8.2 model enrichment + repo
  hardening (consensus anchor, props-blend machinery, UC1–UC3, ops dashboard,
  3,009 tests). Clerk+Stripe billing code landed (PRs #58/#60), env-flagged
  OFF. PWA + roster alerts (#61), my-week hub (#62), H-4 roster-confirm
  identity + doc reconciliation (#63).
- **Deployment:** Vercel frontend + **HF Spaces** backend
  (`gesmith0606-nfl-data-api.hf.space`). **Railway is DEAD** (trial expired
  May 2026) — never point env vars at it. ANTHROPIC_API_KEY auto-syncs to HF
  runtime via deploy-web.
- **Workflows:** 9 GitHub Actions, all healthy as of 2026-07-18. June/early-July
  failures fully diagnosed: AWS-creds outage (fixed, plus `issues: write` so
  failure-notify works), injuries season-range bug (fixed 07-02), one Anthropic
  credit-exhaustion + data-commit rebase race (07-09, recovered).

## Open threads

1. **Billing go-live (user-owned):** execute `docs/BILLING_LAUNCH.md` — Clerk
   prod app, Stripe $7.99/mo product, 7 Vercel env vars, §5 QA, §4 launch order.
   Plan of record was paid-by-Aug-1 — now the critical path.
2. **Dress rehearsal ~Aug 3–7 (scope narrowed 07-30):** all 8 workflows have
   green runs within the last 6 days (see WORKFLOW_READINESS.md addendum);
   remaining value is weekly-pipeline `--ml` against live preseason data +
   sunday-refresh non-no-op injury path.
3. **Ops risks to watch:** Anthropic API credit balance (ran dry 07-09 — set
   billing alerts/auto-reload); concurrent data-commit rebase races.
   RESOLVED 07-30: HF Space staleness (issue #71) — bot data commits never
   trigger deploy-web's push paths (GITHUB_TOKEN suppression), Space drifted
   11 days stale; fixed with a daily 14:30 UTC cron on deploy-web.yml.
4. **In-season gates (Sept+):** line-capture verdict by w10 (mean >+0.3,
   n≥150); prop-implied `--props-blend` eval once Sunday snapshots accumulate;
   RB +0.26 consensus gap levers; PFF decision ~Nov.
5. **Site-fix sprint 2026-08-01 (Phase 81 executed):** live audit found 6 of
   11 dashboard routes broken in prod — /dashboard/draft CRASHED for all
   visitors since ~07-19 (presets envelope, fixed in **PR #73**) and
   games/rankings/players/lineups/matchups render unresolved-Suspense voids
   (remediation branch `fix/dashboard-suspended-routes`). Audit doc:
   `.planning/milestones/v7.2-phases/81-dashboard-feature-audit/UX-01-AUDIT.md`.
   Also in flight: **PR #72** advisor tools (Phase 83 TOOL-01/02),
   frontend polish PR (font tokens, skeletons, demo-form removal, badge cap).
   **User actions: merge the PRs** (gh pr merge is permission-gated for the
   agent) in order #73 → suspended-routes → #72 → polish, resolving small
   conflicts in lineup-view/player-detail if any. Process gap recorded: HTTP
   live gates can't see client-side crashes — hydrated-content sentinel is a
   follow-up candidate.
6. **Push-v2 (blocked on operator infra):** delivery stub is intentionally
   OFF; activation checklist (KV store + VAPID keys + env) documented in
   `docs/PUSH_NOTIFICATIONS.md`. Sentiment-multiplier "wiring" note: already
   BUILT as opt-in `--use-sentiment` (event-based, per Phase 61 D-03);
   default-ON remains gated on in-season eval like `--props-blend`.

## Deferred (unchanged)

| Category | Item | Status |
|----------|------|--------|
| Data     | PFF paid data | decision ~Nov (must beat free ceiling ≥3×) |
| Data     | Neo4j Aura cloud graph | post-season |
| Data     | S3 sync of local data | backlog |
| Sentiment| Twitter/X + ESPN/CBS paid sources | backlog |
| Auth     | Sleeper OAuth / multi-user persistence | backlog |
| Repo     | Packaging normalization + god-module splits | offseason |
| Deploy   | Slim HF Docker image (data baked into image) | backlog |
