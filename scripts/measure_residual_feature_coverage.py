#!/usr/bin/env python3
"""Write ``src/residual_feature_coverage.json``: the share of populated cells in
each residual model's feature matrix on fully-populated history.

The serve-time coverage guard (``src/residual_coverage.py``) compares the live
matrix against these numbers. They are stored in a tracked sidecar, not in
``models/residual/*_meta.json``, so no model artifact is edited or retrained.
Re-run after a model is retrained or its feature list changes::

    python scripts/measure_residual_feature_coverage.py --seasons 2023 2024 2025
"""

import argparse
import json
import os
import sys

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from residual_coverage import REFERENCE_PATH, measure_reference  # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", type=int, nargs="+", default=[2023, 2024, 2025])
    ap.add_argument("--min-week", type=int, default=3)
    ap.add_argument("--residual-dir", default=os.path.join(_ROOT, "models", "residual"))
    ap.add_argument("--out", default=REFERENCE_PATH)
    args = ap.parse_args()

    feats = {}
    for pos in POSITIONS:
        with open(os.path.join(args.residual_dir, f"{pos.lower()}_residual_meta.json"), encoding="utf-8") as fh:
            feats[pos] = json.load(fh)["features"]
    ref = measure_reference(POSITIONS, feats, args.seasons, args.min_week)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(ref, fh, indent=2, sort_keys=True)
        fh.write("\n")
    for pos, r in ref.items():
        print(f"{pos}: non-NaN share {r['nonnan_share']:.3f} over {r['n_rows']} rows x {r['n_features']} features")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
