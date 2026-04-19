"""
Claude-powered text extraction for the NFL Sentiment Pipeline.

Processes Bronze JSON documents through the Claude API (claude-haiku)
to extract player mentions, sentiment scores, confidence levels,
categorization tags, and event flags.

Public API
----------
>>> extractor = ClaudeExtractor()
>>> signals = extractor.extract(doc)
>>> [s.player_name for s in signals]
['Patrick Mahomes', 'Travis Kelce']
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Claude model to use — Haiku is cheapest and sufficient for extraction.
_CLAUDE_MODEL = "claude-haiku-4-5"

# Maximum tokens for the extraction response.
_MAX_TOKENS = 1024

# Valid sentiment categories Claude may return.
_VALID_CATEGORIES = frozenset(
    {"injury", "usage", "trade", "weather", "motivation", "legal", "general"}
)

# Event flag keys expected in Claude's JSON response.
# Kept in sync with PlayerSignal boolean fields and the rule-extractor
# event dict. See src/sentiment/processing/rule_extractor.py module
# docstring for the canonical event vocabulary.
_EVENT_FLAG_KEYS = frozenset(
    {
        # Injury (existing)
        "is_ruled_out",
        "is_inactive",
        "is_questionable",
        "is_suspended",
        "is_returning",
        # Transaction (Plan 61-02)
        "is_traded",
        "is_released",
        "is_signed",
        "is_activated",
        # Usage (Plan 61-02)
        "is_usage_boost",
        "is_usage_drop",
        # Weather (Plan 61-02)
        "is_weather_risk",
    }
)

EXTRACTION_PROMPT = """Analyze this NFL news article and extract player-specific signals.

For each player mentioned, provide:
- player_name: full name
- sentiment: float from -1.0 (very negative) to +1.0 (very positive) for fantasy football value
- confidence: float from 0.0 to 1.0
- category: one of [injury, usage, trade, weather, motivation, legal, general]
- events: dict of boolean flags {{
    is_ruled_out, is_inactive, is_questionable, is_suspended, is_returning,
    is_traded, is_released, is_signed, is_activated,
    is_usage_boost, is_usage_drop,
    is_weather_risk
  }}

Return JSON array. If no players mentioned, return empty array.

Article: {text}
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PlayerSignal:
    """Extracted sentiment signal for a single player mention in a document.

    The event boolean fields form the structured, model-facing surface
    of the sentiment pipeline. They are deliberately typed as plain
    booleans (never continuous) so downstream adjustments in
    ``src/projection_engine.py`` can map each flag to a tightly-bounded
    multiplier (see Phase 61 CONTEXT D-03).

    Attributes:
        player_name: Raw player name as extracted by Claude/rules.
        sentiment: Fantasy-value sentiment from -1.0 (very negative) to
            +1.0 (very positive).
        confidence: Extractor confidence, 0.0 to 1.0. Rule-based
            extraction caps at 0.7; Claude may go higher.
        category: Coarse topic label. One of
            {injury, usage, trade, weather, motivation, legal, general}.
        raw_excerpt: The article text that was analysed (truncated).

    Injury events (existing):
        is_ruled_out: Player has been officially ruled out.
        is_inactive: Player is on the inactive list.
        is_questionable: Player carries questionable designation.
        is_suspended: Player is suspended.
        is_returning: Player is returning from injury or suspension.

    Transaction events (Plan 61-02):
        is_traded: Player changed teams via trade.
        is_released: Player was released / waived / cut.
        is_signed: Player signed a new contract / extension.
        is_activated: Player activated from IR / PUP / suspension.
            Always co-set with is_returning for backward compatibility.

    Usage events (Plan 61-02):
        is_usage_boost: Player is the workhorse / named starter /
            primary target / lead back. Signals increased touches.
        is_usage_drop: Player is splitting carries / limited snaps /
            demoted / benched. Signals decreased touches.

    Weather events (Plan 61-02):
        is_weather_risk: Game is at risk due to blizzard, high winds,
            freezing rain, or game-in-doubt conditions.
    """

    player_name: str
    sentiment: float
    confidence: float
    category: str
    # Injury events (existing)
    is_ruled_out: bool = False
    is_inactive: bool = False
    is_questionable: bool = False
    is_suspended: bool = False
    is_returning: bool = False
    # Transaction events (Plan 61-02)
    is_traded: bool = False
    is_released: bool = False
    is_signed: bool = False
    is_activated: bool = False
    # Usage events (Plan 61-02)
    is_usage_boost: bool = False
    is_usage_drop: bool = False
    # Weather events (Plan 61-02)
    is_weather_risk: bool = False
    raw_excerpt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialise this signal to a plain dict for JSON storage.

        Returns:
            Dict representation with a nested ``events`` sub-dict
            containing all 12 structured event flags.
        """
        return {
            "player_name": self.player_name,
            "sentiment": self.sentiment,
            "confidence": self.confidence,
            "category": self.category,
            "events": {
                # Injury events
                "is_ruled_out": self.is_ruled_out,
                "is_inactive": self.is_inactive,
                "is_questionable": self.is_questionable,
                "is_suspended": self.is_suspended,
                "is_returning": self.is_returning,
                # Transaction events
                "is_traded": self.is_traded,
                "is_released": self.is_released,
                "is_signed": self.is_signed,
                "is_activated": self.is_activated,
                # Usage events
                "is_usage_boost": self.is_usage_boost,
                "is_usage_drop": self.is_usage_drop,
                # Weather events
                "is_weather_risk": self.is_weather_risk,
            },
            "raw_excerpt": self.raw_excerpt,
        }


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class ClaudeExtractor:
    """Extracts player sentiment signals from text using the Claude API.

    DEPRECATED for model-facing extraction per Phase 61 D-02.
    ------------------------------------------------------------------
    The primary production path is now
    ``src.sentiment.processing.rule_extractor.RuleExtractor`` — rules
    are deterministic, reproducible across backtests, and have no
    external dependency. ``SentimentPipeline`` in ``pipeline.py``
    therefore uses ``RuleExtractor`` in auto mode even when
    ``ANTHROPIC_API_KEY`` is set.

    This class is retained only for:
      1. Backward-compatible ``extractor_mode="claude"`` calls that
         explicitly opt into Claude-based extraction (e.g. comparison
         tests or ad-hoc re-runs).
      2. Historical tests that instantiate it directly.

    For website-facing summaries / news-card enrichment, use
    ``src.sentiment.enrichment.LLMEnrichment`` instead — that module
    is gated behind ``ENABLE_LLM_ENRICHMENT`` + ``ANTHROPIC_API_KEY``
    and adds ``summary`` + ``refined_category`` to Silver records
    without touching the model path (Phase 61 D-04).
    ------------------------------------------------------------------

    Uses claude-haiku (cheapest Anthropic model) via the ``anthropic``
    Python SDK.  Falls back gracefully when ``ANTHROPIC_API_KEY`` is not
    set — extraction is skipped and an empty list is returned.

    Attributes:
        model: The Claude model identifier to use.
        _client: The ``anthropic.Anthropic`` client, or None if the SDK is
            unavailable or the API key is missing.

    Example:
        >>> extractor = ClaudeExtractor()
        >>> doc = {"title": "Mahomes questionable", "body_text": "..."}
        >>> signals = extractor.extract(doc)
        >>> signals[0].player_name
        'Patrick Mahomes'
    """

    def __init__(self, model: str = _CLAUDE_MODEL) -> None:
        """Initialise the extractor and attempt to connect to Claude API.

        Args:
            model: Claude model ID to use for extraction.  Defaults to
                ``claude-haiku-4-5``.
        """
        self.model = model
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> Optional[Any]:
        """Create the Anthropic client if the API key is available.

        Returns:
            An ``anthropic.Anthropic`` client instance, or None if the key
            is absent or the SDK is not importable.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning(
                "ClaudeExtractor: ANTHROPIC_API_KEY not set. "
                "Extraction will be skipped for all documents."
            )
            return None

        try:
            import anthropic  # type: ignore

            return anthropic.Anthropic(api_key=api_key)
        except ImportError:
            logger.warning(
                "ClaudeExtractor: 'anthropic' package not installed. "
                "Run: pip install anthropic"
            )
            return None

    def _call_claude(self, text: str) -> str:
        """Send the extraction prompt to Claude and return the raw response text.

        Args:
            text: The article text to analyse (title + body combined).

        Returns:
            Raw string response from Claude.

        Raises:
            Exception: Any API-level error is propagated to the caller.
        """
        prompt = EXTRACTION_PROMPT.format(text=text)
        response = self._client.messages.create(
            model=self.model,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _parse_response(self, raw: str, excerpt: str) -> List[PlayerSignal]:
        """Parse Claude's JSON array response into PlayerSignal objects.

        Handles responses that embed the JSON array inside a markdown
        code-fence (```json ... ```) as Claude sometimes does.

        Args:
            raw: Raw string returned by Claude.
            excerpt: The original article text (stored on each signal for
                traceability).

        Returns:
            List of ``PlayerSignal`` objects (may be empty).
        """
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop first line (```json or ```) and last line (```)
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "ClaudeExtractor: JSON parse error — %s. Raw: %.200s", exc, raw
            )
            return []

        if not isinstance(data, list):
            logger.warning(
                "ClaudeExtractor: expected JSON array, got %s", type(data).__name__
            )
            return []

        signals: List[PlayerSignal] = []
        for item in data:
            signal = self._item_to_signal(item, excerpt)
            if signal is not None:
                signals.append(signal)

        return signals

    def _item_to_signal(self, item: Any, excerpt: str) -> Optional[PlayerSignal]:
        """Convert a single JSON object from Claude's response to a PlayerSignal.

        Args:
            item: A dict (or any object) from Claude's JSON array.
            excerpt: The article text used as the raw_excerpt field.

        Returns:
            A ``PlayerSignal`` if the item is valid, else None.
        """
        if not isinstance(item, dict):
            logger.debug("ClaudeExtractor: skipping non-dict item: %r", item)
            return None

        player_name = item.get("player_name", "").strip()
        if not player_name:
            logger.debug("ClaudeExtractor: item missing player_name, skipping")
            return None

        # Clamp sentiment and confidence to valid ranges
        try:
            sentiment = float(item.get("sentiment", 0.0))
        except (TypeError, ValueError):
            sentiment = 0.0
        sentiment = max(-1.0, min(1.0, sentiment))

        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        raw_category = str(item.get("category", "general")).lower().strip()
        category = raw_category if raw_category in _VALID_CATEGORIES else "general"

        events = item.get("events", {})
        if not isinstance(events, dict):
            events = {}

        return PlayerSignal(
            player_name=player_name,
            sentiment=sentiment,
            confidence=confidence,
            category=category,
            # Injury events
            is_ruled_out=bool(events.get("is_ruled_out", False)),
            is_inactive=bool(events.get("is_inactive", False)),
            is_questionable=bool(events.get("is_questionable", False)),
            is_suspended=bool(events.get("is_suspended", False)),
            is_returning=bool(events.get("is_returning", False)),
            # Transaction events (Plan 61-02)
            is_traded=bool(events.get("is_traded", False)),
            is_released=bool(events.get("is_released", False)),
            is_signed=bool(events.get("is_signed", False)),
            is_activated=bool(events.get("is_activated", False)),
            # Usage events (Plan 61-02)
            is_usage_boost=bool(events.get("is_usage_boost", False)),
            is_usage_drop=bool(events.get("is_usage_drop", False)),
            # Weather events (Plan 61-02)
            is_weather_risk=bool(events.get("is_weather_risk", False)),
            raw_excerpt=excerpt[:500],  # truncate to 500 chars for storage
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """True if the Claude client is initialised and ready to extract.

        Returns:
            Boolean availability flag.
        """
        return self._client is not None

    def extract(self, doc: Dict[str, Any]) -> List[PlayerSignal]:
        """Extract player sentiment signals from a Bronze JSON document.

        Combines the document's ``title`` and ``body_text`` fields into
        a single text block, then calls Claude for extraction.  Returns
        an empty list if the API key is missing, the text is empty, or
        Claude returns no players.

        Args:
            doc: Bronze JSON document dict.  Expected keys: ``title``
                (optional) and ``body_text`` (required).

        Returns:
            List of ``PlayerSignal`` objects, one per player mentioned.

        Example:
            >>> extractor = ClaudeExtractor()
            >>> signals = extractor.extract({"title": "Kelce questionable",
            ...                              "body_text": "Travis Kelce..."})
        """
        if not self.is_available:
            return []

        title = doc.get("title", "") or ""
        body = doc.get("body_text", "") or ""
        combined = f"{title}\n\n{body}".strip()

        if not combined:
            logger.debug("ClaudeExtractor: empty text, skipping doc")
            return []

        try:
            raw = self._call_claude(combined)
        except Exception as exc:
            logger.error(
                "ClaudeExtractor: API call failed for doc '%s': %s",
                doc.get("external_id", "unknown"),
                exc,
            )
            return []

        signals = self._parse_response(raw, combined)
        logger.debug(
            "ClaudeExtractor: extracted %d signals from doc '%s'",
            len(signals),
            doc.get("external_id", "unknown"),
        )
        return signals

    def extract_batch(
        self, docs: List[Dict[str, Any]]
    ) -> Dict[str, List[PlayerSignal]]:
        """Extract signals from a list of Bronze documents.

        Args:
            docs: List of Bronze JSON document dicts.  Each must have an
                ``external_id`` key for use as the return-dict key.

        Returns:
            Dict mapping ``external_id → list[PlayerSignal]``.  Documents
            that fail extraction map to an empty list.
        """
        results: Dict[str, List[PlayerSignal]] = {}
        for doc in docs:
            doc_id = str(doc.get("external_id", id(doc)))
            results[doc_id] = self.extract(doc)
        return results
