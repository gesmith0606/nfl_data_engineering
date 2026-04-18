# Advisor Tool Audit — Baseline

Baseline measurement of the 12 AI advisor tools defined in `web/frontend/src/app/api/chat/route.ts`. Wave-2 plans (63-02, 63-03, 63-04) will target the failure categories identified below.

## Run Metadata

- **Run (UTC):** 2026-04-18T00:39:25Z
- **Base URL:** `https://nfldataengineering-production.up.railway.app`
- **Auth header (X-API-Key):** absent
- **Probes executed:** 12
- **Totals:** 4 PASS / 3 WARN / 5 FAIL

## Tool Status Table

| Tool | Endpoint | HTTP | Latency (ms) | Status | Category | Reason | Sample |
|------|----------|------|--------------|--------|----------|--------|--------|
| getPlayerProjection | /api/projections | 200 | 607 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| compareStartSit | /api/projections | 200 | 463 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| searchPlayers | /api/players/search | 200 | 121 | PASS | - | ok | [{"player_id":"00-0033873","player_name":"P.Mahomes","tea... |
| getNewsFeed | /api/news/feed | 200 | 105 | WARN | EMPTY_PAYLOAD | empty_payload_offseason | [] |
| getPositionRankings | /api/projections | 200 | 118 | PASS | - | ok | {"season":2026,"week":1,"scoring_format":"half_ppr","proj... |
| getGamePredictions | /api/predictions | 404 | 188 | FAIL | HTTP_ERROR | http_status_404 | {"detail":"No prediction data for season=2026 week=1"} |
| getTeamRoster | /api/lineups | 404 | 115 | FAIL | HTTP_ERROR | http_status_404 | {"detail":"No lineup data for season=2026 week=1 team=KC"} |
| getTeamSentiment | /api/news/team-sentiment | 200 | 101 | WARN | EMPTY_PAYLOAD | no_sentiment_data | [] |
| getPlayerNews | /api/news/feed | 200 | 103 | WARN | EMPTY_PAYLOAD | empty_payload_offseason | [] |
| getDraftBoard | /api/draft/board | 200 | 1055 | FAIL | SCHEMA_MISMATCH | schema:missing_board_key | {"session_id":"d5a3d9de3da64e95989e6607fed14609","players... |
| compareExternalRankings | /api/rankings/compare | 404 | 102 | FAIL | HTTP_ERROR | http_status_404 | {"detail":"Not Found"} |
| getSentimentSummary | /api/news/summary | 200 | 105 | FAIL | SCHEMA_MISMATCH | schema:missing_fields:['bearish_players', 'bull... | {"season":2026,"week":1,"total_players":0,"total_docs":0,... |

## Failure Detail

### getGamePredictions — HTTP_ERROR
- **Endpoint:** `/api/predictions`
- **Params:** `{'season': '2026', 'week': '1'}`
- **HTTP:** 404 (latency 188ms)
- **Body shape:** `<none>`
- **Reason:** `http_status_404`
- **Body sample (500 chars):**

```json
{"detail":"No prediction data for season=2026 week=1"}
```

### getTeamRoster — HTTP_ERROR
- **Endpoint:** `/api/lineups`
- **Params:** `{'team': 'KC', 'season': '2026', 'week': '1', 'scoring': 'half_ppr'}`
- **HTTP:** 404 (latency 115ms)
- **Body shape:** `<none>`
- **Reason:** `http_status_404`
- **Body sample (500 chars):**

```json
{"detail":"No lineup data for season=2026 week=1 team=KC"}
```

### getDraftBoard — SCHEMA_MISMATCH
- **Endpoint:** `/api/draft/board`
- **Params:** `{'scoring': 'half_ppr'}`
- **HTTP:** 200 (latency 1055ms)
- **Body shape:** `{my_pick_count,my_roster,n_teams,picks_taken,players,remaining_needs,roster_format,scoring_format,session_id}`
- **Reason:** `schema:missing_board_key`
- **Body sample (500 chars):**

```json
{"session_id":"d5a3d9de3da64e95989e6607fed14609","players":[{"player_id":"00-0034796","player_name":"Lamar Jackson","position":"QB","team":"BAL","projected_points":483.1,"model_rank":1,"adp_rank":null
```

### compareExternalRankings — HTTP_ERROR
- **Endpoint:** `/api/rankings/compare`
- **Params:** `{'source': 'sleeper', 'scoring': 'half_ppr', 'limit': '20'}`
- **HTTP:** 404 (latency 102ms)
- **Body shape:** `<none>`
- **Reason:** `http_status_404`
- **Body sample (500 chars):**

```json
{"detail":"Not Found"}
```

### getSentimentSummary — SCHEMA_MISMATCH
- **Endpoint:** `/api/news/summary`
- **Params:** `{'season': '2026', 'week': '1'}`
- **HTTP:** 200 (latency 105ms)
- **Body shape:** `{season,sentiment_distribution,sources,top_negative,top_positive,total_docs,total_players,week}`
- **Reason:** `schema:missing_fields:['bearish_players', 'bullish_players', 'total_articles']`
- **Body sample (500 chars):**

```json
{"season":2026,"week":1,"total_players":0,"total_docs":0,"sources":{},"top_positive":[],"top_negative":[],"sentiment_distribution":{"positive":0,"neutral":0,"negative":0}}
```

## Warning Detail

- **getNewsFeed** → EMPTY_PAYLOAD / `empty_payload_offseason`
- **getTeamSentiment** → EMPTY_PAYLOAD / `no_sentiment_data`
- **getPlayerNews** → EMPTY_PAYLOAD / `empty_payload_offseason`

## Raw stdout

```
2026-04-17 20:39:22,211 INFO audit_advisor_tools: Base URL: https://nfldataengineering-production.up.railway.app
2026-04-17 20:39:22,211 INFO audit_advisor_tools: Auth header: absent
2026-04-17 20:39:22,398 INFO audit_advisor_tools: Probing getPlayerProjection → /api/projections
2026-04-17 20:39:22,767 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/projections?season=2026&week=1&scoring=half_ppr "HTTP/1.1 200 "
2026-04-17 20:39:23,005 INFO audit_advisor_tools: Probing compareStartSit → /api/projections
2026-04-17 20:39:23,230 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/projections?season=2026&week=1&scoring=half_ppr "HTTP/1.1 200 "
2026-04-17 20:39:23,469 INFO audit_advisor_tools: Probing searchPlayers → /api/players/search
2026-04-17 20:39:23,590 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/players/search?q=mahom "HTTP/1.1 200 "
2026-04-17 20:39:23,591 INFO audit_advisor_tools: Probing getNewsFeed → /api/news/feed
2026-04-17 20:39:23,695 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/news/feed?season=2026&limit=10 "HTTP/1.1 200 "
2026-04-17 20:39:23,696 INFO audit_advisor_tools: Probing getPositionRankings → /api/projections
2026-04-17 20:39:23,812 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/projections?season=2026&week=1&position=RB&limit=10 "HTTP/1.1 200 "
2026-04-17 20:39:23,814 INFO audit_advisor_tools: Probing getGamePredictions → /api/predictions
2026-04-17 20:39:24,003 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/predictions?season=2026&week=1 "HTTP/1.1 404 "
2026-04-17 20:39:24,003 INFO audit_advisor_tools: Probing getTeamRoster → /api/lineups
2026-04-17 20:39:24,118 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/lineups?team=KC&season=2026&week=1&scoring=half_ppr "HTTP/1.1 404 "
2026-04-17 20:39:24,118 INFO audit_advisor_tools: Probing getTeamSentiment → /api/news/team-sentiment
2026-04-17 20:39:24,219 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/news/team-sentiment?season=2026&week=1 "HTTP/1.1 200 "
2026-04-17 20:39:24,219 INFO audit_advisor_tools: Probing getPlayerNews → /api/news/feed
2026-04-17 20:39:24,322 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/news/feed?season=2026&limit=25 "HTTP/1.1 200 "
2026-04-17 20:39:24,322 INFO audit_advisor_tools: Probing getDraftBoard → /api/draft/board
2026-04-17 20:39:25,138 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/draft/board?scoring=half_ppr "HTTP/1.1 200 "
2026-04-17 20:39:25,378 INFO audit_advisor_tools: Probing compareExternalRankings → /api/rankings/compare
2026-04-17 20:39:25,480 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/rankings/compare?source=sleeper&scoring=half_ppr&limit=20 "HTTP/1.1 404 "
2026-04-17 20:39:25,480 INFO audit_advisor_tools: Probing getSentimentSummary → /api/news/summary
2026-04-17 20:39:25,586 INFO httpx: HTTP Request: GET https://nfldataengineering-production.up.railway.app/api/news/summary?season=2026&week=1 "HTTP/1.1 200 "
2026-04-17 20:39:25,587 INFO audit_advisor_tools: Wrote /Users/georgesmith/repos/nfl_data_engineering/.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.md
AUDIT: 4 PASS / 3 WARN / 5 FAIL
```
