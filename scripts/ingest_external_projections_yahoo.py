#!/usr/bin/env python3
"""Yahoo (via FantasyPros consensus) External Projections Ingester — Bronze (Phase 73-01).

Per CONTEXT D-03 (LOCKED): real Yahoo OAuth is deferred to v8.0. We use the
public FantasyPros consensus rankings/projections as a Yahoo proxy because the
FP consensus aggregates ESPN/Yahoo/CBS/RotoWire and provides a reasonable
Yahoo signal. Source label is ``yahoo_proxy_fp`` so users can see provenance.

Writes Parquet to::

    data/bronze/external_projections/yahoo_proxy_fp/season=YYYY/week=WW/yahoo_proxy_fp_{ts}.parquet

Fail-open contract (D-06): any HTTP / parse error logs a warning and exits 0
without writing.

CLI
---
    python scripts/ingest_external_projections_yahoo.py --season 2025 --week 1
    python scripts/ingest_external_projections_yahoo.py --season 2025 --week 1 \\
        --html-fixture tests/fixtures/external_projections/fantasypros_sample.html
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_external_projections_yahoo")

_SOURCE_LABEL: str = "yahoo_proxy_fp"
_REQUEST_TIMEOUT_S: int = 15
_USER_AGENT: str = "nfl-data-engineering/0.1 (external-projections-yahoo-via-fp)"

_DEFAULT_OUT_ROOT: Path = (
    _PROJECT_ROOT / "data" / "bronze" / "external_projections"
)

_FP_URL_TEMPLATE: str = (
    "https://www.fantasypros.com/nfl/projections/{position}.php?week={week}"
)

# Positions to fetch (FantasyPros uses position-specific pages).
_POSITIONS = ("qb", "rb", "wr", "te", "k")


def _fetch_html(url: str) -> Optional[str]:
    """GET URL, return text body or None on error (D-06 fail-open)."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("FP fetch failed for %s: %s — fail-open", url, exc)
        return None


_ROW_RE = re.compile(
    r"<tr[^>]*class=\"[^\"]*mpb-player[^\"]*\"[^>]*>(.+?)</tr>",
    re.DOTALL,
)
_NAME_RE = re.compile(r"<a[^>]*class=\"[^\"]*player-name[^\"]*\"[^>]*>([^<]+)</a>")
_TEAM_RE = re.compile(r"<small[^>]*class=\"[^\"]*grey[^\"]*\">([A-Z]{2,3})</small>")
_FPTS_RE = re.compile(
    r'<td[^>]*class="[^"]*center[^"]*"[^>]*>([0-9]+\.[0-9]+)</td>'
)


def _parse_fp_html(
    html: str, position: str, season: int, week: int, scoring: str
) -> List[Dict]:
    """Parse FantasyPros HTML page (one position) into Bronze records.

    The FP HTML is reasonably stable but not API-grade. We extract per-row:
    player name, team, projected fantasy points (last column on the row,
    typically labelled ``FPTS``). Failure to parse a row is logged at DEBUG
    and the row is skipped — D-06 ensures the run never breaks.

    Args:
        html: Raw HTML body.
        position: Position string (lowercase: qb/rb/wr/te/k).
        season: NFL season year.
        week: NFL week number.
        scoring: Scoring format string.

    Returns:
        List of Bronze record dicts.
    """
    records: List[Dict] = []
    projected_at = datetime.now(timezone.utc).isoformat()

    for row_match in _ROW_RE.finditer(html or ""):
        row = row_match.group(1)
        name_m = _NAME_RE.search(row)
        team_m = _TEAM_RE.search(row)
        fpts_m = _FPTS_RE.search(row)
        if not (name_m and fpts_m):
            continue

        try:
            fpts = float(fpts_m.group(1))
        except (TypeError, ValueError):
            continue

        records.append(
            {
                "player_name": name_m.group(1).strip(),
                "player_id": None,  # PlayerNameResolver runs in Wave 2 Silver step
                "team": team_m.group(1) if team_m else None,
                "position": position.upper(),
                "projected_points": fpts,
                "scoring_format": scoring,
                "source": _SOURCE_LABEL,
                "season": int(season),
                "week": int(week),
                "projected_at": projected_at,
                "raw_payload": row[:500],
            }
        )
    return records


def _write_bronze(
    records: List[Dict], season: int, week: int, out_root: Path
) -> Optional[Path]:
    if not records:
        logger.warning(
            "No FP/Yahoo-proxy projections to write for season=%d week=%d (D-06)",
            season,
            week,
        )
        return None

    week_dir = (
        out_root / _SOURCE_LABEL / f"season={season}" / f"week={week:02d}"
    )
    week_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = week_dir / f"{_SOURCE_LABEL}_{ts}.parquet"

    df = pd.DataFrame(records)
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d FP/Yahoo-proxy projections to %s", len(records), out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--scoring", choices=["ppr", "half_ppr", "standard"], default="half_ppr"
    )
    parser.add_argument("--out-root", type=Path, default=_DEFAULT_OUT_ROOT)
    parser.add_argument(
        "--html-fixture",
        type=Path,
        default=None,
        help=(
            "Optional path to a JSON fixture mapping {position: html_string} "
            "for hermetic testing."
        ),
    )
    args = parser.parse_args()

    all_records: List[Dict] = []

    if args.html_fixture and args.html_fixture.exists():
        # Test mode: load HTML per-position from a JSON fixture map.
        fixture = json.loads(args.html_fixture.read_text(encoding="utf-8"))
        for pos in _POSITIONS:
            html = fixture.get(pos, "")
            all_records.extend(
                _parse_fp_html(html, pos, args.season, args.week, args.scoring)
            )
    else:
        for pos in _POSITIONS:
            url = _FP_URL_TEMPLATE.format(position=pos, week=args.week)
            html = _fetch_html(url)
            if not html:
                continue
            all_records.extend(
                _parse_fp_html(html, pos, args.season, args.week, args.scoring)
            )

    _write_bronze(all_records, args.season, args.week, args.out_root)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
