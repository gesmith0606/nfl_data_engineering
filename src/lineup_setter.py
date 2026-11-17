"""Weekly lineup setter — roster → two projection sources → league scoring → deltas.

Built after the Week 1 2026 Mantis review recommended benching a WR1 on a single
stale source (see ``.planning/LINEUP_TOOL_ENHANCEMENT.md``). Rules encoded here:

* Two independent sources per player: OURS (weekly Gold, or preseason pace when the
  weekly board is thin) and SLEEPER (their weekly projection), both re-scored under
  the league's real ``scoring_settings``.
* A swap is recommended only when BOTH sources agree by at least ``threshold``
  points; agreement below the threshold is a coin flip; disagreement is reported,
  never recommended.
* Locked (kickoff passed), bye, and injury-flagged players are surfaced, not hidden.

Pure functions over dicts/DataFrames; the CLI in ``scripts/set_lineups.py`` does I/O.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from src.league_scoring import score_with_settings
from src.roster_optimizer import _SKIP_SLOTS, _SLOT_ELIGIBILITY, optimal_lineup
from src.sleeper_player_map import normalize_name

ET = ZoneInfo("America/New_York")
# Sleeper team codes that differ from the nflverse schedule codes.
_TEAM_ALIAS = {"LAR": "LA", "OAK": "LV"}
_SLOT_DISPLAY = {
    "SUPER_FLEX": "SFLEX",
    "SUPERFLEX": "SFLEX",
    "WRRB_FLEX": "W/R",
    "REC_FLEX": "W/T",
    "WRRB_WRT": "W/R/T",
}
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}
MIN_WEEKLY_ROWS = 150  # below this the weekly board is a thin/rookie-only artifact

# Weekly Gold stat columns -> the names score_with_settings understands.
_WEEKLY_RENAME = {
    "proj_passing_yards": "passing_yards",
    "proj_passing_tds": "passing_tds",
    "proj_interceptions": "interceptions",
    "proj_rushing_yards": "rushing_yards",
    "proj_rushing_tds": "rushing_tds",
    "proj_receptions": "receptions",
    "proj_receiving_yards": "receiving_yards",
    "proj_receiving_tds": "receiving_tds",
}
_STAT_COLS = list(_WEEKLY_RENAME.values())
_ID_COLS = ["player_id", "player_name", "position", "recent_team"]
GAMES_PER_SEASON = 17

# K and team-defense scoring for leagues whose scoring we only know as a
# ``config.SCORING_CONFIGS`` preset (ESPN, Yahoo): those presets carry offensive
# rules only, so without this every K/DEF would score 0 and tie. Standard
# Yahoo-style rules, Sleeper projection key names. Ordering a roster's kickers
# and defences needs the shape of the scoring, not its exact numbers.
KDEF_DEFAULT_SCORING: Dict[str, float] = {
    "fgm_0_19": 3.0, "fgm_20_29": 3.0, "fgm_30_39": 3.0, "fgm_40_49": 4.0,
    "fgm_50p": 5.0, "xpm": 1.0,
    "sack": 1.0, "int": 2.0, "fum_rec": 2.0, "def_td": 6.0, "def_st_td": 6.0,
    "safe": 2.0, "blk_kick": 2.0,
    "pts_allow_0": 10.0, "pts_allow_1_6": 7.0, "pts_allow_7_13": 4.0,
    "pts_allow_14_20": 1.0, "pts_allow_21_27": 0.0, "pts_allow_28_34": -1.0,
    "pts_allow_35p": -4.0,
}  # fmt: skip


@dataclass
class PlayerRow:
    """One rostered player with both projection sources and status flags."""

    sleeper_id: str
    name: str
    position: str
    team: str
    ours: Optional[float] = None
    sleeper: Optional[float] = None
    injury_status: Optional[str] = None
    depth_chart_order: Optional[int] = None
    kickoff: Optional[dt.datetime] = None
    locked: bool = False
    bye: bool = False
    slot: Optional[str] = None  # current starting slot, None if benched
    slot_index: int = 999  # position of that slot in roster_positions (render order)
    notes: List[str] = field(default_factory=list)
    # Sleeper Out/Doubtful not confirmed by the week's official report.
    status_unconfirmed: bool = False
    # OUT / DOUBTFUL / QUESTIONABLE (see LEVEL_*), None when healthy/unknown.
    status_level: Optional[str] = None
    # The schedule says no game but Sleeper projects him: not treated as bye.
    schedule_mismatch: bool = False

    @property
    def blend(self) -> float:
        vals = [v for v in (self.ours, self.sleeper) if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    @property
    def ours_eff(self) -> Optional[float]:
        """OUR projection, or the consensus when our board has no row for him.

        A missing row used to block every SWAP involving the player (2026: 231 of
        1,818 rostered player-weeks had none) and score 0 in the optimizer.
        """
        return self.ours if self.ours is not None else self.sleeper

    @property
    def sleeper_eff(self) -> Optional[float]:
        return self.sleeper if self.sleeper is not None else self.ours

    @property
    def dead_reason(self) -> Optional[str]:
        """Why he cannot score this week (bye, no team, Out/IR, Doubtful), else None.

        An unconfirmed Sleeper Out/Doubtful tag is NOT dead: that tag is the last
        game's ruling (see ``resolve_injury_status``); it surfaces as CHECK STATUS.
        """
        if self.bye:
            return "BYE"
        if self.team in ("", "FA"):
            return "no NFL team"
        if self.status_level == LEVEL_OUT:
            return "OUT"
        if self.status_level == LEVEL_DOUBTFUL:
            return "DOUBTFUL"
        return None

    @property
    def dead(self) -> bool:
        return self.dead_reason is not None

    def as_optimizer_dict(self, source: str) -> Dict[str, Any]:
        pts = getattr(self, source)
        return {
            "sleeper_id": self.sleeper_id,
            "player_name": self.name,
            "position": self.position,
            "projected_points": 0.0 if (pts is None or self.bye) else pts,
        }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_sleeper_stats(
    stats: Dict[str, Any], scoring_settings: Dict[str, Any], position: str
) -> float:
    """Score a Sleeper projection stat dict under a league's scoring settings.

    Sleeper's projection keys are the same vocabulary as ``scoring_settings``
    (``pass_yd``, ``rec``, ``rec_fd``, ``fum_lost`` ...), so this is a dot product.
    ``bonus_rec_te`` is a per-reception TE premium and only applies to TEs.
    """
    total = 0.0
    for key, weight in scoring_settings.items():
        if key == "bonus_rec_te":
            continue
        val = stats.get(key)
        if val and weight:
            total += float(val) * float(weight)
    te_bonus = scoring_settings.get("bonus_rec_te")
    if te_bonus and position == "TE":
        total += float(stats.get("rec") or 0) * float(te_bonus)
    return round(total, 2)


def weekly_gold_to_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise a weekly Gold parquet (``proj_*`` columns) to plain stat columns."""
    out = df.rename(columns=_WEEKLY_RENAME)
    keep = [c for c in _ID_COLS + _STAT_COLS if c in out.columns]
    return out[keep].copy()


def preseason_to_weekly(
    df: pd.DataFrame, games: int = GAMES_PER_SEASON
) -> pd.DataFrame:
    """Turn a preseason (season-total) Gold parquet into per-game stat rows."""
    out = df[[c for c in _ID_COLS + _STAT_COLS if c in df.columns]].copy()
    for col in _STAT_COLS:
        if col in out.columns:
            out[col] = out[col].astype(float) / games
    return out


def score_ours(df: pd.DataFrame, scoring_settings: Dict[str, Any]) -> pd.DataFrame:
    """Score normalised stat rows under league settings -> ``projected_points``."""
    if df.empty:
        return df.assign(projected_points=pd.Series(dtype=float))
    scored = score_with_settings(df.assign(projected_points=0.0), scoring_settings)
    return scored


# ---------------------------------------------------------------------------
# Identity: GSIS / name -> Sleeper id
# ---------------------------------------------------------------------------


def build_id_maps(
    registry: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, str], Dict[Tuple[str, str], str]]:
    """Return ``(gsis_id -> sleeper_id, (normalised name, position) -> sleeper_id)``."""
    by_gsis: Dict[str, str] = {}
    by_name: Dict[Tuple[str, str], str] = {}
    for sid, meta in registry.items():
        if not isinstance(meta, dict):
            continue
        gsis = meta.get("gsis_id")
        if gsis:
            by_gsis[str(gsis)] = str(sid)
        name = meta.get("full_name") or " ".join(
            p for p in (meta.get("first_name"), meta.get("last_name")) if p
        )
        pos = str(meta.get("position") or "")
        if name and pos in SKILL_POSITIONS | {"K"} and meta.get("active", True):
            by_name.setdefault((normalize_name(name), pos), str(sid))
        elif pos == "DEF" and name:
            # Sleeper keys a defence by its team code ("HOU") and names it
            # "Houston Texans": index the city+nickname and the bare nickname.
            by_name.setdefault((normalize_name(name), "DEF"), str(sid))
            nick = str(meta.get("last_name") or "")
            if nick:
                by_name.setdefault((normalize_name(nick), "DEF"), str(sid))
    return by_gsis, by_name


def roster_gsis_map(rosters: pd.DataFrame) -> Dict[str, str]:
    """``gsis player_id -> sleeper_id`` from Bronze rosters (later seasons win).

    The Sleeper registry's own ``gsis_id`` is sparse, and weekly Gold names are
    abbreviated (``C.Brown``), so without this crosswalk most weekly rows would
    not join (2026 wk1: 3 of 18 Mantis players matched).
    """
    if rosters is None or rosters.empty:
        return {}
    cols = [c for c in ("player_id", "sleeper_id", "season") if c in rosters.columns]
    if not {"player_id", "sleeper_id"} <= set(cols):
        return {}
    df = rosters[cols].dropna(subset=["player_id", "sleeper_id"])
    if "season" in df.columns:
        df = df.sort_values("season")
    out: Dict[str, str] = {}
    for gsis, sid in zip(df["player_id"], df["sleeper_id"]):
        try:
            out[str(gsis)] = str(int(float(sid)))
        except (ValueError, TypeError):
            continue
    return out


def full_name_map(*frames: pd.DataFrame) -> Dict[str, str]:
    """``gsis player_id -> full name`` from Bronze frames (later frames win).

    Accepts Bronze weekly actuals (``player_display_name``) and/or rosters
    (``player_name``); frames missing both columns are skipped.
    """
    out: Dict[str, str] = {}
    for df in frames:
        if df is None or df.empty or "player_id" not in df.columns:
            continue
        col = next(
            (c for c in ("player_display_name", "player_name") if c in df.columns),
            None,
        )
        if col is None:
            continue
        sub = df[["player_id", col]].dropna()
        out.update(zip(sub["player_id"].astype(str), sub[col].astype(str)))
    return out


def ours_by_sleeper_id(
    scored: pd.DataFrame,
    registry: Dict[str, Dict[str, Any]],
    gsis_map: Optional[Dict[str, str]] = None,
    full_names: Optional[Dict[str, str]] = None,
) -> Dict[str, float]:
    """Map our scored projections onto Sleeper ids.

    Order: roster crosswalk ``gsis_map`` (Bronze rosters), then the registry's
    ``gsis_id``, then normalised name + position — using the player's full
    name from ``full_names`` (gsis -> full name, e.g. Bronze weekly actuals)
    when given, since weekly Gold names are abbreviated (``J.Price``). That
    last step is the only path for new rookies, who have neither a
    ``sleeper_id`` in Bronze rosters nor a ``gsis_id`` in the registry.
    """
    by_gsis, by_name = build_id_maps(registry)
    if gsis_map:
        by_gsis = {**by_gsis, **gsis_map}
    full_names = full_names or {}
    out: Dict[str, float] = {}
    for row in scored.itertuples(index=False):
        sid = by_gsis.get(str(row.player_id))
        if sid is None:
            name = full_names.get(str(row.player_id)) or str(row.player_name)
            sid = by_name.get((normalize_name(name), str(row.position)))
        if sid is not None and sid not in out:
            out[sid] = float(row.projected_points)
    return out


def sleeper_to_gsis(
    registry: Dict[str, Dict[str, Any]], gsis_map: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """``sleeper_id -> gsis_id``: the registry's own ``gsis_id``, else the
    inverted Bronze roster crosswalk (``roster_gsis_map``)."""
    out = {sid: str(g) for g, sid in (gsis_map or {}).items()}
    for sid, meta in registry.items():
        if isinstance(meta, dict) and meta.get("gsis_id"):
            out[str(sid)] = str(meta["gsis_id"])
    return out


# ---------------------------------------------------------------------------
# Injury status: official report for the upcoming week vs Sleeper's tag
# ---------------------------------------------------------------------------
#
# Sleeper's ``injury_status`` carries the LAST game's ruling until the next one
# is posted: DJ Moore showed "Out" all of 2026 week 3 prep after leaving the
# week 2 Thursday game, while the news said day-to-day. The official NFL report
# (nflverse injuries, one snapshot per daily ingest) is the week-N ruling.

_GAME_STATUS_ABBR = {"Out": "Out", "Doubtful": "D", "Questionable": "Q"}
_PRACTICE_ABBR = {
    "did not participate in practice": "DNP",
    "limited participation in practice": "LP",
    "full participation in practice": "FP",
}
# Sleeper tags that are per-game rulings (and go stale); IR/PUP/Sus are roster
# designations and stay authoritative.
_GAME_RULING_TAGS = {"Out", "Doubtful", "Questionable"}
# Tags that would bench a starter (Sleeper zeroes its projection for these).
BENCHING_TAGS = {"Out", "Doubtful"}
# Roster designations that mean "no game this week" (IR, PUP, suspended, ...).
_OUT_DESIGNATIONS = {"IR", "PUP", "Sus", "NFI", "COV", "DNR", "NA"}
# Normalised availability levels (PlayerRow.status_level).
LEVEL_OUT, LEVEL_DOUBTFUL, LEVEL_QUESTIONABLE = "OUT", "DOUBTFUL", "QUESTIONABLE"
_TAG_LEVEL = {
    "Out": LEVEL_OUT,
    "Doubtful": LEVEL_DOUBTFUL,
    "Questionable": LEVEL_QUESTIONABLE,
}


@dataclass(frozen=True)
class OfficialReport:
    """One player's line on the official injury report for a week."""

    game_status: Optional[str]  # Out / Doubtful / Questionable, None pre-Friday
    injury: Optional[str]
    practice: Tuple[str, ...]  # DNP/LP/FP trail across snapshots, repeats collapsed
    as_of: Optional[dt.datetime]  # snapshot the latest line came from


@dataclass
class InjuryContext:
    """Everything :func:`resolve_injury_status` needs besides the registry row.

    ``reports``: gsis -> official line for ``week``; ``teams_reported``: teams
    (nflverse codes) with any row on that week's report; ``played_prev``: gsis
    ids with a week ``week - 1`` stat line (None = unknown); ``gsis_by_sleeper``
    from :func:`sleeper_to_gsis`.
    """

    week: int
    reports: Dict[str, OfficialReport] = field(default_factory=dict)
    teams_reported: set = field(default_factory=set)
    played_prev: Optional[set] = None
    gsis_by_sleeper: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class InjuryStatus:
    text: str
    # A Sleeper Out/Doubtful tag the week's official report does not confirm:
    # never bench a starter on it (lineup_deltas -> CHECK STATUS).
    unconfirmed_bench_tag: bool = False
    # Normalised availability: OUT / DOUBTFUL / QUESTIONABLE, None when healthy
    # or when the only evidence is an unconfirmed (stale) Sleeper tag.
    level: Optional[str] = None


def _abbr_practice(val: Any) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return _PRACTICE_ABBR.get(str(val).strip().lower(), str(val))


def _clean(val: Any) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return None
    return str(val)


def official_reports(
    snapshots: pd.DataFrame, week: int
) -> Tuple[Dict[str, OfficialReport], set]:
    """Build the week's official report from nflverse injury snapshots.

    ``snapshots`` is every Bronze injuries file for the season concatenated,
    with a ``snapshot_at`` column (the file's ingest timestamp). The latest
    snapshot holding any row for ``week`` is the current report; earlier ones
    only contribute the practice trail (nflverse keeps one practice status per
    player-week, so the daily snapshots are what show DNP -> LP -> FP).

    Returns ``(gsis_id -> OfficialReport, teams on that week's report)``.
    """
    if snapshots is None or snapshots.empty or "week" not in snapshots.columns:
        return {}, set()
    wk = snapshots[snapshots["week"] == week].dropna(subset=["gsis_id"])
    if wk.empty:
        return {}, set()
    latest_at = wk["snapshot_at"].max()
    latest = wk[wk["snapshot_at"] == latest_at]
    history = wk.sort_values("snapshot_at")
    reports: Dict[str, OfficialReport] = {}
    for row in latest.itertuples(index=False):
        gsis = str(row.gsis_id)
        trail: List[str] = []
        for val in history.loc[history["gsis_id"] == row.gsis_id, "practice_status"]:
            abbr = _abbr_practice(val)
            if abbr and (not trail or trail[-1] != abbr):
                trail.append(abbr)
        reports[gsis] = OfficialReport(
            game_status=_clean(getattr(row, "report_status", None)),
            injury=_clean(getattr(row, "report_primary_injury", None))
            or _clean(getattr(row, "practice_primary_injury", None)),
            practice=tuple(trail),
            as_of=latest_at if isinstance(latest_at, dt.datetime) else None,
        )
    return reports, set(latest["team"].dropna().astype(str))


def _age(then: dt.datetime, now: dt.datetime) -> str:
    hours = (now - then).total_seconds() / 3600
    return f"{hours:.0f}h" if hours < 48 else f"{hours / 24:.0f}d"


def resolve_injury_status(
    sleeper_id: str,
    meta: Dict[str, Any],
    ctx: InjuryContext,
    now: Optional[dt.datetime] = None,
) -> Optional[InjuryStatus]:
    """One display string for a player's injury status, official report first.

    * On the week's official report -> ``wk3 Q (Shoulder), practice DNP>LP``;
      a Sleeper Out/Doubtful the report does not confirm is flagged.
    * Team's report is out but the player is not on it -> any Sleeper
      game-ruling tag is stale (``not on BUF wk3 report``).
    * No report yet -> the Sleeper tag, labelled with where it came from
      (``from wk2 game, not a wk3 ruling`` when he played last week) and the
      age of Sleeper's ``news_updated``.
    """
    now = now or dt.datetime.now(tz=ET)
    week = ctx.week
    tag = _clean(meta.get("injury_status"))
    body = _clean(meta.get("injury_body_part"))
    sl_practice = _clean(meta.get("practice_participation"))
    news_ms = meta.get("news_updated")
    news_age = None
    if news_ms:
        try:
            news_at = dt.datetime.fromtimestamp(float(news_ms) / 1000, tz=ET)
            news_age = f"news {_age(news_at, now)} old"
        except (ValueError, TypeError, OverflowError):
            news_age = None

    gsis = ctx.gsis_by_sleeper.get(str(sleeper_id))
    report = ctx.reports.get(gsis) if gsis else None
    team = str(meta.get("team") or "")
    team = _TEAM_ALIAS.get(team, team)

    if report is not None:
        parts = []
        if report.game_status:
            status = _GAME_STATUS_ABBR.get(report.game_status, report.game_status)
            parts.append(
                f"wk{week} {status}" + (f" ({report.injury})" if report.injury else "")
            )
        else:
            parts.append(
                f"wk{week} report"
                + (f" ({report.injury})" if report.injury else "")
                + ", no game status yet"
            )
        if report.practice:
            parts.append("practice " + ">".join(report.practice))
        if report.as_of is not None:
            parts.append(f"report {report.as_of:%m-%d}")
        confirmed = report.game_status in BENCHING_TAGS
        unconfirmed = tag in BENCHING_TAGS and not confirmed
        if unconfirmed:
            parts.append(f"Sleeper still says {tag}")
        return InjuryStatus(
            ", ".join(parts), unconfirmed, _TAG_LEVEL.get(report.game_status or "")
        )

    if tag is None:
        return None
    label = f"Sleeper: {tag}" + (f" ({body})" if body else "")
    if tag not in _GAME_RULING_TAGS:  # IR / PUP / Sus: roster designation
        return InjuryStatus(
            ", ".join(p for p in (label, news_age) if p),
            level=LEVEL_OUT if tag in _OUT_DESIGNATIONS else None,
        )
    if team in ctx.teams_reported:
        where = f"not on {team} wk{week} report"
        stale = True
    elif week > 1 and ctx.played_prev is not None and gsis:
        stale = gsis in ctx.played_prev
        where = (
            f"from wk{week - 1} game, not a wk{week} ruling"
            if stale
            else f"did not play wk{week - 1}"
        )
    else:
        where, stale = f"no wk{week} report yet", True
    parts = [label, where]
    if sl_practice:
        parts.append(f"Sleeper practice {sl_practice}")
    if news_age:
        parts.append(news_age)
    return InjuryStatus(
        ", ".join(parts),
        stale and tag in BENCHING_TAGS,
        None if stale and tag in BENCHING_TAGS else _TAG_LEVEL.get(tag),
    )


# ---------------------------------------------------------------------------
# Schedule: kickoff / lock / bye
# ---------------------------------------------------------------------------


def kickoffs_for_week(schedule: pd.DataFrame, week: int) -> Dict[str, dt.datetime]:
    """``team -> kickoff (ET, tz-aware)`` for every team playing in *week*."""
    wk = schedule[schedule["week"] == week]
    out: Dict[str, dt.datetime] = {}
    for row in wk.itertuples(index=False):
        try:
            day = dt.date.fromisoformat(str(row.gameday))
            hh, mm = str(row.gametime or "13:00").split(":")[:2]
            ko = dt.datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=ET)
        except (ValueError, TypeError):
            continue
        out[str(row.home_team)] = ko
        out[str(row.away_team)] = ko
    return out


# ---------------------------------------------------------------------------
# Assemble the roster table
# ---------------------------------------------------------------------------


def current_slots(
    roster_positions: Sequence[str], starters: Sequence[str]
) -> List[Tuple[str, str]]:
    """Zip Sleeper's ``starters`` list onto the non-bench ``roster_positions``.

    Sleeper stores starters in roster_positions order with BN/IR/TAXI excluded;
    an empty slot is the string ``"0"``.
    """
    slots = [p for p in roster_positions if str(p).upper() not in _SKIP_SLOTS]
    return list(zip(slots, list(starters) + ["0"] * (len(slots) - len(starters))))


def build_rows(
    player_ids: Iterable[str],
    starters: Sequence[str],
    roster_positions: Sequence[str],
    registry: Dict[str, Dict[str, Any]],
    ours: Dict[str, float],
    sleeper_proj: Dict[str, Dict[str, Any]],
    scoring_settings: Dict[str, Any],
    kickoffs: Dict[str, dt.datetime],
    now: Optional[dt.datetime] = None,
    injury_ctx: Optional[InjuryContext] = None,
    news: Optional[Dict[str, str]] = None,
) -> List[PlayerRow]:
    """Build one :class:`PlayerRow` per rostered player with both sources + flags.

    With ``injury_ctx`` the injury note is :func:`resolve_injury_status`
    (official report first); without it, Sleeper's raw tag. ``news`` maps
    sleeper_id -> Gold sentiment flags (e.g. ``ruled_out,questionable``).
    """
    now = now or dt.datetime.now(tz=ET)
    have_schedule = bool(kickoffs)  # no schedule -> no bye/lock claims at all
    slot_of = {
        pid: (slot, i)
        for i, (slot, pid) in enumerate(current_slots(roster_positions, starters))
        if pid != "0"
    }
    rows: List[PlayerRow] = []
    for pid in player_ids:
        pid = str(pid)
        meta = registry.get(pid) or {}
        pos = str(meta.get("position") or "?")
        team = str(meta.get("team") or "FA")
        name = (
            meta.get("full_name")
            or f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
            or pid
        )
        stats = sleeper_proj.get(pid)
        sl = score_sleeper_stats(stats, scoring_settings, pos) if stats else None
        ko = kickoffs.get(_TEAM_ALIAS.get(team, team))
        # The schedule is trusted only while Sleeper agrees. A schedule missing
        # one game would otherwise turn every starter on those two teams into a
        # MUST FIX (and, on ESPN, a filed move), so a player Sleeper projects
        # above zero is not on bye: the disagreement is flagged, not acted on.
        no_game = have_schedule and ko is None and team != "FA"
        mismatch = no_game and sl is not None and sl > 0
        slot, slot_index = slot_of.get(pid, (None, 999))
        row = PlayerRow(
            sleeper_id=pid,
            name=name,
            position=pos,
            team=team,
            ours=ours.get(pid),
            sleeper=sl,
            injury_status=meta.get("injury_status") or None,
            depth_chart_order=meta.get("depth_chart_order"),
            kickoff=ko,
            locked=bool(ko and now >= ko),
            bye=no_game and not mismatch,
            schedule_mismatch=mismatch,
            slot=slot,
            slot_index=slot_index,
        )
        if mismatch:
            row.notes.append(
                f"schedule has no {team} game but Sleeper projects {sl:.1f}: "
                "not treated as bye"
            )
        if row.bye:
            row.notes.append("BYE")
        if row.locked:
            row.notes.append("LOCKED")
        if injury_ctx is not None:
            status = resolve_injury_status(pid, meta, injury_ctx, now)
            if status is not None:
                row.notes.append(status.text)
                row.status_unconfirmed = status.unconfirmed_bench_tag
                row.status_level = status.level
        elif row.injury_status:
            # No official report to check against. A roster designation (IR,
            # PUP, Sus ...) is authoritative, but a bare Out/Doubtful/Questionable
            # is the LAST game's ruling (see resolve_injury_status): never a
            # reason to bench anyone on its own. It is flagged unconfirmed, which
            # makes it CHECK STATUS and keeps it out of MUST FIX and the writer.
            tag = str(row.injury_status)
            row.notes.append(tag)
            if tag in _OUT_DESIGNATIONS:
                row.status_level = LEVEL_OUT
            elif tag in BENCHING_TAGS:
                row.status_unconfirmed = True
                row.notes.append("tag unconfirmed: no official report loaded")
        if news and news.get(pid):
            row.notes.append(f"news: {news[pid]}")
        if row.ours is None:
            row.notes.append("no model proj")
        if row.sleeper is None:
            row.notes.append("no Sleeper proj")
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Deltas
# ---------------------------------------------------------------------------


@dataclass
class Delta:
    verdict: str  # SWAP | CHECK STATUS | COIN FLIP | SPLIT
    slot: str
    out_player: PlayerRow
    in_player: PlayerRow
    margin_ours: Optional[float]
    margin_sleeper: Optional[float]

    def line(self) -> str:
        m_o = "n/a" if self.margin_ours is None else f"{self.margin_ours:+.1f}"
        m_s = "n/a" if self.margin_sleeper is None else f"{self.margin_sleeper:+.1f}"
        line = (
            f"{self.verdict:9s} {self.slot:6s} start {self.in_player.name} "
            f"over {self.out_player.name}  (ours {m_o}, Sleeper {m_s})"
        )
        if self.verdict == "CHECK STATUS":
            line += (
                f" -- {self.out_player.name}'s Sleeper tag is not this week's "
                "official ruling; swap only if he is actually out"
            )
        return line


def _margin(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(a - b, 2)


def _verdict(
    m_o: Optional[float], m_s: Optional[float], threshold: float
) -> Optional[str]:
    """SWAP: both clear the threshold. COIN FLIP: both positive, one thin.
    SPLIT: one source clears the threshold while the other is missing or leans
    the other way. None: nothing worth saying."""
    if m_o is not None and m_s is not None:
        if m_o >= threshold and m_s >= threshold:
            return "SWAP"
        if m_o > 0 and m_s > 0:
            return "COIN FLIP"
        if max(m_o, m_s) >= threshold and min(m_o, m_s) <= 0:
            return "SPLIT"
        return None
    known = m_o if m_o is not None else m_s
    return "SPLIT" if known is not None and known >= threshold else None


_RANK = {"SWAP": 2, "CHECK STATUS": 2, "COIN FLIP": 1, "SPLIT": 0}


def lineup_deltas(
    rows: List[PlayerRow], threshold: float = 3.0, legacy: bool = False
) -> List[Delta]:
    """Pairwise deltas vs the lineup currently set.

    For each current starter, every eligible bench player is a candidate; see
    :func:`_verdict` for the SWAP / COIN FLIP / SPLIT rule. Candidates are taken
    strongest-first (verdict, then the worse of the two margins) and each player
    appears in at most one delta. Locked bench players are never proposed;
    a locked starter cannot be swapped out. A SWAP that would bench a starter
    whose Sleeper Out/Doubtful tag the week's official report does not confirm
    (``status_unconfirmed``) is downgraded to CHECK STATUS: Sleeper zeroes its
    projection on that tag, so the margin may be nothing but the stale tag.

    Dead players (bye, Out, IR, Doubtful, no team) are not deltas: a dead
    starter is a MUST FIX (:func:`repair_lineup`) and a dead bench player is
    never proposed. A player with no row on one board uses the other source
    (the consensus) instead of blocking the pair. ``legacy=True`` restores the
    pre-2026-11 behaviour (raw projections, missing row blocks, bye-only
    filter); the replay keeps it as the baseline the new rule is measured
    against.
    """
    if legacy:
        starters = [r for r in rows if r.slot and not r.locked]
        bench = [r for r in rows if not r.slot and not r.locked and not r.bye]
        own = lambda r: r.ours  # noqa: E731
        slp = lambda r: r.sleeper  # noqa: E731
    else:
        starters = [r for r in rows if r.slot and not r.locked and not r.dead]
        bench = [r for r in rows if not r.slot and not r.locked and not r.dead]
        own = lambda r: r.ours_eff  # noqa: E731
        slp = lambda r: r.sleeper_eff  # noqa: E731
    candidates = []
    for s in starters:
        elig = _SLOT_ELIGIBILITY.get(s.slot.upper(), set())
        for b in bench:
            if b.position not in elig:
                continue
            m_o, m_s = _margin(own(b), own(s)), _margin(slp(b), slp(s))
            verdict = _verdict(m_o, m_s, threshold)
            if verdict == "SWAP" and s.status_unconfirmed:
                verdict = "CHECK STATUS"
            if verdict:
                worst = min(m for m in (m_o, m_s) if m is not None)
                candidates.append((_RANK[verdict], worst, s, b, m_o, m_s, verdict))
    used: set = set()
    deltas: List[Delta] = []
    for _, _, s, b, m_o, m_s, verdict in sorted(
        candidates, key=lambda c: (c[0], c[1]), reverse=True
    ):
        if b.sleeper_id in used or s.sleeper_id in used:
            continue
        used.update({b.sleeper_id, s.sleeper_id})
        deltas.append(Delta(verdict, s.slot, s, b, m_o, m_s))
    return deltas


# ---------------------------------------------------------------------------
# Dead slots: starters who cannot score, and empty slots
# ---------------------------------------------------------------------------
#
# 2026 replay, carried-over lineups league-wide: 39 of 105 starters on bye or ruled
# out were still in (week 8 left Purdy and McCaffrey in). The pairwise rule above
# ranks on raw projections and cannot see an empty slot, so a dead starter was
# invisible to it. These functions treat a dead or empty slot as a fix to apply
# before any SWAP is weighed.


def assign_slots(
    slots: Sequence[str],
    candidates: Sequence[PlayerRow],
    value: Callable[[PlayerRow], float] = lambda r: r.blend,
) -> List[Optional[PlayerRow]]:
    """Exact best assignment of candidates to slot labels, aligned with ``slots``.

    A maximum-weight matching rather than a greedy fill: with crossing flex
    slots (W/R + W/T) the greedy answer depends on which slot is filled first.
    An entry is None when no candidate is eligible for that slot. Unknown slot
    labels (IDP, ...) are never filled.
    """
    out: List[Optional[PlayerRow]] = [None] * len(slots)
    if not slots or not candidates:
        return out
    cost = np.zeros((len(slots), len(candidates)))
    ok = np.zeros(cost.shape, dtype=bool)
    for i, slot in enumerate(slots):
        elig = _SLOT_ELIGIBILITY.get(str(slot).upper(), set())
        for j, r in enumerate(candidates):
            if r.position in elig:
                ok[i, j] = True
                # the epsilon makes any eligible pairing beat an empty one
                cost[i, j] = -(max(float(value(r)), 0.0) + 1e-4)
    for i, j in zip(*linear_sum_assignment(cost)):
        if ok[i, j]:
            out[i] = candidates[j]
    return out


@dataclass
class MustFix:
    """A starter who cannot score (or an empty slot) and the best replacement."""

    slot: str
    out_player: Optional[PlayerRow]  # None = nobody in the slot
    reason: str
    in_player: Optional[PlayerRow]  # None = no eligible player on the bench

    def line(self) -> str:
        slot = _SLOT_DISPLAY.get(self.slot, self.slot)
        who = (
            f"{self.out_player.name} ({self.out_player.position}, "
            f"{self.out_player.team}) is {self.reason}"
            if self.out_player
            else f"{slot} slot is empty"
        )
        if self.in_player is None:
            return (
                f"{slot:6s} {who} -> no eligible player on your bench "
                "(it scores 0 either way: pick someone up)"
            )
        r = self.in_player
        return (
            f"{slot:6s} {who} -> start {r.name} ({r.position}, {r.team}, "
            f"proj {r.blend:.1f})"
        )

    def as_delta(self) -> Optional[Delta]:
        """The same move as a ``Delta`` (verdict MUST FIX), for the ESPN writer.

        None when it is not a swap of two players (an empty slot, or nobody to
        bring in)."""
        if self.out_player is None or self.in_player is None:
            return None
        return Delta("MUST FIX", self.slot, self.out_player, self.in_player, None, None)


def repair_lineup(
    rows: Sequence[PlayerRow],
    roster_positions: Sequence[str],
    starters: Sequence[str],
    value: Callable[[PlayerRow], float] = lambda r: r.blend,
) -> Tuple[List[str], List[MustFix]]:
    """Replace every dead or empty starting slot; return ``(starters, fixes)``.

    A starter is dead when :attr:`PlayerRow.dead_reason` says so (bye, no team,
    Out/IR, Doubtful). A slot nobody occupies (``"0"``, or an id that is not on
    the roster) is repaired the same way. Locked starters are left alone: their
    game has started and Sleeper will not let them move. Replacements are live,
    unlocked bench players, assigned together so one man cannot fill two slots;
    a bench player whose Sleeper Out/Doubtful tag is unconfirmed is not used
    (we cannot say he plays). A slot with no eligible replacement is vacated.
    """
    by_id = {r.sleeper_id: r for r in rows}
    slots = current_slots(roster_positions, [str(p) for p in starters])
    started = {pid for _, pid in slots if pid != "0"}
    problems: List[Tuple[int, str, Optional[PlayerRow], str]] = []
    for i, (slot, pid) in enumerate(slots):
        if str(slot).upper() not in _SLOT_ELIGIBILITY:
            continue  # IDP and other slots we do not model
        row = by_id.get(pid) if pid != "0" else None
        if row is None:
            problems.append((i, slot, None, "empty"))
        elif not row.locked and row.dead:
            problems.append((i, slot, row, str(row.dead_reason)))
    bench = [
        r
        for r in rows
        if r.sleeper_id not in started
        and not r.locked
        and not r.dead
        and not r.status_unconfirmed
    ]
    chosen = assign_slots([slot for _, slot, _, _ in problems], bench, value)
    fixed = [pid for _, pid in slots]
    fixes: List[MustFix] = []
    for (i, slot, out, reason), pick in zip(problems, chosen):
        fixed[i] = pick.sleeper_id if pick else "0"
        fixes.append(MustFix(slot, out, reason, pick))
    return fixed, fixes


def reslot(
    rows: Sequence[PlayerRow], roster_positions: Sequence[str], starters: Sequence[str]
) -> List[PlayerRow]:
    """Copies of ``rows`` with ``slot``/``slot_index`` set from ``starters``."""
    slot_of = {
        pid: (slot, i)
        for i, (slot, pid) in enumerate(
            current_slots(roster_positions, [str(p) for p in starters])
        )
        if pid != "0"
    }
    return [
        dataclasses.replace(
            r,
            slot=slot_of.get(r.sleeper_id, (None, 999))[0],
            slot_index=slot_of.get(r.sleeper_id, (None, 999))[1],
        )
        for r in rows
    ]


def apply_swaps(starters: Sequence[str], deltas: Iterable[Delta]) -> List[str]:
    """``starters`` with every SWAP delta applied (nothing else is acted on)."""
    out = [str(p) for p in starters]
    for d in deltas:
        if d.verdict == "SWAP":
            out[out.index(d.out_player.sleeper_id)] = d.in_player.sleeper_id
    return out


@dataclass
class Recommendation:
    """What the tool says to do with a lineup: fixes first, then swaps."""

    starters: List[str]  # the lineup after MUST FIX and SWAP, in slot order
    must_fix: List[MustFix]
    deltas: List[Delta]  # judged on the lineup AFTER the must-fix repairs
    rows: List[PlayerRow]  # rows slotted into the repaired lineup


def recommend(
    rows: Sequence[PlayerRow],
    roster_positions: Sequence[str],
    starters: Sequence[str],
    threshold: float = 3.0,
) -> Recommendation:
    """MUST FIX repairs, then the deltas of the repaired lineup, then the swaps."""
    repaired, fixes = repair_lineup(rows, roster_positions, starters)
    slotted = reslot(rows, roster_positions, repaired)
    deltas = lineup_deltas(slotted, threshold)
    return Recommendation(apply_swaps(repaired, deltas), fixes, deltas, slotted)


def optimal_starters(
    rows: Sequence[PlayerRow],
    roster_positions: Sequence[str],
    value: Callable[[PlayerRow], float] = lambda r: r.blend,
) -> List[str]:
    """Best lineup for a roster with no lineup set yet, in ``roster_positions`` order.

    For ESPN/Yahoo from a pasted roster there is nothing to compare against, so
    the honest output is the lineup we RECOMMEND. Dead players are never
    started; ``"0"`` marks a slot nobody eligible can fill. Every slot label
    the optimizer knows is filled, SUPER_FLEX, K and DEF included (the old
    allocation keyed slots by display name and left SUPER_FLEX empty).
    """
    labels = [p for p in roster_positions if str(p).upper() not in _SKIP_SLOTS]
    pool = [r for r in rows if not r.dead and not r.status_unconfirmed]
    return [r.sleeper_id if r else "0" for r in assign_slots(labels, pool, value)]


def optimal_by_source(
    rows: List[PlayerRow], roster_positions: Sequence[str], source: str
) -> set:
    """Set of sleeper_ids the greedy optimizer would start under one source."""
    pool = [r.as_optimizer_dict(source) for r in rows if not r.locked or r.slot]
    lu = optimal_lineup(pool, roster_positions=list(roster_positions))
    return {p["sleeper_id"] for ps in lu["starters"].values() for p in ps}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt(v: Optional[float]) -> str:
    return "  -  " if v is None else f"{v:5.1f}"


def render(
    rows: List[PlayerRow],
    deltas: List[Delta],
    header: str,
    ours_label: str,
    must_fix: Optional[List[MustFix]] = None,
    banner: Optional[str] = None,
) -> str:
    """Plain-text report: MUST FIX first, then the lineup, the bench, the deltas.

    ``must_fix=None`` means the caller did not look (no section); an empty list
    prints that every starter has a game and is not ruled out.
    """
    lines = [header, ""]
    if banner:
        lines += [banner, ""]
    if must_fix is not None:
        if must_fix:
            lines.append(f"MUST FIX ({len(must_fix)}): starters who cannot score")
            lines += ["  " + f.line() for f in must_fix]
        else:
            lines.append(
                "MUST FIX: none -- every starter has a game and is not ruled out"
            )
        lines.append("")
    lines.append(
        f"  {'SLOT':7s}{'PLAYER':24s}{'POS':4s}{'TM':4s} {'OURS':>5s} {'SLPR':>5s} {'BLEND':>5s}  NOTES"
    )
    starters = sorted((r for r in rows if r.slot), key=lambda r: r.slot_index)
    bench = sorted((r for r in rows if not r.slot), key=lambda r: r.blend, reverse=True)
    for r in starters + bench:
        slot = _SLOT_DISPLAY.get(r.slot or "", r.slot) or "BN"
        lines.append(
            f"  {slot:7s}{r.name[:23]:24s}{r.position:4s}{r.team:4s} {_fmt(r.ours)} {_fmt(r.sleeper)} {r.blend:5.1f}  {', '.join(r.notes)}"
        )
    tot_o = sum(r.ours or 0 for r in starters)
    tot_s = sum(r.sleeper or 0 for r in starters)
    lines += [
        "",
        f"  Starters total: ours {tot_o:.1f} / Sleeper {tot_s:.1f}   (OURS = {ours_label})",
        "",
    ]
    if deltas:
        after = " after the MUST FIX moves" if must_fix else ""
        lines.append(
            f"DELTAS vs the lineup above{after} "
            "(rule: SWAP only when BOTH sources agree by the threshold):"
        )
        lines += ["  " + d.line() for d in deltas]
        if any(d.verdict == "CHECK STATUS" for d in deltas):
            lines.append(
                "  (CHECK STATUS: both sources favour the swap, but the starter's "
                "injury tag is unconfirmed for this week -- read the practice report/news first)"
            )
    else:
        lines.append("No changes: no bench player beats a starter on both sources.")
    return "\n".join(lines)
