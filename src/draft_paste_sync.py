"""Paste-sync: parse a pasted draft-room pick log into an ordered pick list.

ESPN has no live draft API (Phase 89 spike verdict: NO-GO — the live draft runs
on an undocumented realtime backend the REST surface doesn't reflect until the
draft completes). But every draft room shows a pick-history panel whose text
can be selected and copied. Paste-sync turns that into near-live sync without
scraping: instead of clicking "Taken" once per pick (mirror mode), the user
pastes the history text and the whole board catches up in one shot.

Format-agnostic by design — one pick per line, matched by fuzzy full-name
lookup against the known player pool, so it survives any ESPN/Yahoo UI change
and also accepts a hand-typed list. Lines that don't contain a known player
name are reported back, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from src.sleeper_player_map import normalize_name

# Longest normalized player names run ~4 tokens ("amonra st brown" is 3);
# windows longer than this only waste cycles.
_MAX_NAME_TOKENS = 5


@dataclass(frozen=True)
class ParsedPick:
    """A single pick recovered from the pasted log, in paste order."""

    line_no: int
    raw_line: str
    player_id: str
    player_name: str


@dataclass(frozen=True)
class PasteSyncResult:
    """Everything the caller needs to apply and report a paste-sync."""

    picks: List[ParsedPick] = field(default_factory=list)
    unmatched_lines: List[str] = field(default_factory=list)


def build_name_lookup(
    names_to_ids: Iterable[Tuple[str, str]],
) -> Dict[str, Tuple[str, str]]:
    """Map normalized full name -> (player_id, canonical display name).

    Args:
        names_to_ids: ``(player_name, player_id)`` pairs, typically from the
            draft board's full player pool (available + already drafted, so a
            re-pasted full history resolves every line).

    Returns:
        Lookup keyed by :func:`normalize_name` output. On duplicate normalized
        names the first pair wins (board order = our rank order, so the more
        relevant player is kept).
    """
    lookup: Dict[str, Tuple[str, str]] = {}
    for name, player_id in names_to_ids:
        key = normalize_name(str(name))
        if key and key not in lookup:
            lookup[key] = (str(player_id), str(name))
    return lookup


def parse_pick_log(
    text: str, name_lookup: Dict[str, Tuple[str, str]]
) -> PasteSyncResult:
    """Recover the ordered pick list from pasted draft-room text.

    Each non-empty line contributes at most one pick: the line is normalized
    the same way player names are, then scanned left-to-right with
    longest-window-first token matching so "1.04 Amon-Ra St. Brown WR DET"
    resolves to the player, not a substring. Duplicate players (full-history
    re-pastes) are kept here — the applying layer decides whether a player is
    already off the board.

    Args:
        text: Raw pasted pick-history text, one pick per line.
        name_lookup: Output of :func:`build_name_lookup`.

    Returns:
        Picks in paste order plus the lines no known player matched.
    """
    picks: List[ParsedPick] = []
    unmatched: List[str] = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        tokens = normalize_name(line).split()
        match = _best_window_match(tokens, name_lookup)
        if match is None:
            unmatched.append(line)
            continue
        player_id, canonical = match
        picks.append(
            ParsedPick(
                line_no=line_no,
                raw_line=line,
                player_id=player_id,
                player_name=canonical,
            )
        )

    return PasteSyncResult(picks=picks, unmatched_lines=unmatched)


def _best_window_match(
    tokens: List[str], name_lookup: Dict[str, Tuple[str, str]]
) -> Optional[Tuple[str, str]]:
    """First longest token-window that is a known normalized player name.

    Longest-first ordering makes "Michael Pittman" win over a hypothetical
    "Michael Pitt"; left-to-right keeps the *picked* player when a line also
    names the drafting team or a comparison player later in the text.
    """
    n = len(tokens)
    for size in range(min(_MAX_NAME_TOKENS, n), 0, -1):
        for start in range(0, n - size + 1):
            end = start + size
            key = " ".join(tokens[start:end])
            hit = name_lookup.get(key)
            if hit is not None:
                return hit
    return None
