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
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Claude model to use — Haiku is cheapest and sufficient for extraction.
_CLAUDE_MODEL = "claude-haiku-4-5"

# Maximum tokens for the extraction response.
_MAX_TOKENS = 1024

# Extractor identity strings (single source of truth — reuse everywhere).
# These strings flow through ``PlayerSignal.extractor`` into the Silver
# record ``extractor`` top-level key. Plans 71-02..05 depend on these
# exact values being stable.
_EXTRACTOR_NAME_RULE = "rule"
_EXTRACTOR_NAME_CLAUDE_PRIMARY = "claude_primary"
_EXTRACTOR_NAME_CLAUDE_LEGACY = "claude_legacy"

# Default batch size for claude_primary extraction (Decision D-01:
# 5-10 docs per call; default 8). Plan 71-03 reads this constant when
# chunking Bronze documents into Claude calls.
BATCH_SIZE = 8

# Larger completion budget for batched extraction (Plan 71-03). The
# single-doc ``_MAX_TOKENS`` (1024) is insufficient for an 8-doc batch
# that may emit a JSON array of up to ~16 signals.
_MAX_TOKENS_BATCH = 4096

# Cap on the per-doc body text included in a batched prompt. Longer docs
# are truncated with an ellipsis marker so the prompt stays token-bounded.
_BATCH_DOC_BODY_TRUNCATE = 2000

# Cap on the number of active-roster names stitched into the cached
# system block (Plan 71-03). Prevents an unbounded roster parquet from
# blowing up the system prefix.
_ROSTER_BLOCK_MAX_NAMES = 1000

# System prefix for the claude_primary batched extractor. This block is
# static across every call in a cache window so Anthropic prompt-caching
# pays the creation cost once and reads the cached block thereafter.
#
# Plan 72-01 amendment: extended event-flag enumeration to 19 keys
# (12 prior + 7 new draft-season flags) and added a REQUIRED
# ``subject_type`` field so EVT-02 can route non-player items.
# Editing this prefix invalidates the Anthropic prompt cache and all
# recorded fixture SHAs — fixtures must be re-recorded in Plan 72-02.
_SYSTEM_PREFIX = """You are an NFL news analyst for a fantasy football product.
Extract structured signals from NFL articles about specific players.
For each player mentioned, return JSON with: player_name (or null for non-player subjects),
team_abbr (3-letter NFL team code, optional),
sentiment (-1.0 to +1.0 for fantasy value),
confidence (0.0 to 1.0),
category (one of: injury, usage, trade, weather, motivation, legal, general),
events (dict of boolean flags; see list below),
summary (<= 200 chars, 1 sentence),
source_excerpt (<= 500 chars verbatim from article).

Event flag keys: is_ruled_out, is_inactive, is_questionable, is_suspended, is_returning,
is_traded, is_released, is_signed, is_activated, is_usage_boost, is_usage_drop, is_weather_risk,
is_drafted, is_rumored_destination, is_coaching_change, is_trade_buzz, is_holdout, is_cap_cut, is_rookie_buzz.
REQUIRED subject_type field: "player" | "coach" | "team" | "reporter" (default "player").

Return a JSON array. For non-player subjects (coach/reporter/team news),
set player_name to null but populate team_abbr and set subject_type to one of
"coach", "team", or "reporter".

Respond with JSON only; no prose, no markdown fences."""

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
        # Draft-season events (Plan 72-01)
        "is_drafted",
        "is_rumored_destination",
        "is_coaching_change",
        "is_trade_buzz",
        "is_holdout",
        "is_cap_cut",
        "is_rookie_buzz",
    }
)

# Valid ``subject_type`` enum values (Plan 72-01). The Claude extractor
# emits ``subject_type`` per item; non-listed values are normalised to
# ``"player"`` by ``PlayerSignal.__post_init__`` (T-72-01-01 mitigation).
_VALID_SUBJECT_TYPES = frozenset({"player", "coach", "team", "reporter"})

EXTRACTION_PROMPT = """Analyze this NFL news article and extract player-specific signals.

For each player mentioned, provide:
- player_name: full name
- sentiment: float from -1.0 (very negative) to +1.0 (very positive) for fantasy football value
- confidence: float from 0.0 to 1.0
- category: one of [injury, usage, trade, weather, motivation, legal, general]
- subject_type: one of [player, coach, team, reporter] (default "player"; Plan 72-01)
- events: dict of boolean flags {{
    is_ruled_out, is_inactive, is_questionable, is_suspended, is_returning,
    is_traded, is_released, is_signed, is_activated,
    is_usage_boost, is_usage_drop,
    is_weather_risk,
    is_drafted, is_rumored_destination, is_coaching_change, is_trade_buzz,
    is_holdout, is_cap_cut, is_rookie_buzz
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

    Claude-primary extensions (Plan 71-01, optional — safe defaults):
        summary: One-sentence Claude-generated summary (<= 200 chars).
            Empty string for rule-based signals.
        source_excerpt: Raw snippet Claude cited as evidence
            (<= 500 chars). Empty string when absent.
        team_abbr: Canonical NFL team abbreviation. Non-player items
            (``player_name=null`` from Claude) carry a team here; player
            items may optionally populate it as enrichment.
        extractor: Producer identity. One of
            {``rule``, ``claude_primary``, ``claude_legacy``}.
            Defaults to ``"rule"`` for back-compat with prior runs.
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
    # Draft-season events (Plan 72-01) — additive only, all default False.
    # See 72-CONTEXT D-01 for the locked vocabulary. RuleExtractor emits
    # them via high-precision keyword patterns; Claude emits them via the
    # extended ``events`` sub-dict in the structured response (Plan 72-02
    # re-records the fixtures so the Anthropic prompt-cache picks up the
    # 19-flag enumeration).
    is_drafted: bool = False
    is_rumored_destination: bool = False
    is_coaching_change: bool = False
    is_trade_buzz: bool = False
    is_holdout: bool = False
    is_cap_cut: bool = False
    is_rookie_buzz: bool = False
    raw_excerpt: str = ""
    # Claude-primary extensions (Plan 71-01) — optional, additive only.
    # Defaults preserve existing RuleExtractor behaviour so the
    # rule-based path keeps producing identical Silver records.
    summary: str = ""
    source_excerpt: str = ""
    team_abbr: Optional[str] = None
    extractor: str = "rule"
    # Subject-type enum (Plan 72-01). One of {"player", "coach", "team",
    # "reporter"}; defaults to "player" for back-compat with the rule
    # path which only emits player items. Phase 72 EVT-02 routes
    # coach/team to a team rollup and reporter to non_player_news.
    # Threat T-72-01-01 mitigation: ``__post_init__`` normalises any
    # value outside ``_VALID_SUBJECT_TYPES`` back to ``"player"``.
    subject_type: str = "player"

    def __post_init__(self) -> None:
        """Validate ``subject_type`` against the locked enum.

        Threat T-72-01-01: an upstream Claude response (or a malformed
        rule path) could populate ``subject_type`` with an arbitrary
        string; downstream routing logic must never branch on
        unbounded input. We coerce any unknown value back to
        ``"player"`` and log at DEBUG so the audit trail is preserved
        without spamming the log.
        """
        if self.subject_type not in _VALID_SUBJECT_TYPES:
            logger.debug(
                "PlayerSignal: invalid subject_type=%r — normalising to "
                "'player'",
                self.subject_type,
            )
            self.subject_type = "player"

    def to_dict(self) -> Dict[str, Any]:
        """Serialise this signal to a plain dict for JSON storage.

        Returns:
            Dict representation with a nested ``events`` sub-dict
            containing all 19 structured event flags (12 existing + 7
            new draft-season flags from Plan 72-01), plus the Plan
            71-01 top-level extensions (``summary``, ``source_excerpt``,
            ``team_abbr``, ``extractor``) and the Plan 72-01 top-level
            ``subject_type`` enum.
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
                # Draft-season events (Plan 72-01)
                "is_drafted": self.is_drafted,
                "is_rumored_destination": self.is_rumored_destination,
                "is_coaching_change": self.is_coaching_change,
                "is_trade_buzz": self.is_trade_buzz,
                "is_holdout": self.is_holdout,
                "is_cap_cut": self.is_cap_cut,
                "is_rookie_buzz": self.is_rookie_buzz,
            },
            "raw_excerpt": self.raw_excerpt,
            # Plan 71-01 additive top-level keys
            "summary": self.summary,
            "source_excerpt": self.source_excerpt,
            "team_abbr": self.team_abbr,
            "extractor": self.extractor,
            # Plan 72-01 additive top-level enum
            "subject_type": self.subject_type,
        }


# ---------------------------------------------------------------------------
# DI seam — Protocol for the Anthropic client
# ---------------------------------------------------------------------------


@runtime_checkable
class ClaudeClient(Protocol):
    """Minimal duck-typed surface for the Anthropic client.

    The real ``anthropic.Anthropic`` instance satisfies this Protocol
    via its ``.messages.create(...)`` attribute chain. ``FakeClaudeClient``
    in ``tests/sentiment/fakes.py`` (Plan 71-02) also satisfies it.

    This seam lets Plan 71-03 batched extractor be injected with a
    fake without monkeypatching ``_build_client``. See 71-CONTEXT.md
    Decision D-02 for the rationale.

    Uses attribute access because ``anthropic.Anthropic`` exposes
    chained ``.messages.create(...)``, not a flat method. The
    ``messages`` attribute is expected to expose
    ``.create(model=..., max_tokens=..., system=..., messages=...)``
    returning a response object whose ``.content[0].text`` carries
    the Claude completion text (same shape the legacy
    ``ClaudeExtractor._call_claude`` already consumes).
    """

    messages: Any   # object with .create(...) -> response


# ---------------------------------------------------------------------------
# Batched-prompt helpers (module-level for deterministic SHA computation
# and test accessibility without instantiating the extractor)
# ---------------------------------------------------------------------------


def _format_batch_user_message(batch_docs: List[Dict[str, Any]]) -> str:
    """Build the per-batch user-message body sent to Claude.

    Each doc is rendered with its ``external_id`` so Claude can echo it
    back in the ``doc_id`` field of every response item. The pipeline
    uses that echoed ``doc_id`` to map signals back to source docs.

    Args:
        batch_docs: List of Bronze doc dicts. Must include ``external_id``
            (falls back to ``str(id(doc))``). ``title`` and ``body_text``
            are optional.

    Returns:
        Multi-line user message string; caller wraps it in
        ``{"role": "user", "content": ...}``.
    """
    parts: List[str] = ["Extract signals for the following articles."]
    for i, doc in enumerate(batch_docs, start=1):
        external_id = str(doc.get("external_id", id(doc)))
        title = doc.get("title", "") or ""
        body = doc.get("body_text", "") or ""
        if len(body) > _BATCH_DOC_BODY_TRUNCATE:
            body = body[:_BATCH_DOC_BODY_TRUNCATE] + "..."
        parts.append(f"\n--- DOC {i} (external_id={external_id}) ---")
        parts.append(f"TITLE: {title}")
        parts.append(f"BODY: {body}")
    parts.append(
        "\nReturn a single JSON array where each item includes a "
        "\"doc_id\" field matching the external_id from the header. "
        "This lets us map signals back to source docs."
    )
    return "\n".join(parts)


def _build_batched_prompt_for_sha(
    static_prefix: str,
    roster_block: str,
    batch_docs: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Build the exact ``(system, messages)`` pair that will be sent to Claude.

    This is factored out so tests (and the fixture-recording script) can
    compute the ``prompt_sha`` key without going through the full
    ``extract_batch_primary`` code path. The structure MUST stay byte-stable
    with what ``ClaudeExtractor._call_claude_batch`` sends or fixture SHAs
    will no longer match.

    Args:
        static_prefix: The cacheable system-prefix text (usually
            ``_SYSTEM_PREFIX``).
        roster_block: Joined active-player names (may be empty string).
        batch_docs: List of Bronze doc dicts for this batch.

    Returns:
        A tuple ``(system, messages)`` in the same shape the
        ``anthropic.Anthropic.messages.create`` API consumes. When
        ``roster_block`` is empty, the ``system`` list is a single entry
        (no second cached block).
    """
    system: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": static_prefix,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if roster_block:
        system.append(
            {
                "type": "text",
                "text": f"ACTIVE PLAYERS:\n{roster_block}",
                "cache_control": {"type": "ephemeral"},
            }
        )

    messages = [
        {"role": "user", "content": _format_batch_user_message(batch_docs)}
    ]
    return system, messages


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

    def __init__(
        self,
        model: str = _CLAUDE_MODEL,
        client: Optional[ClaudeClient] = None,
        roster_provider: Optional[Callable[[], List[str]]] = None,
        cost_log: Optional[Any] = None,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        """Initialise the extractor with optional DI seams (Plan 71-03).

        Args:
            model: Claude model ID to use for extraction. Defaults to
                ``claude-haiku-4-5``.
            client: Optional ``ClaudeClient``-Protocol-compatible object
                (the real ``anthropic.Anthropic`` instance, or a test
                double). When ``None``, the legacy ``_build_client`` path
                is used so existing ``extractor_mode="claude"`` calls
                keep working.
            roster_provider: Zero-arg callable returning the active-roster
                player names for the current week. Plan 71-03 caches the
                returned list in the system prefix of every batched
                Claude call via ``cache_control: {"type": "ephemeral"}``.
                When ``None`` or the returned list is empty, the cached
                roster block is dropped and a one-time warning is logged.
                **Determinism contract (Plan 71-02):** tests/benchmarks
                that exercise SHA-keyed fixture replay MUST pass
                ``roster_provider=lambda: []`` so the SHA computation
                depends only on the static prefix + per-doc body.
            cost_log: Optional ``src.sentiment.processing.cost_log.CostLog``
                instance (or any object exposing ``.write_record(CostRecord)``).
                When provided, one ``CostRecord`` is written per
                ``messages.create`` call. When ``None``, no cost
                accounting is performed (backward-compatible default).
            batch_size: Override for the per-call batch size. Defaults
                to the module-level ``BATCH_SIZE`` constant.
        """
        self.model = model
        self.batch_size = batch_size
        self.roster_provider = roster_provider
        self.cost_log = cost_log
        # Used to emit the empty-roster warning at most once per instance.
        self._empty_roster_warned = False
        # Constructor DI wins over env-var client building.
        self._client: Optional[Any] = (
            client if client is not None else self._build_client()
        )

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
    # Batched primary-path helpers (Plan 71-03)
    # ------------------------------------------------------------------

    def _system_prefix_for_test(self) -> str:
        """Return the cached static system prefix.

        Exists as a public-ish accessor so tests can compute the same
        ``prompt_sha`` the production ``extract_batch_primary`` path will
        produce, without copying the literal into the test file.
        """
        return _SYSTEM_PREFIX

    def _build_batched_prompt(self, batch_docs: List[Dict[str, Any]]) -> str:
        """Build the per-batch user-message body for a Claude call.

        Thin wrapper around the module-level ``_format_batch_user_message``
        so subclasses can override the formatter without touching the
        SHA-deterministic builder.

        Args:
            batch_docs: List of Bronze doc dicts for this batch.

        Returns:
            Multi-line user-message string.
        """
        return _format_batch_user_message(batch_docs)

    def _get_roster_block(self) -> str:
        """Resolve the active-roster block for the cached system prefix.

        Calls ``self.roster_provider()`` (if set), joins the returned
        player names with ", ", and caps at ``_ROSTER_BLOCK_MAX_NAMES``
        entries. Any exception inside the provider is logged as a warning
        and an empty string is returned (fail-open).

        Returns:
            Comma-joined roster string, or the empty string when no
            provider is configured or it fails.
        """
        if self.roster_provider is None:
            return ""
        try:
            names = list(self.roster_provider())
        except Exception as exc:  # noqa: BLE001 — fail-open
            logger.warning(
                "ClaudeExtractor: roster_provider raised %s; proceeding "
                "without cached roster block.",
                exc,
            )
            return ""
        if not names:
            return ""
        return ", ".join(names[:_ROSTER_BLOCK_MAX_NAMES])

    def _call_claude_batch(
        self, batch_docs: List[Dict[str, Any]]
    ) -> Tuple[str, Any]:
        """Send a single batched prompt to Claude and return text + usage.

        Constructs the ``system`` list with ``cache_control`` markers on
        the static prefix and (if non-empty) the active-roster block, then
        calls ``self._client.messages.create(...)``.

        Args:
            batch_docs: List of Bronze doc dicts for this batch.

        Returns:
            Tuple of ``(response_text, usage_object)`` where
            ``usage_object`` exposes ``.input_tokens``, ``.output_tokens``,
            ``.cache_read_input_tokens``, ``.cache_creation_input_tokens``.
            Older SDK versions that don't expose the cache fields are
            handled gracefully — missing attrs default to 0 in the caller.

        Raises:
            Exception: any error from the underlying SDK call propagates
                up so ``extract_batch_primary`` can re-raise to the
                pipeline (Plan 71-04) for per-doc soft fallback.
        """
        roster_block = self._get_roster_block()
        if not roster_block and not self._empty_roster_warned:
            logger.warning(
                "ClaudeExtractor.extract_batch_primary: roster_provider "
                "produced no names; proceeding with single cached system "
                "entry only."
            )
            self._empty_roster_warned = True

        system, messages = _build_batched_prompt_for_sha(
            static_prefix=_SYSTEM_PREFIX,
            roster_block=roster_block,
            batch_docs=batch_docs,
        )
        response = self._client.messages.create(
            model=self.model,
            max_tokens=_MAX_TOKENS_BATCH,
            system=system,
            messages=messages,
        )
        return response.content[0].text, response.usage

    def _item_to_claude_signal(
        self, item: Dict[str, Any], excerpt: str
    ) -> Optional[PlayerSignal]:
        """Convert a Claude JSON item to a ``claude_primary`` PlayerSignal.

        Re-uses the legacy ``_item_to_signal`` pipeline for sentiment
        clamping, confidence clamping, category validation, and event-flag
        coercion, then overrides four Plan 71-01 fields:

        * ``extractor="claude_primary"`` (overrides the ``"rule"`` default)
        * ``summary`` truncated to 200 chars
        * ``source_excerpt`` truncated to 500 chars
        * ``team_abbr`` from the Claude item (may be ``None``)

        Args:
            item: One decoded JSON object from Claude's response array.
            excerpt: The batch-level raw text for traceability.

        Returns:
            A ``PlayerSignal`` with ``extractor="claude_primary"`` when
            the item carries a non-empty player name, else ``None``.
        """
        sig = self._item_to_signal(item, excerpt)
        if sig is None:
            return None
        summary = (item.get("summary") or "")[:200]
        source_excerpt = (item.get("source_excerpt") or "")[:500]
        team_abbr = item.get("team_abbr")
        if isinstance(team_abbr, str):
            team_abbr = team_abbr.strip() or None
        sig.summary = summary
        sig.source_excerpt = source_excerpt
        sig.team_abbr = team_abbr
        sig.extractor = _EXTRACTOR_NAME_CLAUDE_PRIMARY
        return sig

    def _parse_batch_response(
        self,
        raw: str,
        batch_docs: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, List[PlayerSignal]], List[Dict[str, Any]]]:
        """Parse Claude's JSON array response into per-doc signals.

        Signals with a non-null ``player_name`` are bucketed by
        ``doc_id`` (matched against the batch's ``external_id`` values).
        Items with ``player_name: null`` (or empty) are captured
        separately so Plan 72 (EVT-02) can route them to non-player
        storage.

        Parse errors are swallowed — a ``JSONDecodeError`` or unexpected
        array shape returns ``({}, [])`` and logs a warning. API errors
        (from ``_call_claude_batch``) are the only failure mode that
        propagates up; the pipeline in Plan 71-04 catches those and
        falls back to RuleExtractor per doc.

        Args:
            raw: Raw string response text from Claude.
            batch_docs: The same list passed to ``_call_claude_batch``;
                used to look up ``external_id`` ↔ doc mapping.

        Returns:
            Tuple ``(by_doc_id, non_player_items)`` where
            ``by_doc_id`` maps ``external_id`` → list of PlayerSignal
            (only docs with at least one matched signal appear) and
            ``non_player_items`` is a list of dicts with
            ``{external_id, doc_id, team_abbr, summary, sentiment,
              confidence, category, source_excerpt}``.
        """
        # Strip markdown code fences (same logic as _parse_response).
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "ClaudeExtractor.extract_batch_primary: JSON parse error "
                "— %s. Raw: %.200s",
                exc,
                raw,
            )
            return {}, []

        if not isinstance(data, list):
            logger.warning(
                "ClaudeExtractor.extract_batch_primary: expected JSON array, "
                "got %s",
                type(data).__name__,
            )
            return {}, []

        by_doc_id: Dict[str, List[PlayerSignal]] = {}
        non_player_items: List[Dict[str, Any]] = []

        # Build a fast external_id ↔ doc lookup for doc_id matching.
        docs_by_id = {
            str(doc.get("external_id", "")): doc for doc in batch_docs
        }
        # Joined batch excerpt for signals when per-doc source is absent.
        batch_excerpt = "\n\n".join(
            f"{d.get('title','')} {d.get('body_text','')}" for d in batch_docs
        )

        for item in data:
            if not isinstance(item, dict):
                logger.debug(
                    "ClaudeExtractor.extract_batch_primary: skipping "
                    "non-dict item: %r",
                    item,
                )
                continue

            doc_id = str(item.get("doc_id", "")).strip()
            # Determine the per-doc excerpt when we have a matched doc.
            source_doc = docs_by_id.get(doc_id)
            excerpt = (
                f"{source_doc.get('title','')} {source_doc.get('body_text','')}"
                if source_doc
                else batch_excerpt
            )

            player_name = item.get("player_name")
            if player_name is None or (
                isinstance(player_name, str) and not player_name.strip()
            ):
                # Non-player item — capture separately for Plan 72 routing.
                non_player_items.append(
                    {
                        "doc_id": doc_id,
                        "external_id": doc_id,
                        "team_abbr": item.get("team_abbr"),
                        "summary": (item.get("summary") or "")[:200],
                        "sentiment": item.get("sentiment"),
                        "confidence": item.get("confidence"),
                        "category": item.get("category"),
                        "source_excerpt": (
                            item.get("source_excerpt") or ""
                        )[:500],
                    }
                )
                continue

            if not doc_id or doc_id not in docs_by_id:
                # Claude echoed a doc_id we never sent — drop with a debug log.
                logger.debug(
                    "ClaudeExtractor.extract_batch_primary: unmatched "
                    "doc_id=%r for player_name=%r",
                    doc_id,
                    player_name,
                )
                continue

            sig = self._item_to_claude_signal(item, excerpt)
            if sig is None:
                continue
            by_doc_id.setdefault(doc_id, []).append(sig)

        return by_doc_id, non_player_items

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

    # ------------------------------------------------------------------
    # Plan 71-03: batched primary extraction
    # ------------------------------------------------------------------

    def extract_batch_primary(
        self,
        docs: List[Dict[str, Any]],
        season: int,
        week: int,
    ) -> Tuple[Dict[str, List[PlayerSignal]], List[Dict[str, Any]]]:
        """Primary-path batched extraction producing claude_primary signals.

        Slices ``docs`` into batches of ``self.batch_size`` (defaults to
        ``BATCH_SIZE=8``) and sends each batch as a single ``messages.create``
        call with Anthropic prompt caching on the static system prefix and
        the active-roster block. Each call's usage counters are (optionally)
        logged via ``self.cost_log``.

        Per-batch behaviour:

        * **Parse errors** (malformed JSON in the Claude response) are
          swallowed — the batch produces zero signals and a warning is
          logged. Extraction continues with the next batch.
        * **API errors** (anything ``messages.create`` raises) propagate up
          so the pipeline (Plan 71-04) can catch them and substitute
          ``RuleExtractor`` per doc (D-06 per-doc soft fallback).

        Args:
            docs: List of Bronze document dicts. Each should carry
                ``external_id``; ``title`` and ``body_text`` are
                concatenated into the batched prompt.
            season: NFL season year (used for the cost-log partition).
            week: NFL week number 1-22 (used for the cost-log partition).

        Returns:
            Tuple ``(by_doc_id, non_player_items)``:

            * ``by_doc_id``: Dict mapping ``external_id`` → list of
              ``PlayerSignal`` objects with ``extractor="claude_primary"``.
              Only docs with at least one matched Claude item appear.
            * ``non_player_items``: List of dicts for items where
              ``player_name`` was ``None`` / empty (coach moves, front
              office news, etc.). Each dict carries
              ``{doc_id, external_id, team_abbr, summary, sentiment,
                confidence, category, source_excerpt}``.

        Raises:
            Exception: whatever the underlying ``messages.create`` call
                raises. Pipeline code is responsible for catching and
                performing per-doc fallback to ``RuleExtractor``.
        """
        if self._client is None:
            logger.warning(
                "ClaudeExtractor.extract_batch_primary: no client available "
                "(ANTHROPIC_API_KEY unset and no DI-injected client). "
                "Returning empty result."
            )
            return {}, []

        # Lazy-import the cost_log helpers to avoid a circular import at
        # module load time (cost_log is a sibling module).
        from src.sentiment.processing.cost_log import (
            CostRecord,
            compute_cost_usd,
            new_call_id,
        )

        by_doc_id: Dict[str, List[PlayerSignal]] = {}
        non_player_items: List[Dict[str, Any]] = []

        n = len(docs)
        step = max(1, int(self.batch_size))
        for start in range(0, n, step):
            batch = docs[start : start + step]
            raw, usage = self._call_claude_batch(batch)

            batch_by_doc, batch_non_player = self._parse_batch_response(
                raw, batch
            )
            for doc_id, sigs in batch_by_doc.items():
                by_doc_id.setdefault(doc_id, []).extend(sigs)
            non_player_items.extend(batch_non_player)

            if self.cost_log is not None:
                input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
                cache_read = int(
                    getattr(usage, "cache_read_input_tokens", 0) or 0
                )
                cache_creation = int(
                    getattr(usage, "cache_creation_input_tokens", 0) or 0
                )
                record = CostRecord(
                    call_id=new_call_id(),
                    doc_count=len(batch),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_input_tokens=cache_read,
                    cache_creation_input_tokens=cache_creation,
                    cost_usd=compute_cost_usd(
                        input_tokens,
                        output_tokens,
                        cache_read,
                        cache_creation,
                    ),
                    ts=datetime.now(timezone.utc).isoformat(),
                    season=int(season),
                    week=int(week),
                )
                try:
                    self.cost_log.write_record(record)
                except Exception as exc:  # noqa: BLE001 — never crash cron
                    logger.warning(
                        "ClaudeExtractor.extract_batch_primary: cost_log "
                        "write_record failed (%s); continuing.",
                        exc,
                    )

        return by_doc_id, non_player_items
