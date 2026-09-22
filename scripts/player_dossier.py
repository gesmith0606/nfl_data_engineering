"""Per-player waiver dossier from our own Bronze data: last week's usage (snap/target/air-yard/carry
share), Sleeper injury status, same-position teammates on the injury report, next opponent with
spread/total, Sleeper 48h trending adds.

    python scripts/player_dossier.py data/draft/week3_candidates.txt

The names file has "## SECTION" headers followed by one player name per line.
"""

import glob
import sys

import pandas as pd

sys.path.insert(0, ".")
from src.sleeper_player_map import load_sleeper_players, normalize_name  # noqa: E402
from src import sleeper_http  # noqa: E402

wk = pd.read_parquet(
    sorted(glob.glob("data/bronze/players/weekly/season=2026/*.parquet"))[-1]
)
LAST = int(wk.week.max())
wk = wk[wk.week == LAST].copy()
wk["name"] = wk.player_display_name.map(normalize_name)
team_tg = wk.groupby("recent_team").targets.sum()
team_car = wk.groupby("recent_team").carries.sum()
team_ay = wk.groupby("recent_team").receiving_air_yards.sum()
sn = pd.read_parquet(
    sorted(glob.glob("data/bronze/players/snaps/season=2026/week=1/*.parquet"))[-1]
)
sn["name"] = sn.player.map(normalize_name)
dc = pd.read_parquet(
    sorted(glob.glob("data/bronze/depth_charts/season=2026/*.parquet"))[-1]
)
dc = dc[(dc.dt == dc.dt.max()) & (dc.pos_grp.str.contains("Off", na=False))].copy()
dc["name"] = dc.player_name.map(normalize_name)
inj = pd.read_parquet(
    sorted(glob.glob("data/bronze/players/injuries/season=2026/*.parquet"))[-1]
)
inj = inj[inj.week == inj.week.max()]
sch = pd.read_parquet(
    sorted(glob.glob("data/bronze/schedules/season=2026/*.parquet"))[-1]
)
g2 = sch[sch.week == LAST + 1]
opp = {}
for r in g2.itertuples():
    opp[r.home_team] = (
        r.away_team,
        "vs",
        -r.spread_line if pd.notna(r.spread_line) else None,
        r.total_line,
    )
    opp[r.away_team] = (r.home_team, "@", r.spread_line, r.total_line)
dr = pd.read_parquet(
    sorted(glob.glob("data/silver/defense/positional/season=*/opp_rankings_*.parquet"))[
        -1
    ]
)
dr = dr[dr.week == dr.week.max()]
drank = {(t, p): int(r) for t, p, r in zip(dr.team, dr.position, dr["rank"])}
reg = load_sleeper_players()
adds = {
    str(t["player_id"]): t["count"]
    for t in sleeper_http.fetch_sleeper_json(
        "https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=48&limit=300"
    )
    or []
}
byname = {
    normalize_name(m.get("full_name") or ""): (sid, m)
    for sid, m in reg.items()
    if isinstance(m, dict)
    and m.get("position") in ("QB", "RB", "WR", "TE")
    and m.get("team")
}
alias = {"LA": "LAR"}


def dossier(n):
    key = normalize_name(n)
    sid, m = byname.get(key, (None, {}))
    team = m.get("team")
    pos = m.get("position")
    w = wk[wk.name == key]
    w = w.iloc[0] if len(w) else None
    s = sn[sn.name == key]
    s = s.iloc[0] if len(s) else None
    d = dc[dc.name == key]
    d = d.iloc[0] if len(d) else None
    mates = inj[
        (inj.team == team) & (inj.position == pos) & (inj.report_status.notna())
    ]
    o = opp.get(team) or opp.get(alias.get(team, team))
    return {
        "player": n,
        "pos": pos,
        "team": team,
        "inj": m.get("injury_status") or "",
        "depth": f"{d.pos_abb}{d.pos_rank}" if d is not None else "-",
        "snap%": round(float(s.offense_pct) * 100) if s is not None else None,
        "tgt": int(w.targets) if w is not None else None,
        "tgt%": (
            round(100 * w.targets / team_tg.get(w.recent_team, 1))
            if w is not None
            else None
        ),
        "ay%": (
            round(100 * w.receiving_air_yards / team_ay.get(w.recent_team, 1))
            if w is not None and team_ay.get(w.recent_team, 0)
            else None
        ),
        "car": int(w.carries) if w is not None else None,
        "car%": (
            round(100 * w.carries / team_car.get(w.recent_team, 1))
            if w is not None
            else None
        ),
        "recyd": int(w.receiving_yards) if w is not None else None,
        "rushyd": int(w.rushing_yards) if w is not None else None,
        "passyd": int(w.passing_yards) if w is not None else None,
        "td": (
            int(w.rushing_tds + w.receiving_tds + w.passing_tds)
            if w is not None
            else None
        ),
        "next": f"{o[1]}{o[0]} {o[2]:+.1f} O/U{o[3]}" if o else "BYE?",
        "dvp": drank.get((o[0], pos)) if o else None,
        "adds": adds.get(sid, 0),
        "same-pos injured": ", ".join(
            f"{r.full_name}({r.report_status})" for r in mates.itertuples()
        ),
    }


pd.set_option("display.width", 260)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 70)
for section in open(sys.argv[1]).read().split("##")[1:]:
    title, *names = [ln.strip() for ln in section.strip().splitlines() if ln.strip()]
    print(f"\n===== {title} =====")
    print(pd.DataFrame([dossier(n) for n in names]).to_string(index=False))
