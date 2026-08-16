#!/usr/bin/env python3
"""
Model freshness / staleness invariant check — makes the model-staleness
failure class structurally detectable, mirroring what
scripts/check_data_completeness.py did for data holes (see
.planning/MODEL_REVIEW_2026_08_15.md, findings #1/#2/#3/#6/#7/#9/#11).

Every shipped model family (models/residual, models/quantile,
models/ensemble, models/bayesian) is checked for three failure modes that
all trace back to the same root cause the audit found empirically in
models/quantile/imputer.pkl:

  (a) Frozen-imputer NaN statistics — sklearn's SimpleImputer (default
      keep_empty_features=False) permanently drops any column that was
      all-NaN at *fit* time from every future transform(), even after the
      live data is repaired. Any ``statistics_`` entry that is NaN means
      that column is gone forever from this artifact's predictions.
  (b) Live-schema mismatch — the same mechanism reproduced against a real,
      freshly-assembled feature frame: does the current Silver schema
      contain a column this imputer silently drops? (finding #1's exact
      shape.) Best-effort: skipped with a WARN when no local Silver data is
      available to probe (e.g. a fresh CI clone — Silver is not committed).
  (c) Staleness — artifact vintage (trained_at/created_at, or a file-mtime
      fallback when the meta.json has neither — see src/model_provenance.py
      for the real fix) compared against the newest Silver partition on
      disk. A lazy proxy, not a real content hash — WARN-tier only.

Tiers: FAIL blocks (non-zero exit); WARN is reported but never blocks.
Bayesian is unwired/research-tier (finding #14) — every bayesian check is
forced to WARN regardless of what it finds.

Usage:
    python scripts/check_model_freshness.py
    python scripts/check_model_freshness.py --no-probe   # skip live-schema/staleness checks (fast, artifact-only)
"""

import argparse
import json
import pickle
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

# ---------------------------------------------------------------------------
# Paths — module globals so tests can monkeypatch them (same pattern as
# scripts/check_data_completeness.py's DATA_ROOT).
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
MODELS_DIR = PROJECT_ROOT / "models"
DATA_ROOT = PROJECT_ROOT / "data"

sys.path.insert(0, str(SRC_DIR))

POSITIONS: tuple = ("qb", "rb", "wr", "te")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    id: str
    tier: str  # "FAIL" or "WARN"
    passed: bool
    message: str


# ---------------------------------------------------------------------------
# Artifact loading helpers
# ---------------------------------------------------------------------------


def _load_joblib(path: Path) -> Any:
    import joblib

    return joblib.load(path)


def _load_pickle(path: Path) -> Any:
    with open(path, "rb") as f:
        return pickle.load(f)


def _load_json(path: Path) -> Dict:
    with open(path, "r") as f:
        return json.load(f)


def _mtime_iso(path: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Live-schema probe + Silver staleness proxy
# ---------------------------------------------------------------------------


def probe_live_feature_columns(season: Optional[int] = None) -> Optional[Set[str]]:
    """Assemble a real, current player-feature frame and return its columns.

    Best-effort: returns None (never raises) when Silver data isn't present
    locally (e.g. a fresh CI clone — data/silver/ is gitignored, see
    CLAUDE.md's data-layer notes) or any other import/read failure occurs.
    """
    try:
        import config
        from player_feature_engineering import (
            assemble_player_features,
            get_player_feature_columns,
        )
    except Exception:
        return None

    try:
        probe_season = season if season is not None else max(config.PLAYER_DATA_SEASONS)
        df = assemble_player_features(probe_season)
    except Exception:
        return None

    if df is None or df.empty:
        return None

    try:
        return set(get_player_feature_columns(df))
    except Exception:
        return set(df.columns)


def find_newest_silver_timestamp(data_root: Optional[Path] = None) -> Optional[datetime]:
    """Newest mtime among every Parquet file under data/silver/ — a lazy
    proxy for "the last Silver schema-changing event" (no per-file schema
    diffing; see module docstring). None when data/silver/ is absent
    locally (e.g. CI, which never gets Silver — it isn't committed).
    """
    root = (data_root if data_root is not None else DATA_ROOT) / "silver"
    if not root.is_dir():
        return None

    newest: Optional[float] = None
    for f in root.rglob("*.parquet"):
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        if newest is None or mt > newest:
            newest = mt

    if newest is None:
        return None
    return datetime.fromtimestamp(newest, tz=timezone.utc)


def _parse_timestamp(raw: Any) -> datetime:
    """Parse an ISO8601 string (with or without a trailing Z) to a UTC datetime."""
    if isinstance(raw, datetime):
        dt = raw
    else:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Generic checks
# ---------------------------------------------------------------------------


def check_imputer_nan(check_id: str, imputer: Any, tier: str) -> CheckResult:
    """FAIL (or WARN, per tier) if a fitted SimpleImputer has any NaN
    fit-time statistic — the finding #1 mechanism: sklearn silently drops
    that column from every future transform(), forever.
    """
    if imputer is None:
        return CheckResult(check_id, tier, True, "no frozen imputer artifact for this position")

    stats = getattr(imputer, "statistics_", None)
    if stats is None:
        return CheckResult(
            check_id, tier, False,
            "imputer object has no statistics_ (not fitted, or not a SimpleImputer)",
        )

    import numpy as np

    stats_arr = np.asarray(stats, dtype=float)
    nan_idx = [i for i in range(len(stats_arr)) if np.isnan(stats_arr[i])]
    if nan_idx:
        return CheckResult(
            check_id, tier, False,
            f"{len(nan_idx)}/{len(stats_arr)} imputer statistic(s) are NaN — those "
            f"column(s) are permanently dropped from every future transform() "
            f"(sklearn SimpleImputer keep_empty_features=False default)",
        )
    return CheckResult(check_id, tier, True, f"0/{len(stats_arr)} imputer statistics NaN")


def check_feature_coverage(
    check_id: str,
    meta_features: Sequence[str],
    imputer: Any,
    live_columns: Optional[Set[str]],
    tier: str,
) -> List[CheckResult]:
    """Two checks against a live-assembled feature frame:

    1. ``{check_id}/dropped`` (tier-configurable, FAIL-capable): any model
       feature that is BOTH present in the live schema right now AND has a
       NaN fit-time imputer statistic is being silently dropped despite
       being real, current data — finding #1 reproduced directly.
    2. ``{check_id}/live_coverage`` (always WARN, informational): any model
       feature simply absent from the live schema probe (may be normal
       schema evolution, not necessarily a bug).
    """
    dropped_id = f"{check_id}/dropped"
    coverage_id = f"{check_id}/live_coverage"

    if not meta_features:
        msg = "no feature list in artifact meta — skipped"
        return [
            CheckResult(dropped_id, tier, True, msg),
            CheckResult(coverage_id, "WARN", True, msg),
        ]

    if live_columns is None:
        msg = (
            "no local Silver data to probe the live schema — skipped "
            "(run on a machine with data/silver/ populated for a real check)"
        )
        return [
            CheckResult(dropped_id, "WARN", True, msg),
            CheckResult(coverage_id, "WARN", True, msg),
        ]

    dropped_but_live: List[str] = []
    if imputer is not None and hasattr(imputer, "statistics_"):
        import numpy as np

        stats = np.asarray(imputer.statistics_, dtype=float)
        n = min(len(stats), len(meta_features))
        dropped_but_live = [
            meta_features[i]
            for i in range(n)
            if np.isnan(stats[i]) and meta_features[i] in live_columns
        ]

    results = []
    if dropped_but_live:
        preview = dropped_but_live[:8]
        suffix = " ..." if len(dropped_but_live) > 8 else ""
        results.append(CheckResult(
            dropped_id, tier, False,
            f"{len(dropped_but_live)} feature(s) permanently dropped by the frozen "
            f"imputer despite being live in the current Silver schema (finding #1 "
            f"mechanism): {preview}{suffix}",
        ))
    else:
        results.append(CheckResult(dropped_id, tier, True, "no live features silently dropped by imputer"))

    missing_live = [f for f in meta_features if f not in live_columns]
    if missing_live:
        preview = missing_live[:8]
        suffix = " ..." if len(missing_live) > 8 else ""
        results.append(CheckResult(
            coverage_id, "WARN", False,
            f"{len(missing_live)}/{len(meta_features)} model feature(s) absent from "
            f"the live schema probe: {preview}{suffix}",
        ))
    else:
        results.append(CheckResult(coverage_id, "WARN", True, f"all {len(meta_features)} feature(s) present live"))

    return results


def check_provenance(check_id: str, meta: Dict) -> CheckResult:
    """WARN (never blocks) if an artifact's meta.json has no ``provenance``
    key -- the src/model_provenance.py stamp (per-source row counts,
    partition timestamps, git SHA) wired into the four train_*.py save
    paths per .planning/MODEL_FRESHNESS_GUARDS.md. Absence just means a
    legacy artifact predates the stamp, not a defect on its own -- WARN-tier
    only, never FAIL.
    """
    provenance = meta.get("provenance")
    if not provenance:
        return CheckResult(
            check_id, "WARN", False,
            "no provenance stamp in meta.json -- legacy artifact predating "
            "src/model_provenance.py (retrain to pick it up)",
        )
    sources = provenance.get("sources", {}) if isinstance(provenance, dict) else {}
    git_sha = provenance.get("git_sha") if isinstance(provenance, dict) else None
    return CheckResult(
        check_id, "WARN", True,
        f"provenance stamp present: {len(sources)} source(s), git_sha={git_sha!r}",
    )


def check_staleness(
    check_id: str,
    trained_at: Any,
    silver_newest: Optional[datetime],
    proxy_used: bool = False,
) -> CheckResult:
    """WARN if the artifact's vintage predates the newest Silver change on
    disk. Always WARN-tier (a lazy mtime-based proxy, not a real content
    hash — see src/model_provenance.py for the actual fix).
    """
    if silver_newest is None:
        return CheckResult(
            check_id, "WARN", True,
            "no local Silver data available — staleness check skipped "
            "(needs a machine with data/silver/ populated)",
        )

    if trained_at is None:
        return CheckResult(
            check_id, "WARN", False,
            "artifact has no trained_at/created_at timestamp in its meta.json — "
            "cannot verify vintage (see src/model_provenance.py's provenance patch)",
        )

    try:
        trained_dt = _parse_timestamp(trained_at)
    except Exception:
        return CheckResult(check_id, "WARN", False, f"unparseable timestamp: {trained_at!r}")

    proxy_note = " [proxy: artifact file mtime, not a real trained_at]" if proxy_used else ""
    if trained_dt < silver_newest:
        return CheckResult(
            check_id, "WARN", False,
            f"artifact vintage {trained_dt.isoformat()} predates newest Silver "
            f"change {silver_newest.isoformat()}{proxy_note}",
        )
    return CheckResult(
        check_id, "WARN", True,
        f"artifact vintage {trained_dt.isoformat()} >= newest Silver change "
        f"{silver_newest.isoformat()}{proxy_note}",
    )


# ---------------------------------------------------------------------------
# Per-family checks
# ---------------------------------------------------------------------------


def residual_family_results(
    models_dir: Path,
    live_columns: Optional[Set[str]],
    silver_newest: Optional[datetime],
) -> List[CheckResult]:
    results: List[CheckResult] = []
    for pos in POSITIONS:
        cid = f"residual/{pos}"
        meta_path = models_dir / f"{pos}_residual_meta.json"
        model_path = models_dir / f"{pos}_residual.joblib"

        if not meta_path.exists() or not model_path.exists():
            results.append(CheckResult(f"{cid}/artifact", "FAIL", False, "missing model or meta.json"))
            continue

        meta = _load_json(meta_path)
        model_type = str(meta.get("model_type", "ridge"))
        features = meta.get("features", [])

        imputer = None
        try:
            if model_type.startswith("lgb"):
                imputer_path = models_dir / f"{pos}_residual_imputer.joblib"
                if imputer_path.exists():
                    imputer = _load_joblib(imputer_path)
            else:
                pipeline = _load_joblib(model_path)
                if hasattr(pipeline, "named_steps"):
                    imputer = pipeline.named_steps.get("imputer")
        except Exception as e:
            results.append(CheckResult(f"{cid}/load", "FAIL", False, f"failed to load: {e}"))
            continue

        results.append(check_imputer_nan(f"{cid}/imputer_nan", imputer, tier="FAIL"))
        results.extend(check_feature_coverage(f"{cid}/features", features, imputer, live_columns, tier="FAIL"))
        results.append(check_provenance(f"{cid}/provenance", meta))

        trained_at = meta.get("trained_at")
        proxy_used = trained_at is None
        if proxy_used:
            trained_at = _mtime_iso(model_path)
        results.append(check_staleness(f"{cid}/staleness", trained_at, silver_newest, proxy_used))

    return results


def quantile_family_results(
    models_dir: Path,
    live_columns: Optional[Set[str]],
    silver_newest: Optional[datetime],
) -> List[CheckResult]:
    cid = "quantile"
    meta_path = models_dir / "metadata.json"
    imputer_path = models_dir / "imputer.pkl"

    if not meta_path.exists():
        return [CheckResult(f"{cid}/artifact", "FAIL", False, "missing metadata.json")]

    meta = _load_json(meta_path)
    features = meta.get("feature_cols", [])

    imputer = None
    if imputer_path.exists():
        try:
            imputer = _load_pickle(imputer_path)
        except Exception as e:
            return [CheckResult(f"{cid}/load", "FAIL", False, f"failed to load imputer.pkl: {e}")]

    results = [check_imputer_nan(f"{cid}/imputer_nan", imputer, tier="FAIL")]
    results.extend(check_feature_coverage(f"{cid}/features", features, imputer, live_columns, tier="FAIL"))
    results.append(check_provenance(f"{cid}/provenance", meta))

    trained_at = meta.get("created_at") or meta.get("trained_at")
    results.append(check_staleness(f"{cid}/staleness", trained_at, silver_newest, proxy_used=False))
    return results


def ensemble_family_results(
    models_dir: Path,
    silver_newest: Optional[datetime],
) -> List[CheckResult]:
    """Finding #6: does the Ridge meta-learner deserve the same imputer
    NaN-statistics check as quantile/residual? Empirically: no frozen
    imputer artifact exists in this family at all. The meta-learner
    (RidgeCV / non-negative Ridge / MeanMeta -- see
    src/ensemble_training.py::select_meta_learner) stacks only 3 always-
    populated base-model OOF predictions (xgb_pred/lgb_pred/cb_pred); the
    base features feeding XGB/LGB/CB themselves use a live ``.fillna(0.0)``
    at inference (scripts/generate_predictions.py), never a persisted
    SimpleImputer. So the finding #1 mechanism structurally cannot occur
    here -- this is a real, checked verdict, not an assumption.
    """
    results: List[CheckResult] = []

    # ensemble_training must be importable for joblib to unpickle the
    # custom MeanMeta class (and Ridge/RidgeCV need nothing extra).
    try:
        import ensemble_training  # noqa: F401
    except Exception:
        pass

    import numpy as np

    for target in ("spread", "total"):
        cid = f"ensemble/{target}"
        ridge_path = models_dir / f"ridge_{target}.pkl"

        if not ridge_path.exists():
            results.append(CheckResult(f"{cid}/meta_learner", "FAIL", False, "missing meta-learner artifact"))
            continue

        try:
            meta_model = _load_joblib(ridge_path)
        except Exception as e:
            results.append(CheckResult(f"{cid}/meta_learner", "FAIL", False, f"failed to load: {e}"))
            continue

        results.append(CheckResult(
            f"{cid}/imputer_nan", "FAIL", True,
            "N/A — no frozen imputer artifact in this family (meta-learner stacks 3 "
            "base-model OOF predictions only; base features use live .fillna(0.0), "
            "never a persisted SimpleImputer — verified, not assumed)",
        ))

        coef = getattr(meta_model, "coef_", None)
        if coef is None:
            # Legacy artifact predating coef_/intercept_ persistence on
            # MeanMeta (models/ensemble/ridge_*.pkl's pickled __dict__ is
            # empty — see src/ensemble_training.py::MeanMeta) — not an
            # error, just nothing to shape-check. Reported explicitly
            # rather than silently omitted.
            results.append(CheckResult(
                f"{cid}/meta_shape", "FAIL", True,
                "no coef_ on this artifact (legacy MeanMeta pickle predating "
                "coef_/intercept_ persistence) — shape check skipped",
            ))
        else:
            n_weights = int(np.asarray(coef).size)
            if n_weights != 3:
                results.append(CheckResult(
                    f"{cid}/meta_shape", "FAIL", False,
                    f"meta-learner has {n_weights} weight(s), expected 3 (xgb/lgb/cb)",
                ))
            else:
                results.append(CheckResult(f"{cid}/meta_shape", "FAIL", True, "meta-learner shape OK (3 base predictions)"))

    meta_path = models_dir / "metadata.json"
    ensemble_meta: Dict = {}
    if meta_path.exists():
        ensemble_meta = _load_json(meta_path)
    trained_at = ensemble_meta.get("trained_at")
    results.append(check_staleness("ensemble/staleness", trained_at, silver_newest, proxy_used=False))
    results.append(check_provenance("ensemble/provenance", ensemble_meta))

    return results


def bayesian_family_results(
    models_dir: Path,
    live_columns: Optional[Set[str]],
    silver_newest: Optional[datetime],
) -> List[CheckResult]:
    """Research-tier, unwired (finding #14) — every result here is forced
    to WARN regardless of severity, per the task spec.
    """
    results: List[CheckResult] = []

    try:
        import bayesian_projection  # noqa: F401 — needed to unpickle BayesianResidualModel
    except Exception:
        pass

    for pos in POSITIONS:
        cid = f"bayesian/{pos}"
        meta_path = models_dir / f"bayesian_{pos}_meta.json"
        model_path = models_dir / f"bayesian_{pos}.joblib"

        if not meta_path.exists() or not model_path.exists():
            results.append(CheckResult(f"{cid}/artifact", "WARN", False, "missing artifact (research-tier, unwired)"))
            continue

        meta = _load_json(meta_path)
        try:
            model_obj = _load_joblib(model_path)
        except Exception as e:
            results.append(CheckResult(f"{cid}/load", "WARN", False, f"failed to load: {e}"))
            continue

        imputer = None
        pipeline = getattr(model_obj, "pipeline", None)
        if pipeline is not None and hasattr(pipeline, "named_steps"):
            imputer = pipeline.named_steps.get("imputer")

        results.append(check_imputer_nan(f"{cid}/imputer_nan", imputer, tier="WARN"))

        features = getattr(model_obj, "feature_names", None) or meta.get("features", [])
        results.extend(check_feature_coverage(f"{cid}/features", features, imputer, live_columns, tier="WARN"))
        results.append(check_provenance(f"{cid}/provenance", meta))

        trained_at = meta.get("trained_at")
        proxy_used = trained_at is None
        if proxy_used:
            trained_at = _mtime_iso(model_path)
        results.append(check_staleness(f"{cid}/staleness", trained_at, silver_newest, proxy_used))

    return results


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_checks(probe: bool = True) -> List[CheckResult]:
    """Run every family's checks and return the full CheckResult list.

    Args:
        probe: When True (default), attempt the live-schema probe and
            Silver-staleness scan. Both degrade to WARN-tier "skipped"
            results on their own if data/silver/ isn't present (e.g. CI) —
            probe=False just skips the (slow, ~5s) attempt outright.
    """
    live_columns = probe_live_feature_columns() if probe else None
    silver_newest = find_newest_silver_timestamp() if probe else None

    results: List[CheckResult] = []
    results.extend(residual_family_results(MODELS_DIR / "residual", live_columns, silver_newest))
    results.extend(quantile_family_results(MODELS_DIR / "quantile", live_columns, silver_newest))
    results.extend(ensemble_family_results(MODELS_DIR / "ensemble", silver_newest))
    results.extend(bayesian_family_results(MODELS_DIR / "bayesian", live_columns, silver_newest))
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(results: List[CheckResult]) -> int:
    print("\nNFL Model Freshness Check")
    print("=" * 88)

    fail_misses = []
    warn_misses = []

    for r in results:
        status = "PASS" if r.passed else r.tier
        print(f"[{status:>4}] {r.id:<32} {r.message}")
        if not r.passed:
            (fail_misses if r.tier == "FAIL" else warn_misses).append(r)

    print("-" * 88)
    print(
        f"Summary: {len(results)} check(s) — "
        f"{len(results) - len(fail_misses) - len(warn_misses)} PASS, "
        f"{len(warn_misses)} WARN-miss, {len(fail_misses)} FAIL-miss"
    )

    if fail_misses:
        print(f"Overall: FAIL — {len(fail_misses)} FAIL-tier check(s) failed:")
        for r in fail_misses:
            print(f"  - {r.id}: {r.message}")
    else:
        print("Overall: PASS" + (f" (with {len(warn_misses)} WARN-tier miss(es), non-blocking)" if warn_misses else ""))

    print("=" * 88)
    return 1 if fail_misses else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Model freshness/staleness invariant check — see .planning/MODEL_FRESHNESS_GUARDS.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--no-probe", action="store_true",
        help="Skip the live-schema probe and Silver staleness scan (artifact-only checks; faster).",
    )
    args = parser.parse_args()

    results = run_checks(probe=not args.no_probe)
    return print_report(results)


if __name__ == "__main__":
    sys.exit(main())
