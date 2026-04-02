#!/bin/bash
# Start the FastAPI dev server with hot reload.
# Usage: ./web/run_dev.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate
python -m uvicorn web.api.main:app --reload --host 0.0.0.0 --port 8000
