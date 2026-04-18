"""Rule-based text extraction for NFL sentiment signals.

Uses regex patterns to extract player status, roster moves, usage
changes, weather risk, and sentiment from news articles and Reddit
posts. No external API required -- works offline with zero cost.

This extractor is the PRIMARY model-facing signal source per
Phase 61 CONTEXT D-02. The optional Claude Haiku extractor in
``extractor.py`` is demoted to website-only enrichment (D-04).

Event schema (LOCKED for Plan 61-03 consumption)
------------------------------------------------
The extractor emits structured boolean flags via ``PlayerSignal``
(see ``src/sentiment/processing/extractor.py``). The full event
vocabulary is:

Injury events (5)::

    is_ruled_out     — officially ruled out for a game
    is_inactive      — on the inactive list
    is_questionable  — questionable / game-time decision
    is_suspended     — league or team suspension
    is_returning     — returning from injury or suspension

Transaction events (4)::

    is_traded        — changed teams via trade
    is_released      — released, waived, cut
    is_signed        — signed contract, extension, inked deal
    is_activated     — activated from IR/PUP/suspension
                       (also sets is_returning for backward compat)

Usage events (2)::

    is_usage_boost   — named starter, workhorse, lead back,
                       primary target, promoted, increased role
    is_usage_drop    — benched, demoted, splitting carries,
                       limited snaps, timeshare, committee

Weather events (1)::

    is_weather_risk  — blizzard, high winds >= 25 mph, game in
                       doubt, freezing rain, heavy rain

Design principles
-----------------
* HIGH PRECISION > recall (T-61-02-01): prefer false negatives
  over false positives. Ambiguous phrases ("considered in trade
  talks") do NOT fire the flag. Adversarial phrasing is blocked
  by word-boundary anchors and bounded quantifiers.
* No unbounded ``.*`` inside alternations (T-61-02-02): all
  numeric/repeating patterns use bounded quantifiers to prevent
  catastrophic regex backtracking.
* Confidence ceiling ``_RULE_CONFIDENCE = 0.7`` applies to every
  rule-produced signal; Claude may go higher.
* Category vocabulary must stay inside ``_VALID_CATEGORIES``
  from ``extractor.py``:
  {injury, usage, trade, weather, motivation, legal, general}.

Public API
----------
>>> extractor = RuleExtractor()
>>> signals = extractor.extract(doc)
>>> [s.player_name for s in signals]
['Patrick Mahomes']
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.sentiment.processing.extractor import PlayerSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, sentiment, category, event_flags_dict).
# Event flags must match PlayerSignal fields; see module docstring
# for the canonical event vocabulary locked for Plan 61-03.

_PatternEntry = Tuple[re.Pattern, float, str, Dict[str, bool]]


def _compile_patterns() -> List[_PatternEntry]:
    """Build the ordered list of pattern rules.

    Pattern priority is controlled by list order: the first regex
    that matches the document wins. More specific patterns must
    therefore appear before more general ones (e.g. ``re-signed``
    must not accidentally match a ``released`` pattern — handled by
    anchoring on ``\\bsigned\\s+`` and pairing with re-sign variants
    under ``_transaction``).

    Returns:
        List of (regex, sentiment, category, events) tuples.
    """
    entries: List[_PatternEntry] = []

    # -- Transaction patterns (Plan 61-02) --
    # Activation must be declared BEFORE injury patterns so that a
    # headline like "Kelce activated from injured reserve" fires the
    # positive activation flag rather than the negative IR flag.
    # Ordered: activation → released → signed → traded. Each entry
    # sets a specific transaction flag; activations also set
    # ``is_returning`` for backward compatibility with consumers that
    # predate the event expansion.
    _transaction = [
        # Activation from IR/PUP/suspension — most specific, first
        (
            r"activated\s+from\s+(?:IR|injured\s+reserve|PUP|suspension)",
            0.4,
            {"is_activated": True, "is_returning": True},
        ),
        # Release / waiver — before "signed" so "waived" does not
        # collide with "re-signed" semantics
        (
            r"released|waived|cut\s+by|designated\s+for\s+release",
            -0.5,
            {"is_released": True},
        ),
        # Signed / extension — anchored on word-boundary + explicit
        # preposition + bounded contract-length phrase to avoid
        # catching "re-signed" (which prefixes with re-) or bare
        # "signed" in unrelated phrases. Also matches "inked a deal"
        # and "agrees to terms".
        (
            r"\bsigned\s+(?:with|a\s+(?:one|two|three|four|five)[\s-]year)"
            r"|agrees?\s+to\s+terms"
            r"|contract\s+extension"
            r"|inked\s+a\s+deal"
            r"|claimed\s+off\s+waivers",
            0.2,
            {"is_signed": True},
        ),
        # Trade — requires deterministic trade phrasing. Speculation
        # phrases like "considered in trade talks" are deliberately
        # NOT matched (precision > recall per T-61-02-01).
        (
            r"traded\s+to"
            r"|deal\s+sends"
            r"|acquired\s+(?:via\s+trade|in\s+trade)"
            r"|dealt\s+to"
            r"|trade\s+(?:sends|acquires)",
            -0.2,
            {"is_traded": True},
        ),
    ]
    for pat, sent, evts in _transaction:
        entries.append((re.compile(pat, re.IGNORECASE), sent, "trade", evts))

    # -- Injury patterns --
    # Declared AFTER transactions so that "activated from IR" fires
    # the activation branch rather than the "injured reserve" branch.
    _injury = [
        # Severe negative
        (
            r"ruled\s+out|will\s+not\s+play|out\s+for\s+(?:the\s+)?(?:season|game|week)",
            -0.9,
            {"is_ruled_out": True},
        ),
        (
            r"placed\s+on\s+IR|injured\s+reserve|out\s+for\s+season",
            -0.9,
            {"is_ruled_out": True},
        ),
        (r"inactive|is\s+inactive", -0.7, {"is_inactive": True}),
        # Moderate negative
        (r"doubtful|unlikely\s+to\s+play", -0.6, {}),
        (r"did\s+not\s+practice|DNP|sat\s+out", -0.4, {}),
        (
            r"questionable|game[\s-]time\s+decision|50[\s-]50",
            -0.3,
            {"is_questionable": True},
        ),
        (r"limited\s+participant|limited\s+practice|limited\s+in", -0.1, {}),
        # Suspension — sets is_suspended explicitly so rules can fire
        # it without needing the Claude events dict. Matches both
        # numeric ("suspended 4 games") and word ("suspended four
        # games") game counts, plus "by the league/team" and
        # "indefinitely" variants. Bounded quantifier prevents
        # catastrophic backtracking (T-61-02-02).
        (
            r"suspended\s+(?:"
            r"by\s+the\s+(?:league|team)"
            r"|\d{1,2}\s+games?"
            r"|(?:one|two|three|four|five|six|eight|ten|twelve)\s+games?"
            r"|indefinitely"
            r")"
            r"|serving\s+a\s+suspension",
            -0.8,
            {"is_suspended": True},
        ),
        # Positive — recovery / return-to-action
        (r"return(?:ed)?\s+to\s+practice|coming\s+back", 0.4, {"is_returning": True}),
        (
            r"full\s+participant|full\s+practice|fully\s+healthy",
            0.3,
            {"is_returning": True},
        ),
    ]
    for pat, sent, evts in _injury:
        entries.append((re.compile(pat, re.IGNORECASE), sent, "injury", evts))

    # -- Role change patterns --
    _role = [
        (
            r"benched|demoted|losing\s+(?:starting\s+)?(?:job|snaps)|losing\s+starting",
            -0.6,
            {"is_usage_drop": True},
        ),
        (r"decreased\s+role|reduced\s+workload", -0.3, {"is_usage_drop": True}),
        (
            r"named\s+starter|earned\s+starting|promoted|will\s+start",
            0.5,
            {"is_usage_boost": True},
        ),
        (
            r"increased\s+role|expanded\s+role|more\s+touches",
            0.3,
            {"is_usage_boost": True},
        ),
    ]
    for pat, sent, evts in _role:
        entries.append((re.compile(pat, re.IGNORECASE), sent, "usage", evts))

    # -- General sentiment patterns --
    _positive = [
        (r"game[\s-]changing|monster\s+game", 0.5, {}),
        (
            r"breakout|career\s+game|dominant(?:\s+performance)?|elite|explosive",
            0.4,
            {},
        ),
    ]
    for pat, sent, evts in _positive:
        entries.append((re.compile(pat, re.IGNORECASE), sent, "general", evts))

    _negative = [
        (r"fumble\s+issues|drop\s+problems", -0.4, {}),
        (r"struggling|ineffective|concern|disappointing|bust|droppable", -0.3, {}),
    ]
    for pat, sent, evts in _negative:
        entries.append((re.compile(pat, re.IGNORECASE), sent, "general", evts))

    return entries


_PATTERNS: List[_PatternEntry] = _compile_patterns()

# Regex for extracting candidate player names from text (Title Case two-word).
# Handles hyphenated names (Amon-Ra), Mc/Mac prefixes (McCaffrey, McVay),
# St. prefix (St. Brown), apostrophes (O'Brien), and suffixes (Jr., III).
_NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z']{1,15}(?:[.-][A-Z][a-z']{0,15})*"
    r"(?:\.[A-Z]\.?)?\s"
    r"(?:St\.\s)?(?:Mc|Mac)?[A-Z][a-z']{1,20}(?:-[A-Z][a-z']{1,15})?"
    r"(?:\s(?:Jr|Sr|II|III|IV|V)\.?)?)\b"
)

# Rule-based confidence ceiling
_RULE_CONFIDENCE = 0.7


# ---------------------------------------------------------------------------
# Extractor class
# ---------------------------------------------------------------------------


class RuleExtractor:
    """Rule-based extractor producing PlayerSignal objects from plain text.

    Uses regex patterns to detect injury statuses, roster moves, role
    changes, and general sentiment. Always available (no external
    dependency).

    The output format matches ``ClaudeExtractor.extract()`` exactly so
    the two can be used interchangeably in the pipeline.

    Example:
        >>> ext = RuleExtractor()
        >>> signals = ext.extract({"title": "Kelce ruled out", "body_text": "..."})
        >>> signals[0].is_ruled_out
        True
    """

    @property
    def is_available(self) -> bool:
        """Always returns True -- no external dependency required.

        Returns:
            True.
        """
        return True

    def extract(self, doc: Dict[str, Any]) -> List[PlayerSignal]:
        """Extract player sentiment signals from a Bronze document.

        Combines the document's ``title`` and ``body_text`` fields, scans
        for regex pattern matches, and returns one ``PlayerSignal`` per
        detected player-pattern combination.

        Args:
            doc: Bronze document dict with ``title`` and/or ``body_text``.

        Returns:
            List of ``PlayerSignal`` objects (may be empty).
        """
        title = doc.get("title", "") or ""
        body = doc.get("body_text", "") or ""
        combined = f"{title}\n\n{body}".strip()

        if not combined:
            return []

        # Find all candidate player names
        candidate_names = self._extract_names(combined)
        if not candidate_names:
            return []

        # Find all matching patterns in the text
        matches = self._find_matches(combined)
        if not matches:
            return []

        # For each player, pick the best (highest-priority) matching pattern
        signals: List[PlayerSignal] = []
        seen_players: set = set()

        for name in candidate_names:
            if name in seen_players:
                continue

            # Find the best match: first match wins (patterns are priority-ordered)
            best = matches[0]
            sentiment, category, events = best

            signal = PlayerSignal(
                player_name=name,
                sentiment=sentiment,
                confidence=_RULE_CONFIDENCE,
                category=category,
                # Injury events
                is_ruled_out=events.get("is_ruled_out", False),
                is_inactive=events.get("is_inactive", False),
                is_questionable=events.get("is_questionable", False),
                is_suspended=events.get("is_suspended", False),
                is_returning=events.get("is_returning", False),
                # Transaction events (Plan 61-02)
                is_traded=events.get("is_traded", False),
                is_released=events.get("is_released", False),
                is_signed=events.get("is_signed", False),
                is_activated=events.get("is_activated", False),
                # Usage events (Plan 61-02)
                is_usage_boost=events.get("is_usage_boost", False),
                is_usage_drop=events.get("is_usage_drop", False),
                # Weather events (Plan 61-02)
                is_weather_risk=events.get("is_weather_risk", False),
                raw_excerpt=combined[:500],
            )
            signals.append(signal)
            seen_players.add(name)

        return signals

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_names(self, text: str) -> List[str]:
        """Extract candidate player names from text.

        Args:
            text: Combined title + body text.

        Returns:
            Deduplicated list of name strings.
        """
        found = _NAME_PATTERN.findall(text)
        seen: set = set()
        result: List[str] = []
        for name in found:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def _find_matches(self, text: str) -> List[Tuple[float, str, Dict[str, bool]]]:
        """Find all pattern matches in the text.

        Args:
            text: Combined title + body text.

        Returns:
            List of (sentiment, category, events) tuples for each match,
            in pattern-priority order.
        """
        matches: List[Tuple[float, str, Dict[str, bool]]] = []
        for regex, sentiment, category, events in _PATTERNS:
            if regex.search(text):
                matches.append((sentiment, category, events))
        return matches

    def extract_batch(
        self, docs: List[Dict[str, Any]]
    ) -> Dict[str, List[PlayerSignal]]:
        """Extract signals from a list of Bronze documents.

        Args:
            docs: List of Bronze JSON document dicts.

        Returns:
            Dict mapping ``external_id`` to list of ``PlayerSignal``.
        """
        results: Dict[str, List[PlayerSignal]] = {}
        for doc in docs:
            doc_id = str(doc.get("external_id", id(doc)))
            results[doc_id] = self.extract(doc)
        return results
