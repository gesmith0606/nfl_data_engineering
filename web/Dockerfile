FROM python:3.9-slim

# Cache-buster: bumped 2026-05-01 to force Railway to re-run all COPY layers
# instead of importing a stale cached image. Change this ARG to invalidate cache.
ARG CACHE_BUST=2026-05-01-01

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY web/requirements.txt ./web/requirements.txt
COPY web/api/serverless/requirements.txt ./web/api/serverless/requirements.txt
RUN pip install --no-cache-dir -r web/api/serverless/requirements.txt

# Copy application code
COPY src/ ./src/
COPY web/api/ ./web/api/
COPY web/__init__.py ./web/__init__.py

# Copy Gold Parquet data for Parquet-mode fallback.
# When DATABASE_URL is set and reachable, these files are ignored.
# When DATABASE_URL is absent or unreachable, the API reads from here.
COPY data/gold/ ./data/gold/

# Sentiment pipeline: news/team-events and /news/player-badges read from
# Silver (signals) and Bronze (documents) — bake them in until the daily
# cron writes to a persistent volume or S3.
COPY data/silver/sentiment/ ./data/silver/sentiment/
COPY data/bronze/sentiment/ ./data/bronze/sentiment/

# Bronze schedules + rosters: required by /api/teams/current-week,
# /api/teams/{team}/roster, and default week resolution for predictions
# and lineups. Without these the endpoints return 503. Phase 66 / v7.0.
COPY data/bronze/schedules/ ./data/bronze/schedules/
COPY data/bronze/players/rosters/ ./data/bronze/players/rosters/

# Bronze depth charts: required by /api/lineups (lineup_builder reads
# `data/bronze/depth_charts/season=YYYY/*.parquet` to identify starters).
# Without these COPY'd, the endpoint silently returns lineups=[] for every
# team. Allowlist already exists in .gitignore (TD-08).
COPY data/bronze/depth_charts/ ./data/bronze/depth_charts/

# Silver defense+team SoS: required by /api/teams/{team}/defense-metrics
# (team_defense_service reads `data/silver/defense/positional/` and
# `data/silver/teams/sos/`). Without these the matchups page renders an
# empty matchup-advantages card and "neutral" tooltips for every key
# matchup. ~13 MB.
COPY data/silver/defense/ ./data/silver/defense/
COPY data/silver/teams/ ./data/silver/teams/

ENV PORT=8000
EXPOSE 8000

CMD uvicorn web.api.main:app --host 0.0.0.0 --port $PORT
