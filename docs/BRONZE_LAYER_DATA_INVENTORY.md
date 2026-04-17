# Bronze Layer Data Inventory

**Generated:** 2026-04-14 (updated)
**Total Files:** 509+
**Total Size:** ~146 MB

| Data Type | Files | Size (MB) | Seasons | Columns | Last Updated |
|-----------|-------|-----------|---------|---------|--------------|
| combine | 26 | 0.72 | 2000-2025 | 18 | 2026-03-09 |
| depth_charts | 25 | 11.89 | 2001-2025 | 15 | 2026-03-09 |
| draft_picks | 26 | 0.99 | 2000-2025 | 36 | 2026-03-09 |
| games | 6 | 0.31 | 2020-2025 | 50 | 2026-03-06 |
| odds | 1 | ~0.02 | 2020 | 14 | 2026-03-27 |
| ngs/passing | 10 | 0.89 | 2016-2025 | 29 | 2026-03-09 |
| ngs/receiving | 10 | 1.28 | 2016-2025 | 23 | 2026-03-09 |
| ngs/rushing | 10 | 0.53 | 2016-2025 | 22 | 2026-03-09 |
| officials | 10 | 0.12 | 2016-2025 | 5 | 2026-03-16 |
| pbp | 20 | 103.99 | 2016-2025 | 140 | 2026-03-16 |
| pfr/seasonal/def | 8 | 0.51 | 2018-2025 | 30 | 2026-03-09 |
| pfr/seasonal/pass | 8 | 0.24 | 2018-2025 | 37 | 2026-03-09 |
| pfr/seasonal/rec | 8 | 0.33 | 2018-2025 | 25 | 2026-03-09 |
| pfr/seasonal/rush | 8 | 0.20 | 2018-2025 | 19 | 2026-03-09 |
| pfr/weekly/def | 8 | 1.22 | 2018-2025 | 29 | 2026-03-09 |
| pfr/weekly/pass | 8 | 0.25 | 2018-2025 | 24 | 2026-03-09 |
| pfr/weekly/rec | 8 | 0.42 | 2018-2025 | 17 | 2026-03-09 |
| pfr/weekly/rush | 8 | 0.35 | 2018-2025 | 16 | 2026-03-09 |
| players/injuries | 9 | 1.10 | 2016-2024 | 18 | 2026-03-11 |
| players/rosters | 10 | 5.49 | 2016-2025 | 39 | 2026-03-11 |
| players/seasonal | 10 | 1.49 | 2016-2025 | 60 | 2026-03-12 |
| players/snaps | 215 | 8.60 | 2016-2025 | 16 | 2026-03-11 |
| players/weekly | 10 | 3.13 | 2016-2025 | 55 | 2026-03-12 |
| qbr | 36 | 1.04 | 2006-2023 | 23 | 2026-03-09 |
| schedules | 10 | 0.49 | 2016-2025 | 46 | 2026-03-11 |
| teams | 1 | 0.01 | N/A | 16 | 2026-03-09 |

### Sentiment & External Data (v4.2)

| Data Type | Path | Source | Format | Updated |
|-----------|------|--------|--------|---------|
| RSS articles | `data/bronze/sentiment/rss/` | 5 RSS feeds (Rotoworld, FantasyPros, PFF, ESPN, NFL.com) | JSON | Daily (GHA cron) |
| Sleeper trending | `data/bronze/sentiment/sleeper/` | Sleeper trending players API | JSON | Daily (GHA cron) |
| External rankings | `data/external/` | Sleeper ADP, FantasyPros ECR, ESPN rankings | JSON (24h TTL) | On demand / daily |

**Notes:**
- Sentiment Bronze data is ingested by `scripts/daily_sentiment_pipeline.py` (orchestrates RSS + Sleeper + roster refresh) or individual scripts: `ingest_sentiment_rss.py`, `ingest_sentiment_sleeper.py`
- External rankings cached as `data/external/sleeper_rankings.json`, `data/external/fantasypros_rankings.json`, `data/external/espn_rankings.json` with 24-hour TTL
- Rankings refreshed by `scripts/refresh_external_rankings.py --source all`
- Reddit ingestion (`data/bronze/sentiment/reddit/`) is scaffolded but not yet active
- Daily GHA cron (`.github/workflows/daily-sentiment.yml`) runs at 12:00 UTC: sentiment pipeline + roster refresh + auto-commit
