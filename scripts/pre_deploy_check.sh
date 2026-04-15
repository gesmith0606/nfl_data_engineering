#!/bin/bash
# Pre-deploy sanity check — run before pushing projection updates
#
# Validates projections and predictions against consensus rankings,
# checks for critical discrepancies, and gates deployment.
#
# Exit codes:
#   0 = PASS or WARN (safe to deploy)
#   1 = CRITICAL failure (do NOT deploy)
#
# Usage:
#   ./scripts/pre_deploy_check.sh
#   ./scripts/pre_deploy_check.sh --season 2026 --week 5

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate venv if available
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "=== Pre-Deploy Sanity Check ==="
echo ""

python scripts/sanity_check_projections.py --all --scoring half_ppr "$@"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "Pre-deploy check PASSED — safe to deploy."
else
    echo "Pre-deploy check FAILED — do NOT deploy. Fix CRITICAL issues first."
fi

exit $EXIT_CODE
