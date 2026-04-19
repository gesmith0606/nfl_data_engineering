FROM python:3.9-slim

# Cache-buster: bumped 2026-04-19 to force Railway to re-run all COPY layers
# instead of importing a stale cached image. Change this ARG to invalidate cache.
ARG CACHE_BUST=2026-04-19-01

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

ENV PORT=8000
EXPOSE 8000

CMD uvicorn web.api.main:app --host 0.0.0.0 --port $PORT
