#!/usr/bin/env python3
"""The raw news about named players, for a human or a model to READ.

    python scripts/player_news.py "Roschon Johnson" "Dalton Schultz"
    python scripts/player_news.py --days 3 --league mantis --from-report

The Gold sentiment layer turns articles into keyword flags (`returning`,
`usage_drop`). That is a lossy summary built by pattern matching, and the
waiver report only shows a COUNT of them. The articles themselves are sitting
in Bronze with ``resolved_player_ids`` already attached.

So for the handful of candidates a claim actually comes down to, read the news
instead of the flags. Comprehension-grade extraction in the pipeline needs a
funded ANTHROPIC_API_KEY; comprehension at *advice* time needs only this.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.sleeper_player_map import (  # noqa: E402
    load_sleeper_players,
    normalize_name,
)

BRONZE = REPO_ROOT / "data" / "bronze" / "sentiment"


def load_docs(days: int) -> List[Dict[str, Any]]:
    """Every Bronze sentiment document published within ``days``, newest first.

    Deduplicates on ``external_id``: the same article arrives through several
    feeds and daily captures overlap.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    seen: Dict[str, Dict[str, Any]] = {}
    for path in sorted(glob.glob(str(BRONZE / "**" / "*.json"), recursive=True)):
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = (
            raw
            if isinstance(raw, list)
            else (raw.get("items") or raw.get("docs") or [])
        )
        for doc in items:
            if not isinstance(doc, dict):
                continue
            stamp = str(doc.get("published_at") or "")[:10]
            try:
                when = datetime.strptime(stamp, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if when < cutoff:
                continue
            key = str(doc.get("external_id") or doc.get("url") or doc.get("title"))
            if key not in seen:
                seen[key] = doc
    return sorted(
        seen.values(), key=lambda d: str(d.get("published_at") or ""), reverse=True
    )


def about(
    docs: Sequence[Dict[str, Any]], gsis_ids: Iterable[str], name: str
) -> List[Dict[str, Any]]:
    """Documents that mention this player, by resolved id or by name.

    The id path is exact; the name path catches articles the ingester could
    not resolve, which is most of them for a rookie.
    """
    wanted, norm = set(gsis_ids), normalize_name(name)
    hits = []
    for doc in docs:
        ids = {str(i) for i in (doc.get("resolved_player_ids") or [])}
        text = f"{doc.get('title') or ''} {doc.get('body_text') or ''}"
        cands = {normalize_name(str(c)) for c in (doc.get("candidate_names") or [])}
        if (wanted & ids) or norm in cands or norm in normalize_name(text):
            hits.append(doc)
    return hits


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("players", nargs="+", help="player names to read the news for")
    ap.add_argument("--days", type=int, default=7, help="how far back (default 7)")
    ap.add_argument(
        "--max-per-player", type=int, default=6, help="articles shown each (default 6)"
    )
    args = ap.parse_args(argv)

    registry = load_sleeper_players(max_age_days=7)
    by_norm: Dict[str, List[str]] = {}
    for meta in registry.values():
        gsis = meta.get("gsis_id")
        if gsis and meta.get("full_name"):
            by_norm.setdefault(normalize_name(str(meta["full_name"])), []).append(
                str(gsis)
            )

    docs = load_docs(args.days)
    print(f"\n{len(docs)} unique articles in the last {args.days} days\n")
    for name in args.players:
        hits = about(docs, by_norm.get(normalize_name(name), []), name)
        print(f"=== {name} — {len(hits)} article(s) ===")
        if not hits:
            print("  nothing. Silence is not good news; it is no news.\n")
            continue
        for doc in hits[: args.max_per_player]:
            when = str(doc.get("published_at") or "")[:10]
            src = str(doc.get("source") or "?")
            print(f"  [{when} {src}] {str(doc.get('title') or '').strip()[:150]}")
            body = " ".join(str(doc.get("body_text") or "").split())
            if body:
                print(f"      {body[:300]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
