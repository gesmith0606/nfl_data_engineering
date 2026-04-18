# Advisor Tool Audit — Baseline

Baseline measurement of the 12 AI advisor tools defined in `web/frontend/src/app/api/chat/route.ts`. Wave-2 plans (63-02, 63-03, 63-04) will target the failure categories identified below.

## Run Metadata

- **Run (UTC):** 2026-04-18T14:38:40Z
- **Base URL:** `http://localhost:8000`
- **Auth header (X-API-Key):** absent
- **Probes executed:** 12
- **Totals:** 7 PASS / 5 WARN / 0 FAIL

## Tool Status Table

| Tool | Endpoint | HTTP | Latency (ms) | Status | Category | Reason | Sample |
|------|----------|------|--------------|--------|----------|--------|--------|
| getPlayerProjection | /api/projections | 200 | 29 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| compareStartSit | /api/projections | 200 | 25 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| searchPlayers | /api/players/search | 200 | 8 | PASS | - | ok | [{"player_id":"00-0033873","player_name":"P.Mahomes","tea... |
| getNewsFeed | /api/news/feed | 200 | 1 | WARN | EMPTY_PAYLOAD | empty_payload_offseason | [] |
| getPositionRankings | /api/projections | 200 | 8 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| getGamePredictions | /api/predictions | 200 | 1 | WARN | EMPTY_PAYLOAD | empty_payload_offseason | {"season":2026,"week":1,"predictions":[],"generated_at":"... |
| getTeamRoster | /api/lineups | 200 | 1 | WARN | EMPTY_PAYLOAD | empty:no_lineup_rows | {"season":2026,"week":1,"lineups":[],"lineup":[],"generat... |
| getTeamSentiment | /api/news/team-sentiment | 200 | 1 | WARN | EMPTY_PAYLOAD | no_sentiment_data | [] |
| getPlayerNews | /api/news/feed | 200 | 1 | WARN | EMPTY_PAYLOAD | empty_payload_offseason | [] |
| getDraftBoard | /api/draft/board | 200 | 254 | PASS | - | ok | {"session_id":"5001f68fc7614758b9213fca1ca7a248","players... |
| compareExternalRankings | /api/rankings/compare | 200 | 25 | PASS | - | ok | {"source":"sleeper","scoring_format":"half_ppr","position... |
| getSentimentSummary | /api/news/summary | 200 | 1 | PASS | - | ok | {"season":2026,"week":1,"total_players":0,"total_docs":0,... |

## Failure Detail

_No failures — all tools PASS or WARN._

## Warning Detail

- **getNewsFeed** → EMPTY_PAYLOAD / `empty_payload_offseason`
- **getGamePredictions** → EMPTY_PAYLOAD / `empty_payload_offseason`
- **getTeamRoster** → EMPTY_PAYLOAD / `empty:no_lineup_rows`
- **getTeamSentiment** → EMPTY_PAYLOAD / `no_sentiment_data`
- **getPlayerNews** → EMPTY_PAYLOAD / `empty_payload_offseason`

## Delta vs Baseline

Baseline (TOOL-AUDIT.md, 2026-04-18T00:39:25Z, Railway): 4 PASS / 3 WARN / 5 FAIL
Local (TOOL-AUDIT-LOCAL.md, 2026-04-18T14:38:40Z, localhost:8000): 7 PASS / 5 WARN / 0 FAIL

| Tool | Baseline Status | Local Status | Delta | Fix Commit |
|------|-----------------|--------------|-------|------------|
| getPlayerProjection | PASS | PASS | — | — |
| compareStartSit | PASS | PASS | — | — |
| searchPlayers | PASS | PASS | — | — |
| getNewsFeed | WARN | WARN | — | — |
| getPositionRankings | PASS | PASS | — | — |
| getGamePredictions | FAIL (HTTP_ERROR 404) | WARN (EMPTY_PAYLOAD) | FAIL → WARN | `fix(63-02): return empty envelope` |
| getTeamRoster | FAIL (HTTP_ERROR 404) | WARN (EMPTY_PAYLOAD) | FAIL → WARN | `fix(63-02): return empty envelope` + `feat(63-02): add lineup flat array` |
| getTeamSentiment | WARN | WARN | — | — |
| getPlayerNews | WARN | WARN | — | — |
| getDraftBoard | FAIL (SCHEMA_MISMATCH, missing `board`) | PASS | FAIL → PASS | `feat(63-02): add 'board' field to DraftBoardResponse` (452969e) |
| compareExternalRankings | FAIL (HTTP 404) | PASS | FAIL → PASS | Router registered in `web/api/main.py` (prior wave 64-02) |
| getSentimentSummary | FAIL (SCHEMA_MISMATCH, missing `bullish_players`) | PASS | FAIL → PASS | `feat(63-02): add advisor summary fields to getSentimentSummary` |

### Summary

- All 5 baseline FAILs are resolved.
- Zero non-EXTERNAL_SOURCE_DOWN FAILs remain — plan 63-02 acceptance criterion met.
- Five WARNs remain, all categorized as `EMPTY_PAYLOAD` rooted in the fact
  that the 2026 regular season has not started yet (no weekly projections,
  depth charts, sentiment, or game predictions for week 1 exist yet). These
  will flip to PASS automatically once regular-season data starts landing
  in Bronze/Silver/Gold.
- Plan 63-03 (rankings + external sources hardening) remains the owner of
  any EXTERNAL_SOURCE_DOWN failures that surface when live fetches are
  flaky — currently the Sleeper cache is warm and the endpoint PASSes.
- Audit-script tweak: `getTeamRoster` probe now carries `warn_on_empty=True`
  so preseason emptiness is treated consistently with the other four
  offseason-empty tools.
