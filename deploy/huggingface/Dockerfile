# Hugging Face Spaces (Docker SDK) — BRIDGE backend for the NFL site.
#
# Why this exists: the Railway trial was exhausted (~2026-05-06) and the
# production backend went dark. This Space is a $0 stopgap that restores
# prod. It is NOT the public-launch backend — Phase 84 (de-bloat data out
# of the image + move to a launch-grade host) supersedes this before launch.
#
# Strategy: clone the PUBLIC source repo at build time so this Space repo
# stays tiny (just Dockerfile + README) and always builds from latest main,
# including the committed Parquet the API reads in Parquet-fallback mode.

FROM python:3.9-slim

# git: to clone the source repo. libpq-dev/gcc: psycopg2-binary build deps
# (kept for parity with the known-good Railway image, even in Parquet mode).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces convention: run as non-root UID 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# Bump CACHE_BUST to force HF to re-run the clone and pick up newer main
# (e.g. after the daily data cron pushes fresh Parquet to GitHub).
ARG REPO=https://github.com/gesmith0606/nfl_data_engineering.git
ARG REF=main
ARG CACHE_BUST=2026-06-12-01
# CACHE_BUST must be referenced in the RUN command itself — declaring it as
# an ARG above is not enough. Docker's layer cache hashes the literal RUN
# string, so unless ${CACHE_BUST} appears here the layer is reused and the
# clone is never re-run. (The previous form silently served stale main.)
RUN echo "cache-bust ${CACHE_BUST}" && git clone --depth 1 --branch ${REF} ${REPO} repo

WORKDIR /home/user/app/repo

# Exact dependency set the proven-good Railway image used (Parquet mode:
# no boto3/pyspark — src/utils.py is import-safe without them per ed3b047).
RUN pip install --no-cache-dir --user -r web/api/serverless/requirements.txt

# HF routes external traffic to app_port (declared in README.md → 7860).
ENV PORT=7860
EXPOSE 7860

# Mirror railway.json's known-good start command (cwd = repo root, so the
# `web` and `src` packages are importable).
CMD ["python", "-c", "import os,uvicorn;uvicorn.run('web.api.main:app',host='0.0.0.0',port=int(os.environ.get('PORT','7860')))"]
