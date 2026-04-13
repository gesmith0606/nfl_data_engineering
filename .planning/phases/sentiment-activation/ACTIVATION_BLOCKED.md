# Sentiment Pipeline Activation — BLOCKED

**Date**: 2026-04-07
**Status**: BLOCKED — Missing `ANTHROPIC_API_KEY`

## Problem

The sentiment pipeline (S1–S4) is fully implemented and 47 Bronze documents are ready for
processing (4 RSS files + 1 Sleeper file). However, the `ANTHROPIC_API_KEY` is not present
in the environment or in the `.env` file.

The extraction step in `scripts/process_sentiment.py` calls the Claude API to extract
structured player sentiment signals from raw news text. Without the API key, the pipeline
will fail before producing any Silver or Gold data.

## Evidence

- `ANTHROPIC_API_KEY` is absent from the shell environment.
- `.env` file exists but contains no `ANTHROPIC_API_KEY` entry.
- The key pattern `ANTHROPIC` yielded 0 matches in `.env`.

## What You Need To Do

1. Obtain an Anthropic API key from https://console.anthropic.com/.

2. Add it to the `.env` file in the project root:

   ```
   ANTHROPIC_API_KEY=sk-ant-api03-...
   ```

   Keep the key between the existing config blocks. Do NOT commit `.env` to git.
   The `.gitignore` already excludes it, and the pre-commit hook blocks credential patterns.

3. Verify the key is loaded:

   ```bash
   set -a && source .env && set +a
   echo "Key set: $([ -n "$ANTHROPIC_API_KEY" ] && echo YES || echo NO)"
   ```

4. Then re-run this activation workflow (or ask the agent to pick up from Task 3).

## Pipeline State (ready to run)

| Component | File | Status |
|-----------|------|--------|
| Bronze RSS ingestion | `scripts/ingest_sentiment_rss.py` | Complete |
| Bronze Sleeper ingestion | `scripts/ingest_sentiment_sleeper.py` | Complete |
| Silver extraction (Claude) | `scripts/process_sentiment.py` | Blocked — needs API key |
| Gold aggregation | `scripts/process_sentiment.py` (aggregation step) | Blocked — needs Silver |
| FastAPI endpoints | `web/api/routers/news.py` | Implemented, untested |
| Source modules | `src/sentiment/` | Complete (S1–S4) |

Bronze documents waiting: **47** (data/bronze/news/)

## Next Steps After Adding Key

Run the activation tasks in order:

```bash
# Task 3: Clear processed IDs so all 47 docs get extracted
rm -f data/silver/sentiment/processed_ids.json

# Task 4: Run extraction
source venv/bin/activate
python scripts/process_sentiment.py --season 2025 --week 1 --verbose

# Task 5: Verify Silver signals and Gold parquet exist
find data/silver/sentiment/signals -name "*.json" | head -5
find data/gold/sentiment -name "*.parquet" | head -5

# Task 6: Test FastAPI endpoints (start server separately)
curl "http://localhost:8000/api/news/alerts?season=2025&week=1"
curl "http://localhost:8000/api/news/player/00-0036442?season=2025&week=1"
```
