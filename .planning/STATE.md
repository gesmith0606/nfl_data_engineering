---
gsd_state_version: 1.0
milestone: launch-2026
milestone_name: Pre-August Paid Launch
status: active
stopped_at: WS1 pipeline-reliability + WS3 UX polish complete (PR #63); WS2 billing go-live is user-owned; dress rehearsal scheduled ~Aug 3-7.
last_updated: "2026-07-18T00:00:00.000Z"
last_activity: 2026-07-18
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
2. **Dress rehearsal ~Aug 3–7:** dispatch all workflows once, verify end-to-end
   (runbook: `WORKFLOW_READINESS.md`).
3. **Ops risks to watch:** Anthropic API credit balance (ran dry 07-09 — set
   billing alerts/auto-reload); concurrent data-commit rebase races.
4. **In-season gates (Sept+):** line-capture verdict by w10 (mean >+0.3,
   n≥150); prop-implied `--props-blend` eval once Sunday snapshots accumulate;
   RB +0.26 consensus gap levers; PFF decision ~Nov.

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
