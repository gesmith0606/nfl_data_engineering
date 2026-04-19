"""Optional Claude Haiku enrichment for website-facing NewsItem summaries.

This module implements Phase 61 D-04 + D-06: Claude is a strictly
optional, opt-in post-processing step that adds a 1-sentence ``summary``
and a ``refined_category`` tag to Silver signal records for use on the
news page. It never feeds the model path (D-02), never overwrites the
rule-extracted event flags, and never raises — any failure (missing key,
missing SDK, API error, rate limit, parse error) silently returns the
input record unchanged.

Module contract
---------------
``LLMEnrichment``
    - ``is_available``: True iff ``ANTHROPIC_API_KEY`` is set AND the
      ``anthropic`` SDK is importable.
    - ``enrich(record)``: returns a copy with two NEW optional fields —
      ``summary: str`` (≤ 200 chars) and
      ``refined_category: str`` (∈ ``_VALID_CATEGORIES``).
      Original event flags are never modified.

``enrich_silver_records(season, week, dry_run=False)``
    - Walks ``data/silver/sentiment/signals/season=YYYY/week=WW/*.json``.
    - Writes enriched sidecar envelopes to
      ``data/silver/sentiment/signals_enriched/season=YYYY/week=WW/``.
    - Non-destructive: never touches the originals.
    - Returns the total number of records enriched. Returns 0 when no
      Silver files exist (never raises).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Claude Haiku — cheapest Anthropic model. Enrichment is summary-only, no
# structured event extraction, so Haiku is appropriate (per D-04 cost note).
_CLAUDE_MODEL = "claude-haiku-4-5"

# Hard cap on LLM-generated summary length for news card rendering.
_SUMMARY_MAX_CHARS = 200

# Max tokens in the Anthropic response — summary + category JSON is tiny.
_MAX_TOKENS = 256

# Valid refined_category values mirror the rule-extractor allow-list in
# ``src/sentiment/processing/extractor.py::_VALID_CATEGORIES``.
_VALID_CATEGORIES = frozenset(
    {"injury", "usage", "trade", "weather", "motivation", "legal", "general"}
)

_ENRICHMENT_PROMPT = (
    "In <=1 sentence, summarize this NFL news article for a fantasy football "
    "reader. Article title: {title}. Body: {body}. Respond with JSON only: "
    '{{"summary": "...", "category": "injury|usage|trade|weather|'
    'motivation|legal|general"}}.'
)

# Project-root-anchored Silver paths — kept as module attributes so tests
# can monkeypatch them for hermetic tmp-tree runs.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SILVER_SIGNALS_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "signals"
_SILVER_ENRICHED_DIR = (
    _PROJECT_ROOT / "data" / "silver" / "sentiment" / "signals_enriched"
)


# ---------------------------------------------------------------------------
# Enrichment class
# ---------------------------------------------------------------------------


class LLMEnrichment:
    """Optional Claude Haiku client that adds a summary + category to records.

    The class is safe to instantiate in any environment: when the env var
    or SDK is missing, ``is_available`` is False and ``enrich()`` returns
    the input unchanged. Callers never need to guard around it.

    Attributes:
        model: The Claude model identifier to use.
        _client: The ``anthropic.Anthropic`` client, or None if the SDK is
            unavailable or the API key is missing.

    Example:
        >>> enrichment = LLMEnrichment()
        >>> if enrichment.is_available:
        ...     record = enrichment.enrich(record)  # adds summary + category
    """

    def __init__(self, model: str = _CLAUDE_MODEL) -> None:
        """Initialise the enrichment client.

        Args:
            model: Claude model ID. Defaults to ``claude-haiku-4-5``.
        """
        self.model = model
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # Client construction (fail-open per D-06)
    # ------------------------------------------------------------------

    def _build_client(self) -> Optional[Any]:
        """Build the Anthropic client, or return None on any failure.

        Never raises. Checks ``ANTHROPIC_API_KEY`` first; if set, attempts
        to import the ``anthropic`` SDK and construct a client. Any error
        at any stage is logged as a warning and None is returned.

        Returns:
            An ``anthropic.Anthropic`` instance, or None if unavailable.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.info(
                "LLMEnrichment: ANTHROPIC_API_KEY unset -- "
                "enrichment disabled (D-04 opt-in)."
            )
            return None

        try:
            import anthropic  # type: ignore

            return anthropic.Anthropic(api_key=api_key)
        except ImportError:
            logger.warning(
                "LLMEnrichment: 'anthropic' package not importable; "
                "enrichment will be skipped."
            )
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "LLMEnrichment: client construction failed (%s); "
                "enrichment will be skipped.",
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """True if the client is constructed and enrichment can proceed."""
        return self._client is not None

    def enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy of *record* with optional summary + refined_category.

        On any failure (missing key, missing SDK, API error, JSON parse
        error, invalid category), returns the input unchanged — never
        raises. Existing event flags are never modified (T-61-06-05).

        Args:
            record: A Silver signal record dict.

        Returns:
            A new dict. When enrichment succeeds, the returned dict has
            two extra keys — ``summary`` (≤ 200 chars) and
            ``refined_category`` (∈ ``_VALID_CATEGORIES``). When
            enrichment is unavailable or fails, the returned dict is a
            shallow copy of the input with NO extra keys added.
        """
        if not self.is_available:
            # Shallow copy preserves "returned unchanged" semantics while
            # letting callers mutate the result without side effects.
            return dict(record)

        title = str(record.get("title") or "").strip()
        body = str(record.get("raw_excerpt") or record.get("body_text") or "").strip()
        if not title and not body:
            # Nothing to summarize — skip.
            return dict(record)

        # Truncate body aggressively to keep Haiku latency + cost bounded.
        body_trimmed = body[:1500]

        try:
            raw = self._call_claude(title, body_trimmed)
            parsed = self._parse_response(raw)
        except Exception as exc:
            # D-06 fail-open: never propagate Anthropic failures
            logger.warning(
                "LLMEnrichment: failed to enrich record %s (%s); "
                "returning unchanged.",
                record.get("signal_id", "unknown"),
                exc,
            )
            return dict(record)

        if parsed is None:
            return dict(record)

        summary, refined_category = parsed
        out = dict(record)
        out["summary"] = summary
        out["refined_category"] = refined_category
        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_claude(self, title: str, body: str) -> str:
        """Send the enrichment prompt to Claude and return the raw text.

        Args:
            title: Article title (may be empty).
            body: Article body text (may be empty).

        Returns:
            Raw string response.

        Raises:
            Any exception from the Anthropic SDK is propagated to the
            caller, which converts it into a fail-open pass-through.
        """
        prompt = _ENRICHMENT_PROMPT.format(title=title, body=body)
        response = self._client.messages.create(  # type: ignore[union-attr]
            model=self.model,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    @staticmethod
    def _parse_response(raw: str) -> Optional[tuple]:
        r"""Parse Claude's JSON response into (summary, category) or None.

        Accepts responses wrapped in ``\`\`\`json ... \`\`\``` fences.
        Clamps ``summary`` to ``_SUMMARY_MAX_CHARS``. Falls back to
        ``"general"`` when the returned category is not in the allow-list.

        Args:
            raw: Raw string returned by Claude.

        Returns:
            ``(summary, category)`` tuple, or None if parsing failed.
        """
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "LLMEnrichment: JSON parse error -- %s. Raw: %.200s", exc, raw
            )
            return None

        if not isinstance(data, dict):
            logger.warning(
                "LLMEnrichment: expected JSON object, got %s",
                type(data).__name__,
            )
            return None

        summary = str(data.get("summary") or "").strip()
        if not summary:
            return None
        summary = summary[:_SUMMARY_MAX_CHARS]

        raw_category = str(data.get("category") or "general").lower().strip()
        category = raw_category if raw_category in _VALID_CATEGORIES else "general"
        return summary, category


# ---------------------------------------------------------------------------
# Batch driver (walks Silver envelopes, writes enriched sidecars)
# ---------------------------------------------------------------------------


def _load_silver_envelope(path: Path) -> Optional[Dict[str, Any]]:
    """Read a Silver envelope JSON file. Returns None on parse error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("LLMEnrichment: failed to read %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning(
            "LLMEnrichment: envelope %s has unexpected top-level type %s",
            path,
            type(data).__name__,
        )
        return None
    return data


def _list_silver_envelopes(season: int, week: int) -> List[Path]:
    """Return the list of Silver envelope JSON paths for a season/week."""
    week_dir = _SILVER_SIGNALS_DIR / f"season={season}" / f"week={week:02d}"
    if not week_dir.exists():
        return []
    return sorted(week_dir.glob("signals_*.json"))


def _write_enriched_envelope(
    batch_id: str,
    season: int,
    week: int,
    records: List[Dict[str, Any]],
) -> Path:
    """Write an enriched sidecar envelope and return its path."""
    out_dir = _SILVER_ENRICHED_DIR / f"season={season}" / f"week={week:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"enriched_{batch_id}_{ts}.json"
    envelope = {
        "batch_id": batch_id,
        "season": season,
        "week": week,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source": "llm_enrichment",
        "record_count": len(records),
        "records": records,
    }
    path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return path


def enrich_silver_records(
    season: int,
    week: int,
    dry_run: bool = False,
) -> int:
    """Enrich every Silver signal record for a season/week.

    Non-destructive: original Silver envelopes are never modified. Each
    enriched envelope is written to
    ``data/silver/sentiment/signals_enriched/season=YYYY/week=WW/``.

    Returns 0 (and does nothing) when:
        - no Silver files exist for the season/week, OR
        - ``ANTHROPIC_API_KEY`` is absent / SDK missing.

    Any per-record enrichment failure is logged and the record is passed
    through unchanged (D-06 fail-open).

    Args:
        season: NFL season year.
        week: NFL week number (1-18).
        dry_run: If True, enrichment still runs but no sidecar file is
            written to disk. The return count reflects records that
            *would* have been written.

    Returns:
        Total number of records enriched across all envelopes.
    """
    envelopes = _list_silver_envelopes(season, week)
    if not envelopes:
        logger.info(
            "LLMEnrichment: no Silver envelopes found for season=%d week=%d",
            season,
            week,
        )
        return 0

    enrichment = LLMEnrichment()
    if not enrichment.is_available:
        # Explicit log so ops operators know the flag was on but the key
        # / SDK was not. Pipeline still returns 0 gracefully.
        logger.warning(
            "LLMEnrichment: enrichment requested but unavailable "
            "(missing ANTHROPIC_API_KEY or anthropic SDK); skipping %d envelope(s).",
            len(envelopes),
        )
        return 0

    total_enriched = 0
    for envelope_path in envelopes:
        data = _load_silver_envelope(envelope_path)
        if data is None:
            continue

        source_records = data.get("records") or []
        if not isinstance(source_records, list):
            logger.warning(
                "LLMEnrichment: envelope %s has non-list records; skipping.",
                envelope_path,
            )
            continue

        enriched_records: List[Dict[str, Any]] = []
        for record in source_records:
            if not isinstance(record, dict):
                continue
            try:
                enriched_records.append(enrichment.enrich(record))
            except Exception as exc:  # pragma: no cover - double-defence
                # enrich() already fails open, but belt-and-braces here
                logger.warning(
                    "LLMEnrichment: unexpected error on record %s: %s",
                    record.get("signal_id", "unknown"),
                    exc,
                )
                enriched_records.append(dict(record))

        if not enriched_records:
            continue

        batch_id = str(data.get("batch_id") or uuid.uuid4().hex[:8])

        if dry_run:
            logger.info(
                "LLMEnrichment: dry-run -- would write %d records for batch=%s",
                len(enriched_records),
                batch_id,
            )
        else:
            out_path = _write_enriched_envelope(
                batch_id=batch_id,
                season=season,
                week=week,
                records=enriched_records,
            )
            logger.info(
                "LLMEnrichment: wrote %d records -> %s",
                len(enriched_records),
                out_path,
            )

        total_enriched += len(enriched_records)

    return total_enriched
