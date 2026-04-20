# Advisor Tool Audit — FINAL (Post-Deploy Re-Audit)

Post-deploy re-audit of all 12 AI advisor tools defined in `web/frontend/src/app/api/chat/route.ts`. This is the SHIP gate for phase 63 — every fix from plans 63-02, 63-03, and 63-04 has been deployed to Railway, and this audit confirms the live stack matches the local audit from 63-02.

## Run Metadata

- **Run (UTC):** 2026-04-20T00:29:50Z
- **Base URL:** `https://nfldataengineering-production.up.railway.app`
- **Auth header (X-API-Key):** absent
- **Probes executed:** 12
- **Totals:** 7 PASS / 5 WARN / 0 FAIL
- **Backend commit deployed:** `d06e7ae` (post-63-02/03/04 fixes + sanity guard)
- **Frontend commit deployed:** `030fb80` (post-63-05 persistent widget)

## Tool Status Table

| Tool | Endpoint | HTTP | Latency (ms) | Status | Category | Reason | Sample |
|------|----------|------|--------------|--------|----------|--------|--------|
| getPlayerProjection | /api/projections | 200 | 545 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| compareStartSit | /api/projections | 200 | 473 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| searchPlayers | /api/players/search | 200 | 218 | PASS | - | ok | [{"player_id":"00-0033873","player_name":"P.Mahomes","tea... |
| getNewsFeed | /api/news/feed | 200 | 191 | WARN | EMPTY_PAYLOAD | empty_payload_offseason | [] |
| getPositionRankings | /api/projections | 200 | 126 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| getGamePredictions | /api/predictions | 200 | 108 | WARN | EMPTY_PAYLOAD | empty_payload_offseason | {"season":2026,"week":1,"predictions":[],"generated_at":"... |
| getTeamRoster | /api/lineups | 200 | 117 | WARN | EMPTY_PAYLOAD | empty:no_lineup_rows | {"season":2026,"week":1,"lineups":[],"lineup":[],"generat... |
| getTeamSentiment | /api/news/team-sentiment | 200 | 112 | WARN | EMPTY_PAYLOAD | no_sentiment_data | [] |
| getPlayerNews | /api/news/feed | 200 | 111 | WARN | EMPTY_PAYLOAD | empty_payload_offseason | [] |
| getDraftBoard | /api/draft/board | 200 | 1199 | PASS | - | ok | {"session_id":"979ab0db2d314c879b797e202159d64f","players... |
| compareExternalRankings | /api/rankings/compare | 200 | 654 | PASS | - | ok | {"source":"sleeper","scoring_format":"half_ppr","position... |
| getSentimentSummary | /api/news/summary | 200 | 109 | PASS | - | ok | {"season":2026,"week":1,"total_players":0,"total_docs":0,... |

## Failure Detail

_No failures — all tools PASS or WARN._

## Warning Detail

All 5 WARNs are `EMPTY_PAYLOAD` rooted in the 2026 regular season not having started yet. Each tool carries `warn_on_empty=True` in the probe registry so an empty offseason envelope is treated as a WARN rather than a FAIL. These will automatically flip to PASS once Bronze/Silver/Gold pipelines start landing regular-season 2026 data.

- **getNewsFeed** → EMPTY_PAYLOAD / `empty_payload_offseason` — RSS/Sleeper feeds haven't fired yet for 2026 season
- **getGamePredictions** → EMPTY_PAYLOAD / `empty_payload_offseason` — no game prediction parquet for 2026 wk 1
- **getTeamRoster** → EMPTY_PAYLOAD / `empty:no_lineup_rows` — depth charts unavailable for preseason week 1 (team=KC probed)
- **getTeamSentiment** → EMPTY_PAYLOAD / `no_sentiment_data` — no processed sentiment signals for 2026 wk 1
- **getPlayerNews** → EMPTY_PAYLOAD / `empty_payload_offseason` — same underlying RSS/Sleeper state as getNewsFeed

## Verdict

**PASS — phase 63 can SHIP.**

- 0 FAIL (down from 5 in baseline)
- 5 WARN, all documented as offseason-empty and acceptable per the plan's `warn_on_empty` contract
- Zero HTTP errors, zero schema mismatches, zero transport failures
- No EXTERNAL_SOURCE_DOWN — `compareExternalRankings` returns live Sleeper data (654ms latency)
- All three plans in wave 2 (63-02 schema + envelopes, 63-03 rankings cache, 63-04 Gold grounding) demonstrably shipped and held up under live probe

Meets the SHIP gate criterion from `63-06-PLAN.md`:

> PASS if 0 FAIL and WARNs are documented (preseason-empty or cache-stale).

## Delta vs Baseline

Baseline (`TOOL-AUDIT.md`, 2026-04-18T00:39:25Z, Railway): **4 PASS / 3 WARN / 5 FAIL**
Final    (this file,         2026-04-20T00:29:50Z, Railway): **7 PASS / 5 WARN / 0 FAIL**

Net delta: **+3 PASS, +2 WARN, -5 FAIL**.

| Tool | Baseline Status | Final Status | Delta | Fix Plan / Commit |
|------|-----------------|--------------|-------|-------------------|
| getPlayerProjection | PASS | PASS | — | — |
| compareStartSit | PASS | PASS | — | — |
| searchPlayers | PASS | PASS | — | — |
| getNewsFeed | WARN | WARN | — | — (preseason empty) |
| getPositionRankings | PASS | PASS | — | 63-04 added meta.data_as_of (non-regression) |
| getGamePredictions | FAIL (404) | WARN (empty envelope) | **FAIL → WARN** | 63-02 `8a09e2b` fix: empty envelope on missing data |
| getTeamRoster | FAIL (404) | WARN (empty envelope) | **FAIL → WARN** | 63-02 `8a09e2b` + `6e0f275` empty envelope + flat `lineup` array |
| getTeamSentiment | WARN | WARN | — | — (preseason empty) |
| getPlayerNews | WARN | WARN | — | — (preseason empty) |
| getDraftBoard | FAIL (schema: missing `board`) | PASS | **FAIL → PASS** | 63-02 `452969e` feat: add `board` field to DraftBoardResponse |
| compareExternalRankings | FAIL (404 router unreg) | PASS | **FAIL → PASS** | 63-02 router registration + 63-03 `c372d77` cache-first fallback |
| getSentimentSummary | FAIL (schema: missing advisor fields) | PASS | **FAIL → PASS** | 63-02 `efb614d` feat: add advisor summary fields |

### Delta vs TOOL-AUDIT-LOCAL.md

Local audit (2026-04-18T14:38:40Z, `localhost:8000`): 7 PASS / 5 WARN / 0 FAIL.
Final audit (2026-04-20T00:29:50Z, Railway):          7 PASS / 5 WARN / 0 FAIL.

**Identical per-tool verdicts.** The Railway deploy has picked up every local fix exactly as expected; no production divergence. Latencies are higher on Railway (network round-trip + cold containers) — the Draft board endpoint is the slowest at 1.2s, within the audit script's 15s timeout.

## Raw stdout

```
2026-04-19 20:29:46,202 INFO audit_advisor_tools: Base URL: https://nfldataengineering-production.up.railway.app
2026-04-19 20:29:46,202 INFO audit_advisor_tools: Auth header: absent
2026-04-19 20:29:46,400 INFO audit_advisor_tools: Probing getPlayerProjection → /api/projections
2026-04-19 20:29:46,747 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/projections?season=2026&week=1&scoring=half_ppr "HTTP/1.1 200 "
2026-04-19 20:29:46,946 INFO audit_advisor_tools: Probing compareStartSit → /api/projections
2026-04-19 20:29:47,181 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/projections?season=2026&week=1&scoring=half_ppr "HTTP/1.1 200 "
2026-04-19 20:29:47,420 INFO audit_advisor_tools: Probing searchPlayers → /api/players/search
2026-04-19 20:29:47,638 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/players/search?q=mahom "HTTP/1.1 200 "
2026-04-19 20:29:47,639 INFO audit_advisor_tools: Probing getNewsFeed → /api/news/feed
2026-04-19 20:29:47,831 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/news/feed?season=2026&limit=10 "HTTP/1.1 200 "
2026-04-19 20:29:47,831 INFO audit_advisor_tools: Probing getPositionRankings → /api/projections
2026-04-19 20:29:47,957 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/projections?season=2026&week=1&position=RB&limit=10 "HTTP/1.1 200 "
2026-04-19 20:29:47,958 INFO audit_advisor_tools: Probing getGamePredictions → /api/predictions
2026-04-19 20:29:48,065 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/predictions?season=2026&week=1 "HTTP/1.1 200 "
2026-04-19 20:29:48,066 INFO audit_advisor_tools: Probing getTeamRoster → /api/lineups
2026-04-19 20:29:48,183 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/lineups?team=KC&season=2026&week=1&scoring=half_ppr "HTTP/1.1 200 "
2026-04-19 20:29:48,184 INFO audit_advisor_tools: Probing getTeamSentiment → /api/news/team-sentiment
2026-04-19 20:29:48,296 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/news/team-sentiment?season=2026&week=1 "HTTP/1.1 200 "
2026-04-19 20:29:48,297 INFO audit_advisor_tools: Probing getPlayerNews → /api/news/feed
2026-04-19 20:29:48,408 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/news/feed?season=2026&limit=25 "HTTP/1.1 200 "
2026-04-19 20:29:48,409 INFO audit_advisor_tools: Probing getDraftBoard → /api/draft/board
2026-04-19 20:29:49,281 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/draft/board?scoring=half_ppr "HTTP/1.1 200 "
2026-04-19 20:29:49,609 INFO audit_advisor_tools: Probing compareExternalRankings → /api/rankings/compare
2026-04-19 20:29:50,262 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/rankings/compare?source=sleeper&scoring=half_ppr&limit=20 "HTTP/1.1 200 "
2026-04-19 20:29:50,263 INFO audit_advisor_tools: Probing getSentimentSummary → /api/news/summary
2026-04-19 20:29:50,372 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/news/summary?season=2026&week=1 "HTTP/1.1 200 "
2026-04-19 20:29:50,375 INFO audit_advisor_tools: Wrote /Users/georgesmith/repos/nfl_data_engineering/.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.md
AUDIT: 7 PASS / 5 WARN / 0 FAIL
```
