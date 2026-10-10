"""Waiver claims for George's leagues: claims file, live checks, payloads, read-back.

Pure functions only (no network), so every rule is testable from recorded
fixtures. :mod:`src.waiver_sites` does the browser I/O and
``scripts/submit_claims.py`` / ``scripts/check_pending_claims.py`` wire the two.

Platform facts (verified against the live leagues 2026-10-09 unless noted):

* **ESPN** — a claim is a ``WAIVER`` transaction with ``executionType EXECUTE``
  and status ``PENDING``. That record stays PENDING forever: the waiver run adds
  a separate ``PROCESS`` record (``EXECUTED`` / ``FAILED_*``) and a cancel adds a
  ``CANCEL`` record, each pointing back through ``relatedTransactionId``.
  ``mTransactions2`` lists a claim under every scoring period it spans, so
  records are de-duplicated by id. Only our own claims are visible.
  ``FAILED_INVALIDPLAYERSOURCE`` = the add went to another team, or an earlier
  claim already used the drop.
* **Yahoo** — the Fantasy API needs an approved app; ours gets ``401
  additional_authorization_required`` and new apps cannot get write scope, so a
  claim goes through the site's own add/drop form. Player search's "Roster
  Status" column reads ``W (Oct 11)`` (waivers), ``FA``, or the owning team.
* **Sleeper** — read-only here. The public API shows only processed claims
  (pending ones are private) and Sleeper's Terms (updated 2026-10-06, §11.1) ban
  scripted access to the private GraphQL API that the app uses to file claims.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

import yaml

try:
    from src.espn_league import PRO_TEAM_MAP
    from src.sleeper_player_map import normalize_name
except ImportError:  # pragma: no cover - direct-script import path
    from espn_league import PRO_TEAM_MAP
    from sleeper_player_map import normalize_name

#: Player availability as each site reports it.
WAIVERS = "waivers"
FREE_AGENT = "free agent"
#: Unrostered but the site does not say which (Sleeper's public API).
AVAILABLE = "available"
MINE = "mine"
ROSTERED = "rostered"
NOT_FOUND = "not found"
ADDABLE = (WAIVERS, FREE_AGENT, AVAILABLE)

#: Sleeper fantasy positions a claim can target (Mantis has no K/DEF).
_SLEEPER_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}
_DEF_TOKENS = {"dst", "def", "defense"}


class ClaimsFileError(ValueError):
    """The claims file is malformed (bad YAML, missing keys, wrong types)."""


@dataclass(frozen=True)
class Claim:
    """One claim as written in ``data/draft/claims_week<N>.yaml``."""

    league: str
    add: str
    drop: Optional[str]
    bid: int
    priority: int
    add_id: Optional[str] = None
    drop_id: Optional[str] = None


@dataclass(frozen=True)
class Player:
    """A player resolved on a site: id + where he is right now."""

    name: str
    pid: str
    status: str
    owner: str = ""

    @property
    def where(self) -> str:
        """``waivers`` / ``rostered: Team``."""
        return f"{self.status}: {self.owner}" if self.owner else self.status

    def label(self) -> str:
        """``Name (waivers)`` / ``Name (rostered: Team)`` for tables."""
        return f"{self.name} ({self.where})"


@dataclass(frozen=True)
class CheckedClaim:
    """A claim with its resolved players and everything wrong with it."""

    claim: Claim
    add: Player
    drop: Optional[Player]
    problems: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """True when nothing blocks submitting this claim."""
        return not self.problems

    @property
    def kind(self) -> str:
        """``WAIVER`` (a claim), ``FREE AGENT`` (adds immediately) or ``?``."""
        return {
            WAIVERS: "WAIVER",
            FREE_AGENT: "FREE AGENT",
            AVAILABLE: "WAIVER/FA",
        }.get(self.add.status, "?")


@dataclass(frozen=True)
class ClaimRecord:
    """A claim read back from a site: pending, or its processed outcome."""

    league: str
    add: str
    drop: str
    bid: Optional[int]
    status: str
    claim_id: str = ""
    filed: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# Claims file
# ---------------------------------------------------------------------------


def _int(value: Any, field: str, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ClaimsFileError(
            f"{where}: '{field}' must be a whole number, got {value!r}"
        )
    return value


def load_claims(path: Path, leagues: Iterable[str]) -> List[Claim]:
    """Read a claims YAML file.

    Format — a list (or a mapping with a ``claims`` list) of::

        - {league: la_liga, add: Commanders D/ST, drop: Bears D/ST, bid: 1, priority: 1}

    ``drop`` may be omitted (open roster spot). ``priority`` defaults to the
    order the league's claims appear in (1 = first). ``bid`` is required —
    a missing bid is a typo, not a $0 claim. ``add_id`` / ``drop_id`` pin the
    site's player id when two players share a name.

    Args:
        path: The YAML file.
        leagues: Valid league keys (``config.LEAGUE_PRESETS``).

    Returns:
        Claims in file order.

    Raises:
        ClaimsFileError: Unreadable YAML, unknown league, missing/invalid fields.
    """
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ClaimsFileError(f"cannot read {path}: {exc}") from exc
    rows = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        raise ClaimsFileError(f"{path}: expected a non-empty list of claims")
    valid = set(leagues)
    seen: Dict[str, int] = {}
    claims: List[Claim] = []
    for i, row in enumerate(rows, 1):
        where = f"{path} claim #{i}"
        if not isinstance(row, dict):
            raise ClaimsFileError(f"{where}: expected a mapping, got {row!r}")
        unknown = set(row) - {
            "league",
            "add",
            "drop",
            "bid",
            "priority",
            "add_id",
            "drop_id",
        }
        if unknown:
            raise ClaimsFileError(f"{where}: unknown keys {sorted(unknown)}")
        league = str(row.get("league") or "").strip()
        if league not in valid:
            raise ClaimsFileError(
                f"{where}: unknown league {league!r} ({sorted(valid)})"
            )
        add = str(row.get("add") or "").strip()
        if not add:
            raise ClaimsFileError(f"{where}: 'add' is required")
        if "bid" not in row:
            raise ClaimsFileError(f"{where}: 'bid' is required (use 0 for a $0 claim)")
        drop = str(row.get("drop") or "").strip() or None
        seen[league] = seen.get(league, 0) + 1
        priority = row.get("priority", seen[league])
        claims.append(
            Claim(
                league=league,
                add=add,
                drop=drop,
                bid=_int(row["bid"], "bid", where),
                priority=_int(priority, "priority", where),
                add_id=_opt_id(row.get("add_id")),
                drop_id=_opt_id(row.get("drop_id")),
            )
        )
    return claims


def _opt_id(value: Any) -> Optional[str]:
    return None if value is None or str(value).strip() == "" else str(value).strip()


def load_keepers(path: Optional[Path]) -> Set[str]:
    """Our keepers (``*`` lines) from a keepers file, as player keys."""
    if not path or not Path(path).is_file():
        return set()
    out: Set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("*"):
            out.add(player_key(line[1:]))
    return out


# ---------------------------------------------------------------------------
# Name resolution + checks
# ---------------------------------------------------------------------------


def player_key(name: str) -> str:
    """Normalized match key; team defenses match on the nickname alone.

    ``"Jaguars D/ST"`` (ESPN), ``"Jaguars"`` (Yahoo) and ``"Jaguars DEF"`` all
    key to ``"jaguars"``.
    """
    tokens = normalize_name(name).split()
    while len(tokens) > 1 and tokens[-1] in _DEF_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def index_players(players: Iterable[Player]) -> Dict[str, List[Player]]:
    """``{player_key: [Player, ...]}`` (several entries = same-name players)."""
    index: Dict[str, List[Player]] = {}
    for p in players:
        index.setdefault(player_key(p.name), []).append(p)
    return index


def search_name(name: str) -> str:
    """The name as a site search box wants it (``Jaguars D/ST`` -> ``Jaguars``)."""
    words = str(name).split()
    while len(words) > 1 and normalize_name(words[-1]) in _DEF_TOKENS:
        words.pop()
    return " ".join(words)


def resolve(
    name: str, index: Mapping[str, Sequence[Player]], pid: Optional[str] = None
) -> Tuple[Player, Optional[str]]:
    """Find ``name`` (optionally pinned to the site id ``pid``) in a site's index.

    Same-name players are never guessed between — a claim filed for the wrong
    twin cannot be taken back — so they need ``pid`` (``add_id`` / ``drop_id``).

    Returns:
        ``(player, problem)`` — ``problem`` is None when the match is unique.
    """
    hits = list({p.pid: p for p in index.get(player_key(name), [])}.values())
    if pid is not None:
        pinned = [p for p in hits if p.pid == str(pid)]
        if not pinned:
            return Player(name, str(pid), NOT_FOUND), f"no '{name}' with id {pid}"
        hits = pinned
    if not hits:
        return Player(name, "", NOT_FOUND), None
    if len(hits) > 1:
        options = ", ".join(f"{p.label()} id {p.pid}" for p in hits)
        return hits[0], f"'{name}' matches several players ({options}): pin the id"
    if not hits[0].pid:
        return hits[0], f"'{name}' has no site id"
    return hits[0], None


def check_league(
    claims: Sequence[Claim],
    index: Mapping[str, Sequence[Player]],
    faab_left: Optional[int],
    keepers: Iterable[str] = (),
    min_bid: int = 0,
    pending: Sequence["ClaimRecord"] = (),
    allow_free_agent: bool = False,
) -> List[CheckedClaim]:
    """Validate one league's claims against its live state (Step 4b rule).

    Blocking problems: the add is not on waivers / a free agent, a same-name
    player without a pinned id, the drop is not on our roster or is a keeper,
    the bid is out of range, the same add twice, two claims sharing a priority,
    a claim for the add is already pending (a re-run must not file it twice),
    a free-agent add (adds immediately, no cancel) unless ``allow_free_agent``.
    Warnings: claims sharing a drop (only one can execute, and ESPN's order
    among our claims is not guaranteed); bids that together exceed the budget
    (pending bids are not reserved); an unknown budget.

    Args:
        claims: One league's claims.
        index: :func:`index_players` of the site's free agents + all rosters.
        faab_left: Remaining budget, None when unknown (budget not checked).
        keepers: :func:`player_key` names that are never drop candidates.
        min_bid: The league's minimum bid.
        pending: Claims the site already shows (see :func:`is_pending_for`).
        allow_free_agent: File free-agent adds (they execute immediately).

    Returns:
        Claims in priority order with their problems/warnings.
    """
    keep = set(keepers)
    out: List[CheckedClaim] = []
    adds: Dict[str, int] = {}
    prios: Set[int] = set()
    for c in sorted(claims, key=lambda c: c.priority):
        problems: List[str] = []
        warnings: List[str] = []
        add, why = resolve(c.add, index, c.add_id)
        if why:
            problems.append(why)
        elif add.status == NOT_FOUND:
            problems.append(f"add '{c.add}' not found on the site")
        elif add.status not in ADDABLE:
            problems.append(f"add '{add.name}' is not available ({add.where})")
        elif add.status == FREE_AGENT:
            note = f"{add.name} is a free agent: adds IMMEDIATELY, cannot be cancelled"
            note += f"; the ${c.bid} bid is ignored" if c.bid else ""
            if allow_free_agent:
                warnings.append(note)
            else:
                problems.append(note + " (pass --allow-free-agent to file it)")
        if any(is_pending_for(r, add.name) for r in pending):
            problems.append(
                f"a claim for {add.name} is already pending on the site "
                "(cancel it there or drop it from the file)"
            )
        drop = None
        if c.drop:
            drop, why = resolve(c.drop, index, c.drop_id)
            if why:
                problems.append(why)
            elif drop.status != MINE:
                problems.append(f"drop '{c.drop}' is not on our roster ({drop.where})")
            if player_key(drop.name) in keep or player_key(c.drop) in keep:
                problems.append(f"drop '{c.drop}' is a KEEPER - never drop")
            if add.pid and add.pid == drop.pid:
                problems.append("add and drop are the same player")
        if c.bid < min_bid:
            problems.append(f"bid ${c.bid} is below the league minimum ${min_bid}")
        if faab_left is not None and c.bid > faab_left:
            problems.append(f"bid ${c.bid} exceeds the FAAB left (${faab_left})")
        key = player_key(add.name)
        if key in adds:
            problems.append(
                f"'{add.name}' is claimed twice "
                f"(priorities {adds[key]} and {c.priority})"
            )
        adds.setdefault(key, c.priority)
        if c.priority in prios:
            problems.append(f"priority {c.priority} is used twice")
        prios.add(c.priority)
        out.append(CheckedClaim(c, add, drop, tuple(problems), tuple(warnings)))
    by_drop: Dict[str, List[int]] = {}
    for c in out:
        if c.drop and c.drop.pid:
            by_drop.setdefault(c.drop.pid, []).append(c.claim.priority)
    total = sum(c.claim.bid for c in out)
    for i, c in enumerate(out):
        extra: List[str] = []
        shared = by_drop.get(c.drop.pid, []) if c.drop and c.drop.pid else []
        if len(shared) > 1 and c.claim.priority == shared[0]:
            extra.append(
                f"claims {shared} share the drop {c.drop.name}: only one can "
                "execute, and the site may not process them in priority order"
            )
        if i == len(out) - 1 and faab_left is not None and total > faab_left:
            extra.append(
                f"bids total ${total} > FAAB left ${faab_left}: "
                "later claims fail if earlier ones win"
            )
        if i == 0 and faab_left is None:
            extra.append("FAAB left unknown: bids not checked against the budget")
        if extra:
            out[i] = dataclasses.replace(c, warnings=c.warnings + tuple(extra))
    return out


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------

_ESPN_STATUS = {"WAIVERS": WAIVERS, "FREEAGENT": FREE_AGENT}


def espn_name(pid: Any, names: Mapping[str, str]) -> str:
    """Player name for an ESPN id.

    Team defenses (id ``-16000 - proTeamId``) fall back to ``JAX D/ST``.
    """
    name = names.get(str(pid))
    if name:
        return name
    try:
        n = int(pid)
    except (TypeError, ValueError):
        return f"espn:{pid}"
    if n < 0:
        return f"{PRO_TEAM_MAP.get(-16000 - n, str(n))} D/ST"
    return f"espn:{pid}"


def espn_players(
    pool: Sequence[Sequence[Any]],
    rosters: Sequence[Sequence[Any]],
    my_team_id: int,
) -> List[Player]:
    """ESPN free-agent pool + every roster -> Players.

    Args:
        pool: ``[id, name, status]`` rows from ``kona_player_info`` filtered to
            ``FREEAGENT``/``WAIVERS``.
        rosters: ``[team_id, team_name, id, name]`` rows from ``mRoster``.
        my_team_id: Our ESPN teamId.
    """
    out = [
        Player(str(name), str(pid), _ESPN_STATUS.get(str(status), str(status).lower()))
        for pid, name, status in pool
    ]
    for team_id, team_name, pid, name in rosters:
        mine = int(team_id) == int(my_team_id)
        out.append(
            Player(
                str(name),
                str(pid),
                MINE if mine else ROSTERED,
                "" if mine else str(team_name),
            )
        )
    return out


def espn_claim_body(
    team_id: int,
    scoring_period: int,
    add_id: str,
    drop_id: Optional[str],
    bid: int,
    free_agent: bool = False,
) -> Dict[str, Any]:
    """The ``lm-api-writes .../transactions/`` body for one claim.

    Matches the claims ESPN itself records for this league (fields
    ``isLeagueManager``, ``teamId``, ``type``, ``scoringPeriodId``,
    ``executionType``, ``bidAmount``, ``items``). ``memberId`` (our SWID) is
    added inside the browser so it never passes through Python.

    Args:
        team_id: Our teamId — never another team's.
        scoring_period: The league's CURRENT ``scoringPeriodId``.
        add_id / drop_id: ESPN player ids (D/ST ids are negative).
        bid: FAAB bid (ignored by ESPN for a free-agent add).
        free_agent: True when the add already cleared waivers (adds immediately).
    """
    items = [
        {
            "playerId": int(add_id),
            "type": "ADD",
            "fromTeamId": 0,
            "toTeamId": int(team_id),
            "fromLineupSlotId": -1,
            "toLineupSlotId": -1,
        }
    ]
    if drop_id:
        items.append(
            {
                "playerId": int(drop_id),
                "type": "DROP",
                "fromTeamId": int(team_id),
                "toTeamId": 0,
                "fromLineupSlotId": -1,
                "toLineupSlotId": -1,
            }
        )
    return {
        "isLeagueManager": False,
        "isActingAsTeamOwner": False,
        "teamId": int(team_id),
        "type": "FREEAGENT" if free_agent else "WAIVER",
        "scoringPeriodId": int(scoring_period),
        "executionType": "EXECUTE",
        "bidAmount": 0 if free_agent else int(bid),
        "items": items,
    }


def espn_claim_records(
    transactions: Sequence[Mapping[str, Any]],
    my_team_id: int,
    names: Mapping[str, str],
    league: str = "la_liga",
) -> List[ClaimRecord]:
    """Our ESPN waiver claims with their current status, oldest first.

    Status is ``PENDING`` until a ``PROCESS``/``CANCEL`` record points back at
    the claim; then it is that record's status (``EXECUTED``,
    ``FAILED_INVALIDPLAYERSOURCE``, ``CANCELED`` ...).

    Args:
        transactions: ``mTransactions2`` rows (any number of scoring periods).
        my_team_id: Our teamId.
        names: ``{player id: name}``.
        league: League key for the records.
    """
    by_id: Dict[str, Mapping[str, Any]] = {}
    for t in transactions:
        by_id.setdefault(str(t.get("id")), t)
    outcome: Dict[str, str] = {}
    for t in by_id.values():
        rel = t.get("relatedTransactionId")
        if rel and t.get("executionType") in ("PROCESS", "CANCEL"):
            outcome[str(rel)] = str(t.get("status"))
    claims = [
        t
        for t in by_id.values()
        if t.get("type") == "WAIVER"
        and t.get("executionType") == "EXECUTE"
        and t.get("teamId") == my_team_id
    ]

    def pick(items: Sequence[Mapping[str, Any]], kind: str) -> str:
        return "; ".join(
            espn_name(i.get("playerId"), names) for i in items if i.get("type") == kind
        )

    out = []
    for t in sorted(claims, key=lambda t: t.get("proposedDate") or 0):
        items = t.get("items") or []
        out.append(
            ClaimRecord(
                league=league,
                add=pick(items, "ADD"),
                drop=pick(items, "DROP"),
                bid=t.get("bidAmount"),
                status=outcome.get(str(t.get("id")), str(t.get("status"))),
                claim_id=str(t.get("id")),
                filed=_epoch_ms(t.get("proposedDate")),
            )
        )
    return out


def _epoch_ms(value: Any) -> str:
    import datetime as dt

    try:
        return dt.datetime.fromtimestamp(int(value) / 1000).strftime("%a %m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return ""


# ---------------------------------------------------------------------------
# Yahoo
# ---------------------------------------------------------------------------


def yahoo_players(search: Mapping[str, Sequence[Mapping[str, Any]]]) -> List[Player]:
    """Yahoo player-search rows -> Players.

    Args:
        search: ``{query: [{name, pid, roster_status, ours}]}`` — ``ours`` is
            True when the row offers "Drop" (only our own players do).
    """
    out = []
    for rows in search.values():
        for r in rows:
            rs = str(r.get("roster_status") or "").strip()
            if r.get("ours"):
                status, owner = MINE, ""
            elif rs == "FA":
                status, owner = FREE_AGENT, ""
            elif re.match(r"^W\b", rs):
                status, owner = WAIVERS, ""
            else:
                status, owner = ROSTERED, rs
            out.append(Player(str(r.get("name")), str(r.get("pid")), status, owner))
    return out


def yahoo_form_problems(
    form: Mapping[str, Any], add: Player, drop: Optional[Player], team_path: str
) -> List[str]:
    """Check the add/drop form Yahoo serves for a claim before posting it.

    Yahoo serves this form even for a player on another roster, so it never
    proves availability (that is the search's Roster Status). What it does
    show: a waiver player gets a FAAB box and a "Create claim ..." button, a
    free agent gets neither and is added immediately.

    Args:
        form: ``{found, drops: [[id, name]], faab, submits: [[name, label]], error}``
            from the ``/addplayer`` page.
        add: The resolved add.
        drop: The resolved drop (None = add only).
        team_path: Our team, e.g. ``/f1/658684/10`` — the form must post there.
    """
    if not form.get("found"):
        return [
            f"Yahoo add form unavailable: {form.get('error') or 'no add/drop form'}"
        ]
    problems = []
    if form.get("action") != f"{team_path}/addplayer":
        problems.append(f"Yahoo's form posts to {form.get('action')}, not {team_path}")
    drop_names = {str(i): str(n) for i, n in form.get("drops") or []}
    if drop and drop.pid not in drop_names:
        problems.append(f"drop '{drop.name}' is not a drop option on Yahoo's form")
    elif drop and player_key(drop_names[drop.pid]) != player_key(drop.name):
        problems.append(
            f"Yahoo's drop option {drop.pid} is '{drop_names[drop.pid]}', "
            f"not '{drop.name}'"
        )
    submits = [(str(n), str(label)) for n, label in form.get("submits") or []]
    usable = [label for n, label in submits if ("drop" in n) == bool(drop)]
    if not usable:
        problems.append(
            "Yahoo's form has no add+drop button"
            if drop
            else "roster is full on Yahoo: a drop is required"
        )
    elif add.status == WAIVERS and not (
        form.get("faab") and "claim" in usable[0].lower()
    ):
        problems.append(
            f"Yahoo would not file a waiver claim for {add.name} "
            f"(button: '{usable[0]}')"
        )
    return problems


def yahoo_claim_records(
    items: Sequence[Mapping[str, Any]], league: str = "feetball"
) -> List[ClaimRecord]:
    """Pending entries from the team page's Transactions box.

    Waiver-claim markup has not been captured yet (no claim was pending when
    this was built), so the text is kept whole in ``note`` and add/drop/bid are
    parsed best-effort. Pending trades come back with status ``TRADE``.
    """
    out = []
    for it in items:
        text = re.sub(r"\s+", " ", str(it.get("text") or "")).strip()
        if not text:
            continue
        if "trade" in str(it.get("path") or "").lower() or "trade" in text.lower():
            out.append(ClaimRecord(league, "", "", None, "TRADE", note=text))
            continue
        add = re.search(
            r"\bAdd(?:ed|ing)?:?\s+(.+?)(?=\s+(?:Drop|and drop|for|\$)|,|$)", text, re.I
        )
        drop = re.search(
            r"\bDrop(?:ped|ping)?:?\s+(.+?)(?=\s+(?:Add|for|\$|Edit|Cancel)|,|$)",
            text,
            re.I,
        )
        bid = re.search(r"\$(\d+)", text)
        out.append(
            ClaimRecord(
                league,
                add.group(1).strip() if add else "",
                drop.group(1).strip() if drop else "",
                int(bid.group(1)) if bid else None,
                "PENDING",
                note=text,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Sleeper (read-only)
# ---------------------------------------------------------------------------


def sleeper_players(
    registry: Mapping[str, Mapping[str, Any]],
    rosters: Sequence[Mapping[str, Any]],
    owners: Mapping[Any, str],
    my_roster_id: int,
) -> List[Player]:
    """Sleeper registry + league rosters -> Players.

    Unrostered players are ``AVAILABLE``: the public API does not say whether
    one is on waivers or a free agent. Inactive registry entries without a
    team are skipped so retired namesakes do not make a name ambiguous.

    Args:
        registry: ``/v1/players/nfl`` (``load_sleeper_players``).
        rosters: ``/v1/league/<id>/rosters``.
        owners: ``{roster_id: team name}``.
        my_roster_id: Our roster id.
    """
    where: Dict[str, Tuple[str, str]] = {}
    for r in rosters:
        rid = r.get("roster_id")
        for pid in r.get("players") or []:
            where[str(pid)] = (
                (MINE, "")
                if rid == my_roster_id
                else (ROSTERED, owners.get(rid, f"roster {rid}"))
            )
    out = []
    for pid, meta in registry.items():
        if pid not in where and not (meta.get("active") and meta.get("team")):
            continue
        if meta.get("position") not in _SLEEPER_POSITIONS:
            continue
        name = (
            meta.get("full_name")
            or f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        )
        status, owner = where.get(str(pid), (AVAILABLE, ""))
        out.append(Player(name, str(pid), status, owner))
    return out


def sleeper_claim_records(
    txns_by_leg: Mapping[int, Sequence[Mapping[str, Any]]],
    my_roster_id: int,
    registry: Mapping[str, Mapping[str, Any]],
    league: str = "mantis",
) -> List[ClaimRecord]:
    """Our processed Sleeper waiver claims (``complete`` / ``failed``) per leg."""

    def name(pid: Any) -> str:
        return (registry.get(str(pid)) or {}).get("full_name") or str(pid)

    out = []
    for leg, txns in sorted(txns_by_leg.items()):
        for t in txns or []:
            if t.get("type") != "waiver" or my_roster_id not in (
                t.get("roster_ids") or []
            ):
                continue
            settings = t.get("settings") or {}
            out.append(
                ClaimRecord(
                    league=league,
                    add="; ".join(name(p) for p in t.get("adds") or {}),
                    drop="; ".join(name(p) for p in t.get("drops") or {}),
                    bid=settings.get("waiver_bid"),
                    status=str(t.get("status", "")).upper(),
                    claim_id=str(t.get("transaction_id", "")),
                    filed=f"leg {leg}",
                    note=str((t.get("metadata") or {}).get("notes") or ""),
                )
            )
    return out


def is_pending_for(record: ClaimRecord, name: str) -> bool:
    """True when ``record`` is a pending claim to add ``name``.

    Yahoo records are parsed best-effort, so the raw text counts too.
    """
    if record.status != "PENDING":
        return False
    return player_key(record.add) == player_key(name) or normalize_name(
        name
    ) in normalize_name(record.note)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    cells = [[str(c) for c in header]] + [
        ["" if c is None else str(c) for c in r] for r in rows
    ]
    widths = [max(len(r[i]) for r in cells) for i in range(len(header))]

    def fmt(r: Sequence[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()

    return [fmt(cells[0]), fmt(["-" * w for w in widths])] + [fmt(r) for r in cells[1:]]


def render_checked(checked: Sequence[CheckedClaim]) -> str:
    """The claims table printed before anything is submitted."""
    rows = [
        (
            c.claim.league,
            c.claim.priority,
            c.kind,
            c.add.label(),
            c.drop.label() if c.drop else "-",
            f"${c.claim.bid}",
            "OK" if c.ok else "BLOCKED",
        )
        for c in checked
    ]
    lines = _table(("LEAGUE", "PRI", "TYPE", "ADD", "DROP", "BID", "CHECK"), rows)
    for c in checked:
        for p in c.problems:
            lines.append(f"  x {c.claim.league} #{c.claim.priority}: {p}")
        for w in c.warnings:
            lines.append(f"  ! {c.claim.league} #{c.claim.priority}: {w}")
    return "\n".join(lines)


def render_records(records: Sequence[ClaimRecord]) -> str:
    """Pending / processed claims read back from a site."""
    if not records:
        return "  (none)"
    rows = [
        (
            r.status,
            r.add or "?",
            r.drop or "-",
            "" if r.bid is None else f"${r.bid}",
            r.filed,
            r.note[:70],
        )
        for r in records
    ]
    return "\n".join(
        "  " + line
        for line in _table(("STATUS", "ADD", "DROP", "BID", "FILED", "NOTE"), rows)
    )
