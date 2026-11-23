#!/usr/bin/env python3
"""Print every verdict, its ruling and PASS/FAIL per assertion; exit 1 on failure.

Usage: python scripts/check_verdicts.py   (see docs/VERDICT_REGISTRY.md)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.verdict_registry import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
