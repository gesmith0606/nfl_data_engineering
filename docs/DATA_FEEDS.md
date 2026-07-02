# Data Feeds & Refresh Schedule

**Version:** 1.1 — gaps #1–#3 from v1.0 closed same day (rankings cron, reference-data cron, FP partners live tier)
**Last Updated:** July 1, 2026
**Purpose:** Single source of truth for every external data feed the pipeline consumes and when each one refreshes
**Related:** [ARCHITECTURE.md](./ARCHITECTURE.md) | [NFL_DATA_DICTIONARY.md](./NFL_DATA_DICTIONARY.md) | [BRONZE_LAYER_DATA_INVENTORY.md](./BRONZE_LAYER_DATA_INVENTORY.md) | [.github/workflows/](../.github/workflows/)

Feeds fall into four refresh classes: **scheduled** (GitHub Actions cron), **request-time** (fetched live when used, with cache fallback), **manual/on-demand** (CLI only), and **static** (one-time historical backfill, never refreshed).

Maintenance rule: any PR that adds/removes a feed, changes a cron, or changes where data lands MUST update this document.

---

## 1. Scheduled Feeds (GitHub Actions crons)

All cron output is committed to `main` (and mirrored to S3 where noted). ET times shift ±1h across DST; UTC is authoritative.

### Cron calendar at a glance

| UTC | ET | Day | Workflow | What refreshes |
|-----|----|----|----------|----------------|
| 08:00 | 4:00 AM | Tue | `weekly-reference-refresh.yml` | schedules + depth_charts (git-committed TD-08/TD-09 paths), pruned to newest per partition — runs 1h before weekly-pipeline so Silver joins see flexed schedules |
| 09:00 | 5:00 AM | Tue | `weekly-pipeline.yml` | Core nflverse stats → Silver → Gold projections |
| 12:00 | 8:00 AM | Daily | `daily-sentiment.yml` | News/sentiment sources + Sleeper roster patch + external rankings caches (×5) |
| 13:00 | 9:00 AM | Daily | `odds-capture.yml` | Odds API spreads/totals (morning snapshot) |
| 14:00 | 10:00 AM | Tue | `weekly-external-projections.yml` | ESPN / Sleeper / Yahoo-proxy projections |
| 12:00 | 8:00 AM | Sun | `weekly-external-projections.yml` | Same, pre-game pass |
| 14:00 | 10:00 AM | Sun | `odds-capture.yml` | Odds API player props (post-inactives) |
| 15:35 + 16:45 | ~11:35 AM | Sun | `sunday-refresh.yml` | Live injuries re-applied to Gold (dual pass for DST) |
| 21:00 | 5:00 PM | Daily | `odds-capture.yml` | Odds API spreads/totals (closing snapshot) |
| 22:00 | 6:00 PM | Thu | `odds-capture.yml` | Odds API props for TNF |

### weekly-reference-refresh.yml — Tuesdays 08:00 UTC

Closes v1.0 gap #2. Refreshes the two git-committed nflverse reference datasets (no AWS creds needed — local write + git commit with rebase-retry):

| Feed | Why it must stay fresh | Lands in |
|------|------------------------|----------|
| `schedules` | TD-09: `web/Dockerfile` COPYs it; Silver game-context joins; in-season flex re-times | `data/bronze/schedules/season=YYYY/` |
| `depth_charts` | TD-08: PlayerNameResolver in GHA sentiment runs; rookie ranking fallback | `data/bronze/depth_charts/season=YYYY/` |

Season auto-resolves (March+ → current year; Jan–Feb → previous). Each run appends a timestamped parquet, so a prune step keeps only the newest file per season partition, guarded against truncated fetches (newest must be ≥1 KB and ≥30% of the file it replaces). Failure opens a deduped `pipeline-failure` issue.

### weekly-pipeline.yml — Tuesdays 09:00 UTC

The core stat refresh, timed after MNF concludes. Week auto-computed (dispatch inputs → `PIPELINE_WEEK_OVERRIDE` repo var → calendar).

| Feed | Provider | Scope | Failure mode |
|------|----------|-------|--------------|
| `player_weekly` | nflverse (nfl-data-py) | week | blocking |
| `snap_counts` | nflverse | week | blocking |
| `injuries` | nflverse | week | blocking |
| `rosters` (seasonal) | nflverse | season | continue-on-error |
| NGS passing/rushing/receiving | NFL Next Gen Stats via nflverse | season (current + prior) | fail-open |
| PFR weekly pass/rush/rec/def | Pro-Football-Reference via nflverse | season (current + prior) | fail-open |
| ESPN QBR weekly | ESPN via nflverse | season (current + prior) | fail-open (2024+ gap upstream) |
| PBP + participation | nflverse | season (current + prior) | fail-open, 25-min step timeout |

Downstream in the same run: Silver player/advanced/graph transforms → Gold `generate_projections.py --ml` (v4.3 hybrid) with `check_ml_output.py` validation and heuristic fallback + escalation issue on ML failure → previous-week grading report → `sanity_check_projections.py --all` + `check_pipeline_health.py`. Failure opens a GitHub issue (`pipeline-failure` label).

### weekly-external-projections.yml — Tue 14:00 UTC + Sun 12:00 UTC

Competitor projections for benchmarking (Sleeper consensus is the accuracy benchmark the model is graded against). Matrix over three sources, each fail-open (D-06):

| Feed | Provider | Script | Lands in |
|------|----------|--------|----------|
| ESPN weekly projections | ESPN Fantasy API | `ingest_external_projections_espn.py` | `data/bronze/external_projections/espn/` |
| Sleeper weekly projections | Sleeper API | `ingest_external_projections_sleeper.py` | `data/bronze/external_projections/sleeper/` |
| Yahoo-proxy projections | FantasyPros HTML scrape (real Yahoo OAuth deferred, D-03) | `ingest_external_projections_yahoo.py` | `data/bronze/external_projections/yahoo_proxy_fp/` |

Consolidated by `silver_external_projections_transformation.py`; Bronze + Silver committed to git.

### daily-sentiment.yml — daily 12:00 UTC

Runs `daily_sentiment_pipeline.py` over five free news/sentiment sources, then patches rosters:

| Feed | Provider | Access | Lands in |
|------|----------|--------|----------|
| RSS ×5 (espn_news, nfl_news, rotoworld, pro_football_talk, fantasypros) | ESPN / NFL.com / NBC Rotoworld / PFT / FantasyPros | public RSS (`SENTIMENT_CONFIG['rss_feeds']`) | `data/bronze/sentiment/rss/` |
| Reddit ×3 (r/fantasyfootball, r/nfl, r/DynastyFF) | Reddit public JSON | no auth | `data/bronze/sentiment/reddit/` |
| Sleeper trending adds | Sleeper API | no auth | `data/bronze/sentiment/sleeper/` |
| RotoWire NFL news RSS | RotoWire | public RSS | `data/bronze/sentiment/rotowire/` |
| PFT RSS (rule-first envelope) | NBC Sports | public RSS | `data/bronze/sentiment/pft/` |
| Sleeper roster refresh | Sleeper API | no auth | patches team/position in latest Gold preseason parquet (`refresh_rosters.py`, D-05: Gold only) |
| External rankings caches ×5 | see §2 | fail-open step | `refresh_external_rankings.py` — writes `data/external/*.json` envelopes, skip-if-unchanged so commits only happen when ranks move (closes v1.0 gap #1) |

Extraction: Claude Haiku (`claude_primary`) when repo var `ENABLE_LLM_ENRICHMENT=true` + `ANTHROPIC_API_KEY` set; rule-based otherwise. This workflow also hosts the **odds-freshness watchdog** (§5).

### odds-capture.yml — 4 crons

The Odds API v4 (`ODDS_API_KEY`, free tier 500 credits/month). Fail-open on API blips; hard failures open a GitHub issue. Snapshots are append-only — line history cannot be backfilled.

| Cron (UTC) | Job | Feed | Lands in |
|------------|-----|------|----------|
| 13:00 daily | capture | Spreads/totals morning snapshot (opener proxy) | `data/bronze/odds_api/snapshots/` |
| 21:00 daily | capture | Spreads/totals evening snapshot (close proxy) | same |
| 14:00 Sun | capture-props | Player props, Sun+Mon slate (~65-75 credits) | `data/bronze/odds_api/props/` |
| 22:00 Thu | capture-props | Player props, TNF (~5 credits) | same |

### sunday-refresh.yml — Sun 15:35 + 16:45 UTC

`sunday_projection_refresh.py`: fresh injuries/inactives pull via nfl-data-py (Bronze fallback), re-applied to already-published Gold weekly parquets **without re-running the model**. Two passes because 11:30 AM ET inactives shift in UTC across the DST boundary; idempotent and credit-free so both run year-round.

### Event-driven workflows (no feeds)

- `deploy-web.yml` — push to `main`: sanity gates (incl. SANITY-M6 weekly partition gate), Vercel/HF-bridge verification, live-gate, 5-minute auto-rollback window.
- `ci.yml` — PRs + non-main pushes: frontend build, backend pytest, deploy-drift check.

---

## 2. Request-Time Feeds (live fetch on use, cached fallback)

### External rankings (website Compare Sources)

Served by `web/api/services/external_rankings_service.py` with the ADVR-03 chain: live fetch → `data/external/{source}_rankings.json` cache (24h TTL) → Bronze fallback (fantasypros only) → empty-stale envelope. Caches are refreshed **daily at 12:00 UTC** by `daily-sentiment.yml` (canonical envelope, skip-if-unchanged) and additionally at request time; manual CLI: `scripts/refresh_external_rankings.py`.

| Source key | Provider | Access | Notes |
|-----------|----------|--------|-------|
| `sleeper` | Sleeper API `search_rank` | free API | most reliable |
| `fantasypros` (`yahoo` in multi-compare) | FantasyPros **partners API** (primary, no auth); public v2 as legacy fallback | live tier **restored 2026-07-01** via partners endpoint (v2 has required a token since ~2026-06) | Bronze `yahoo_proxy_fp` scrape remains as tier 3 |
| `espn` | ESPN Fantasy API | no auth, percent-owned sort | |
| `draftsharks` | DraftSharks.com HTML (`/rankings/load-rows`) | free, bs4 parse | added 2026-07-01; analysts took #1+#2 of 225 in 2024 FP draft-accuracy contest. No standard board → half-ppr served |
| `ftn` | Jeff Ratcliffe via FantasyPros partners API (`filters=125`) | no auth | added 2026-07-01; #1 multi-year FP draft accuracy. **Empty until he submits season ranks (typically Jul–Aug)** — the daily refresh will pick his board up automatically the day it drops |

### Other live feeds

| Feed | Provider | When fetched | Auth |
|------|----------|--------------|------|
| Sleeper user/league/rosters | Sleeper API | per website request ("My League" views), fail-open | none |
| Sleeper live draft (picks, traded picks, league settings) | Sleeper API | polled during draft night via `/draft-live` (snapshot / `--watch`) | none |
| Yahoo live draft (`draft_results`, players, stat modifiers) | Yahoo Fantasy API | draft night only | OAuth2: `YAHOO_CLIENT_ID`/`YAHOO_CLIENT_SECRET` + `data/yahoo_tokens.json` |
| Sleeper player registry (~5 MB) | Sleeper API | age-based re-fetch by `src/sleeper_player_map.py` | none |
| `player_seasonal` (draft board) | nflverse | request-time by `web/api/routers/draft.py`, cached-projection fallback | none |

ESPN live draft: **NO-GO** (Phase 89) — no API exists; `espn_adapter.py` is gated to `--manual` pick entry.

---

## 3. Manual / On-Demand Feeds (CLI only — no automation)

| Feed | Provider | Script | Typical cadence |
|------|----------|--------|-----------------|
| `schedules` | nflverse | `bronze_ingestion_simple.py --data-type schedules` | start of season / as needed (committed to git, TD-09) |
| `teams` | nflverse | same CLI | rarely changes |
| `player_seasonal` | nflverse | same CLI | offseason |
| `pfr_seasonal` (4 sub-types) | PFR via nflverse | same CLI | offseason |
| `depth_charts` | nflverse | same CLI | as needed (committed to git, TD-08) |
| `draft_picks`, `combine`, `officials` | nflverse | same CLI | annual |
| FTN play-charting (2022+) | FTN via nflverse | `bronze_ftn_ingestion.py` | HOLD verdict (v4.3) — not wired to any workflow |
| College data ×4 (player_stats, usage, teams, draft_picks) | CollegeFootballData.com | `bronze_college_ingestion.py` | offseason/rookie prep; needs `CFBD_API_KEY` |
| Sleeper ADP + projections | Sleeper API | `refresh_adp.py` → `data/adp_latest.csv` | pre-draft (`/draft-prep`) |
| FantasyPros ADP page | FantasyPros | fetch MCP (agent-driven, `/draft-prep` fallback) | pre-draft |
| External rankings ×5 | see §2 | `refresh_external_rankings.py --source all` | ad hoc (also on the daily cron since 2026-07-01) |

## 4. Static Feeds (frozen — never refresh)

| Feed | Provider | Coverage | Note |
|------|----------|----------|------|
| Historical odds archive | FinnedAI sportsbookreview-scraper (GitHub raw JSON) | 2016–2021 only | `bronze_odds_ingestion.py`; source frozen — this is why market features are NaN for 2022+ training windows |

---

## 5. Monitoring & Watchdogs

| Guard | Lives in | Fires when |
|-------|----------|------------|
| Odds freshness watchdog | `daily-sentiment.yml` (independent of the odds cron — a dead cron can't monitor itself) | newest odds snapshot >36h old → deduped GitHub issue; skips Mar–May dead zone |
| Weekly pipeline failure issue | `weekly-pipeline.yml` | any job failure/cancel |
| ML fallback escalation | `weekly-pipeline.yml` | `--ml` output invalid → deletes artifact, re-runs heuristic, opens deduped issue |
| Sentiment pipeline failure issue | `daily-sentiment.yml` | job failure |
| Odds capture failure issue | `odds-capture.yml` | hard failure (API blips are fail-open) |
| Reference refresh failure issue | `weekly-reference-refresh.yml` | schedules/depth_charts ingest or push failure (deduped per episode) |
| Sanity gates (SANITY + M6) + live gate + auto-rollback | `deploy-web.yml` | pre/post-deploy projection sanity failures |
| S3/local freshness | `check_pipeline_health.py` (in weekly pipeline; also `/health-check`) | missing/undersized partitions |

## 6. Required Credentials by Feed

| Env key | Needed by | Where set |
|---------|-----------|-----------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` | S3 mirrors (weekly pipeline) | GHA secrets (local creds expired 2026-03 — local-first) |
| `ODDS_API_KEY` | odds + props capture | GHA secret (free tier) |
| `ANTHROPIC_API_KEY` | Claude sentiment extraction | GHA secret; **not set in Railway** (website sentiment blocked) |
| `CFBD_API_KEY` | college ingestion | `.env` (local) |
| `YAHOO_CLIENT_ID` / `YAHOO_CLIENT_SECRET` | Yahoo live draft | `.env` + `data/yahoo_tokens.json` (gitignored) |
| — (no auth) | nflverse, Sleeper, ESPN, FantasyPros public/partners, Draft Sharks, RSS, Reddit | n/a |

## 7. Known Gaps

Open:

- **weekly-pipeline blocked on AWS credentials — NEEDS USER ACTION.** Discovered 2026-07-02: all four June scheduled runs failed at `configure-aws-credentials` ("Could not load credentials from any providers") before any ingestion ran, and the failures were silent because the workflow had no `issues: write` permission (fixed 2026-07-02 — future failures will open issues). Fix requires either setting valid `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` repo secrets or converting the workflow to the local-first + git-commit pattern the other workflows use. Target: August dress rehearsal at the latest.
- **ESPN QBR 2024+ missing upstream** (nflverse gap) — re-verified 2026-07-01 (`import_qbr` returns 0 rows for 2024 and 2025); nothing actionable on our side, models handle NaN. Re-check occasionally.
- **FTN rankings empty until Ratcliffe submits 2026 ranks** (~Jul–Aug) — by design, not a defect; auto-populates via the daily refresh the day his board drops.

Closed in v1.1 (2026-07-01):

- ~~External rankings caches had no scheduled refresh~~ → daily 12:00 UTC step in `daily-sentiment.yml`, envelope format + skip-if-unchanged commits.
- ~~`schedules` / `depth_charts` manual-only~~ → `weekly-reference-refresh.yml` (Tue 08:00 UTC) with prune-to-latest + truncation guard.
- ~~FantasyPros v2 auth token killed the ECR live tier~~ → partners API (`partners.fantasypros.com/api/v1/consensus-rankings.php`, no auth) is now the primary live tier; v2 kept as legacy fallback, Bronze scrape as tier 3.
