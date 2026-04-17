---
gsd_state_version: 1.0
milestone: v6.0
milestone_name: "Website Production Ready + Agent Ecosystem"
status: in_progress
last_updated: "2026-04-17T12:00:00.000Z"
last_activity: 2026-04-17
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-17)

**Core value:** A rich NFL data lake powering both fantasy football projections and game prediction models
**Current focus:** Website production quality + agent ecosystem optimization

## Production Status

| Component | URL | Status |
|-----------|-----|--------|
| Frontend | https://frontend-jet-seven-33.vercel.app | LIVE (2026 preseason data) |
| Backend | https://nfldataengineering-production.up.railway.app | LIVE (Parquet fallback) |
| MAE | 4.92 (2022-2024, half_ppr) | Near v3.2 baseline (4.80) |
| Tests | 1,379+ passing | All green |

## Production Routing

- QB → XGBoost SHIP (bias control for -2.47 heuristic under-projection)
- RB/WR/TE → Pure heuristic (ship gate SKIP — residual models over-correct)

## Active Workstreams

### 1. Models — v4.1 Production Refinement (COMPLETE)

- Phase 54: COMPLETE — unified evaluation pipeline
- Phase 55: COMPLETE — LGB residuals researched (WFCV misleading)
- Phase 56: COMPLETE — Bayesian intervals (78-87% calibration, not in production)
- Phase 57: COMPLETE — Quantile regression (74-82% calibration, not in production)
- v4.1-p3: COMPLETE — QB bias root cause (NaN in _usage_multiplier), heuristic consolidated (3→1)
- v4.1-p4: COMPLETE — Ridge shipped over LGB (+0.35 recovery), PFE tooling built
- v4.1-p5: COMPLETE — Stale routing overrides found and disabled (-0.39 recovery), MAE 4.92

### 2. Website — v4.0/W6/W9

- Phase W1-W5: COMPLETE — FastAPI + Next.js + Vercel + Railway
- Phase W6: COMPLETE — Dark mode, team colors, SEO metadata
- Phase W9-01: COMPLETE — Draft API backend (6 endpoints, 17 tests)
- Phase W9-02/03: NEXT — Draft tool frontend (board UI, config dialog, mock draft)
- AI Advisor: COMPLETE (code) — Gemini 2.5 Flash + Groq fallback, 4 tools, chat UI at /dashboard/advisor
- NEXT: Deploy AI advisor + draft frontend to production

### 3. Sentiment Pipeline — v5.0 (LIVE)

- Phase S1: COMPLETE — Schema, RSS, Sleeper ingestion, player name resolver
- Phase S2: COMPLETE — Claude extraction (optional), rule-based extraction (default)
- Phase SV2-01: COMPLETE — Reddit scraper + rule-based extractor
- Phase SV2-02: COMPLETE — Team sentiment aggregation + game line adjustment
- Phase SV2-03: COMPLETE — Website news feed page, team badges, enhanced player news
- Phase SV2-04: COMPLETE — Daily automation (GitHub Actions cron)
- Phase S3: COMPLETE — Projection engine integration (apply_sentiment_adjustments)
- Pipeline ACTIVATED: 15 players with sentiment multipliers in Gold, API endpoints returning real data
- PlayerNameResolver bug fixed: duplicate column rename was dropping all roster rows

### 4. AI Agent Research (COMPLETE)

- Recommended stack: Gemini 2.5 Flash (free) + Groq Llama 8B (fallback) + Vercel AI SDK v6
- Architecture: tool-calling to FastAPI (not RAG)
- Cost: $0 for 100-500 daily users, ~$5/month at 1000 users
- Research at .planning/research/AI_AGENT_SUMMARY.md

## Current Position

Phase: v6.0 — Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-04-17 — Milestone v6.0 started

## Key Artifacts

| Artifact | Location |
|----------|----------|
| Project | .planning/PROJECT.md |
| Roadmap | .planning/ROADMAP.md |
| PFE Protocol | .planning/phases/v4.1-phase4/NEW_EVAL_PROTOCOL.md |
| MAE Gap Experiments | .planning/phases/v4.1-phase5/MAE_GAP_EXPERIMENTS.md |
| AI Agent Research | .planning/research/AI_AGENT_SUMMARY.md |
| Sentiment v2 Plans | .planning/phases/sentiment-v2/SV2-0*-PLAN.md |
| Draft Tool Plans | .planning/phases/phase-W9/W9-0*-PLAN.md |
| Unstructured Data Arch | .planning/unstructured-data/ARCHITECTURE.md |

## Accumulated Context

### Key Decisions (Current Session)

- [v4.1/P4]: Ridge beats LGB by 0.35 MAE in production. LGB "7-17% improvement" was WFCV artifact.
- [v4.1/P4]: Graph features are net-positive (+0.08 MAE). Feature count 30-60 makes no difference for Ridge.
- [v4.1/P5]: Stale routing overrides (WR/TE/RB forced to HYBRID despite SKIP verdict) caused +0.44 MAE noise. Disabled → 5.31→4.92 MAE.
- [v4.1/P5]: Heuristic-only baseline is 4.87 MAE. QB XGB adds 0.05 for bias control. Ship gate SKIP is correct for RB/WR/TE.
- [v4.1/P5]: QB heuristic has -2.47 systematic under-projection. XGB corrects this but adds noise.
- [Arch]: 3 duplicate heuristic functions CONSOLIDATED to `compute_heuristic_baseline()` in projection_engine.py. Contract test added.
- [Arch]: PFE protocol established. WFCV permanently banned for residual model evaluation.
- [AI]: Gemini 2.5 Flash (free) + Groq fallback. Tool-calling to FastAPI, not RAG. Vercel AI SDK v6.
- [SV2]: Rule-based extraction works without API key. Claude is optional upgrade.
- [SV2]: PlayerNameResolver bug fixed (duplicate column rename dropped all roster rows).
- [W9]: Draft API uses in-memory UUID sessions with 100-session eviction cap.

### Research Flags

- QB heuristic has -2.47 bias — fixing this at projection_engine level would eliminate need for XGB SHIP and reach 4.87 MAE
- Bayesian/Quantile models researched but not in production — could provide better floor/ceiling than hardcoded %
- PFF data ($300-500) would upgrade proxy matchup features to real coverage data
- Walk-forward CV permanently unreliable for residual models — use PFE only

### Blockers/Concerns

- Draft tool frontend (W9-02/03) not yet built
- AI Advisor not yet deployed to production (needs push + Vercel redeploy)
- Groq + Google API keys in .env but not in Railway/Vercel env vars yet
- ANTHROPIC_API_KEY still not set (rule-based extraction working fine as alternative)
- QBR Bronze data missing for 2024+ (upstream nflverse gap)
- 2025 roster data not ingested — limits player name resolution for sentiment

## Next Session Priorities

**Priority 1 — Deploy + Ship:**
- Push all commits to origin (AI advisor, draft API, sentiment activation, MAE fix)
- Set GOOGLE_GENERATIVE_AI_API_KEY + GROQ_API_KEY in Vercel env vars
- Redeploy frontend to Vercel
- Verify AI advisor works live

**Priority 2 — Draft Tool Frontend (W9-02/03):**
- Draft board page with sortable columns, position filters
- Config dialog (teams, pick, scoring, roster format)
- Mock draft simulation UI
- Pick recording + recommendations display

**Priority 3 — Model Improvement:**
- Fix QB heuristic -2.47 bias in projection_engine.py → reach 4.87 MAE
- Ingest 2025 rosters for better sentiment player matching
- Consider Bayesian floor/ceiling for production

**Priority 4 — Polish:**
- Generate more projection data (multiple weeks, not just preseason)
- Run sentiment pipeline on more weeks of data
- Website: add Open Graph images, sitemap.xml

---
*Last updated: 2026-04-12 — MAE recovered to 4.92, AI Advisor built, Sentiment LIVE, Draft API done. Deploy + draft frontend next.*
