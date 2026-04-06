FROM python:3.9-slim

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

# Create empty data directory (production uses DATABASE_URL, not Parquet files)
RUN mkdir -p data

ENV PORT=8000
EXPOSE 8000

CMD uvicorn web.api.main:app --host 0.0.0.0 --port $PORT
