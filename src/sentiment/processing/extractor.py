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
_EVENT_FLAG_KEYS = frozenset(
    {
        "is_ruled_out",
        "is_inactive",
        "is_questionable",
        "is_suspended",
        "is_returning",
    }
)

EXTRACTION_PROMPT = """Analyze this NFL news article and extract player-specific signals.

For each player mentioned, provide:
- player_name: full name
- sentiment: float from -1.0 (very negative) to +1.0 (very positive) for fantasy football value
- confidence: float from 0.0 to 1.0
- category: one of [injury, usage, trade, weather, motivation, legal, general]
- events: dict of boolean flags {{is_ruled_out, is_inactive, is_questionable, is_suspended, is_returning}}

Return JSON array. If no players mentioned, return empty array.

Article: {text}
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PlayerSignal:
    """Extracted sentiment signal for a single player mention in a document.

    Attributes:
        player_name: Raw player name as extracted by Claude.
        sentiment: Fantasy-value sentiment from -1.0 (very negative) to
            +1.0 (very positive).
        confidence: Claude's confidence in this extraction, 0.0 to 1.0.
        category: Coarse topic label for the signal.
        is_ruled_out: Player has been officially ruled out.
        is_inactive: Player is on the inactive list.
        is_questionable: Player carries questionable designation.
        is_suspended: Player is suspended.
        is_returning: Player is returning from injury or suspension.
        raw_excerpt: The article text that was analysed (truncated if long).
    """

    player_name: str
    sentiment: float
    confidence: float
    category: str
    is_ruled_out: bool = False
    is_inactive: bool = False
    is_questionable: bool = False
    is_suspended: bool = False
    is_returning: bool = False
    raw_excerpt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialise this signal to a plain dict for JSON storage.

        Returns:
            Dict representation of all fields.
        """
        return {
            "player_name": self.player_name,
            "sentiment": self.sentiment,
            "confidence": self.confidence,
            "category": self.category,
            "events": {
                "is_ruled_out": self.is_ruled_out,
                "is_inactive": self.is_inactive,
                "is_questionable": self.is_questionable,
                "is_suspended": self.is_suspended,
                "is_returning": self.is_returning,
            },
            "raw_excerpt": self.raw_excerpt,
        }


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class ClaudeExtractor:
    """Extracts player sentiment signals from text using the Claude API.

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
            logger.warning("ClaudeExtractor: JSON parse error — %s. Raw: %.200s", exc, raw)
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

    def _item_to_signal(
        self, item: Any, excerpt: str
    ) -> Optional[PlayerSignal]:
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
            is_ruled_out=bool(events.get("is_ruled_out", False)),
            is_inactive=bool(events.get("is_inactive", False)),
            is_questionable=bool(events.get("is_questionable", False)),
            is_suspended=bool(events.get("is_suspended", False)),
            is_returning=bool(events.get("is_returning", False)),
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
