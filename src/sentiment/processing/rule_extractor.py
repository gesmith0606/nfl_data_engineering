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

Draft-season events (7, Plan 72-01)::

    is_drafted               — player was selected in the NFL Draft
    is_rumored_destination   — speculation that names a specific team
    is_coaching_change       — head coach / coordinator hire-or-fire
    is_trade_buzz            — soft trade speculation (no team named)
    is_holdout               — skipping minicamp / OTAs / training camp
    is_cap_cut               — release driven by salary-cap moves
    is_rookie_buzz           — pre-draft prospect hype / draft-board surge

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

    # -- Role change / usage patterns --
    # Priority order: strong-signal usage phrases first (workhorse,
    # primary target, lead back), then the original role pattern set.
    # All entries set is_usage_boost or is_usage_drop so Plan 61-03's
    # apply_event_adjustments can key on structured flags rather than
    # continuous sentiment (D-03).
    _role = [
        # Strong usage-boost phrases (new in 61-02)
        (
            r"named\s+starter"
            r"|earned\s+starting"
            r"|expected\s+to\s+start"
            r"|will\s+start"
            r"|workhorse(?:\s+back)?"
            r"|lead\s+back"
            r"|primary\s+target"
            r"|bell[\s-]cow",
            0.5,
            {"is_usage_boost": True},
        ),
        # Promotion / increased workload (existing, augmented)
        (
            r"increased\s+role"
            r"|expanded\s+role"
            r"|more\s+touches"
            r"|promoted\s+to\s+starter"
            r"|promoted",
            0.3,
            {"is_usage_boost": True},
        ),
        # Strong usage-drop phrases (new in 61-02)
        # Bounded quantifier on \d{1,2} prevents catastrophic
        # backtracking (T-61-02-02).
        (
            r"splitting\s+carries"
            r"|timeshare"
            r"|committee\s+back"
            r"|limited\s+snaps"
            r"|limited\s+to\s+\d{1,2}\s+snaps"
            r"|saw\s+only"
            r"|rotational",
            -0.3,
            {"is_usage_drop": True},
        ),
        # Bench / demotion (existing, augmented with 'demoted to backup')
        (
            r"benched"
            r"|demoted(?:\s+to\s+backup)?"
            r"|losing\s+(?:starting\s+)?(?:job|snaps)"
            r"|losing\s+starting"
            r"|decreased\s+role"
            r"|reduced\s+workload",
            -0.6,
            {"is_usage_drop": True},
        ),
    ]
    for pat, sent, evts in _role:
        entries.append((re.compile(pat, re.IGNORECASE), sent, "usage", evts))

    # -- Weather patterns (Plan 61-02) --
    # Only fire is_weather_risk for extreme conditions that realistically
    # affect pass/rush volume or accuracy. Benign mentions ("light rain
    # on Wednesday practice") deliberately do NOT match.
    # Bounded \d{2,} quantifier prevents catastrophic regex backtracking
    # (T-61-02-02); the threshold of two-digit wind speeds starts at 10
    # mph, which with the "sustained/gusts" anchor filters out casual
    # wind mentions.
    _weather = [
        (
            r"blizzard|ice\s+storm|snowstorm|white[\s-]out\s+conditions",
            -0.4,
            {"is_weather_risk": True},
        ),
        (
            r"high\s+winds"
            r"|wind\s+gusts"
            r"|(?:sustained|gusts?)\s+(?:of\s+|up\s+to\s+)?\d{2,}\s*mph"
            r"|winds?\s+(?:over|above|of)\s+\d{2,}",
            -0.3,
            {"is_weather_risk": True},
        ),
        (
            r"game\s+(?:in\s+doubt|could\s+be\s+postponed|may\s+be\s+moved)"
            r"|weather\s+delay",
            -0.3,
            {"is_weather_risk": True},
        ),
        (
            r"heavy\s+rain|monsoon|torrential|freezing\s+rain",
            -0.2,
            {"is_weather_risk": True},
        ),
    ]
    for pat, sent, evts in _weather:
        entries.append((re.compile(pat, re.IGNORECASE), sent, "weather", evts))

    # -- Draft-season patterns (Plan 72-01) --
    # 7 high-precision keyword patterns for the new draft-season event
    # flags. The Claude path is the primary producer for these events
    # (it can disambiguate context that bare keywords cannot), so the
    # rule path is a low-confidence zero-cost fallback. Signals that
    # ONLY fire draft-season flags are confidence-capped at
    # ``_DRAFT_SEASON_CONFIDENCE`` (0.5) inside ``RuleExtractor.extract``.
    #
    # Bounded quantifiers + word-boundary anchors per T-72-01-02
    # (no unbounded ``.*`` inside alternations — prevents catastrophic
    # backtracking on adversarial Bronze text).
    _draft_season = [
        # is_drafted — confirmed selection in the NFL Draft.
        (
            r"\bdrafted\s+(?:by|to)\s+the\s+\w{3,20}\b",
            0.4,
            "general",
            {"is_drafted": True},
        ),
        # is_rumored_destination — speculation that names a specific team
        # (different from generic is_trade_buzz which does not name one).
        (
            r"\b(?:rumored\s+to\s+land|rumored\s+destination"
            r"|could\s+land\s+in)\b",
            0.0,
            "trade",
            {"is_rumored_destination": True},
        ),
        # is_coaching_change — head-coach / coordinator hire-or-fire.
        (
            r"\b(?:hired\s+as|fired"
            r"|new\s+(?:head\s+coach|coordinator)"
            r"|coaching\s+change)\b",
            -0.1,
            "general",
            {"is_coaching_change": True},
        ),
        # is_trade_buzz — soft trade speculation (no team named).
        (
            r"\b(?:trade\s+rumor"
            r"|rumored\s+to\s+be\s+(?:traded|dealt|moved)"
            r"|trade\s+speculation)\b",
            -0.1,
            "trade",
            {"is_trade_buzz": True},
        ),
        # is_holdout — player skipping minicamp/OTAs/training camp.
        (
            r"\bhold(?:ing\s+)?out\b",
            -0.3,
            "trade",
            {"is_holdout": True},
        ),
        # is_cap_cut — release driven by salary-cap considerations.
        (
            r"\b(?:cap\s+(?:cut|casualty)"
            r"|salary[\s-]?cap\s+(?:cut|release))\b",
            -0.4,
            "trade",
            {"is_cap_cut": True},
        ),
        # is_rookie_buzz — pre-draft prospect hype / draft-board surge.
        (
            r"\b(?:rookie\s+buzz"
            r"|first[\s-]round\s+(?:hype|prospect)"
            r"|sleeper\s+rookie)\b",
            0.4,
            "motivation",
            {"is_rookie_buzz": True},
        ),
    ]
    for pat, sent, cat, evts in _draft_season:
        entries.append((re.compile(pat, re.IGNORECASE), sent, cat, evts))

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

# Lower confidence ceiling for the 7 draft-season patterns added in
# Plan 72-01. The Claude path is the primary producer for these events
# (it has full-context disambiguation that bare keywords cannot match);
# rule-only matches are flagged as low-confidence so downstream
# aggregators can de-prioritise them. Capped at 0.5 per CONTEXT D-01.
_DRAFT_SEASON_CONFIDENCE = 0.5

# Set of draft-season event flag keys (Plan 72-01). Used by
# ``RuleExtractor.extract`` to decide whether a given best-match's
# events dict should be capped at ``_DRAFT_SEASON_CONFIDENCE``.
_DRAFT_SEASON_FLAGS = frozenset(
    {
        "is_drafted",
        "is_rumored_destination",
        "is_coaching_change",
        "is_trade_buzz",
        "is_holdout",
        "is_cap_cut",
        "is_rookie_buzz",
    }
)


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

            # Confidence cap (Plan 72-01): when the best-match's events
            # dict ONLY fires draft-season flags (and no legacy 12-flag
            # event), apply the lower ceiling so aggregators can
            # de-prioritise rule-only draft-season signals. If a legacy
            # flag is also set, the higher 0.7 ceiling stands so we do
            # not regress existing pattern confidence.
            event_keys = {k for k, v in events.items() if v}
            only_draft_season = (
                bool(event_keys) and event_keys.issubset(_DRAFT_SEASON_FLAGS)
            )
            confidence = (
                _DRAFT_SEASON_CONFIDENCE if only_draft_season else _RULE_CONFIDENCE
            )

            signal = PlayerSignal(
                player_name=name,
                sentiment=sentiment,
                confidence=confidence,
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
                # Draft-season events (Plan 72-01)
                is_drafted=events.get("is_drafted", False),
                is_rumored_destination=events.get(
                    "is_rumored_destination", False
                ),
                is_coaching_change=events.get("is_coaching_change", False),
                is_trade_buzz=events.get("is_trade_buzz", False),
                is_holdout=events.get("is_holdout", False),
                is_cap_cut=events.get("is_cap_cut", False),
                is_rookie_buzz=events.get("is_rookie_buzz", False),
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
