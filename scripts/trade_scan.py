"""Trade scanner: ROS value per player, each team's optimal lineup, and win-win swaps.

    python scripts/trade_scan.py feetball   # every team's optimal lineup + trades that help me
    python scripts/trade_scan.py la_liga
    python scripts/trade_scan.py mantis            # rosters pulled live from Sleeper

League rosters: data/draft/<league>_2026_league_rosters.txt (Feetball: "name|pos|team" per line
from the Yahoo taken-players list; La Liga: one "Team [w-l]: Name (POS), ..." line per team
from the ESPN League Rosters page). Refresh them after every waiver run.

Value = FantasyPros ROS consensus rank mapped to our preseason season-points curve
(rank -> points via our own preseason board sorted by points), so every rostered player
gets a value even when our board lacks him. Injured-reserve players are zeroed.
"""

import glob
import itertools
import json
import re
import sys

sys.path.insert(0, ".")
import pandas as pd  # noqa: E402
from src.sleeper_player_map import normalize_name, load_sleeper_players  # noqa: E402

LEAGUE = sys.argv[1]
DRAFT = "data/draft"
SLOTS = {
    "feetball": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1},
    "la_liga": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2},
    "mantis": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 2, "SFLEX": 1},
}[LEAGUE]
ME = {"feetball": "The Oracle", "la_liga": "The Oracle", "mantis": "Gforceee"}[LEAGUE]
NEED_POS = {"feetball": "WR", "la_liga": "RB", "mantis": "QB"}[LEAGUE]

# ---- values ---------------------------------------------------------------
fp = json.load(open("data/external/fantasypros_rankings.json"))["players"]
fp_rank = {(normalize_name(p["player_name"]), p["position"]): p["rank"] for p in fp}
pre = pd.read_parquet(
    sorted(
        glob.glob(
            "data/gold/projections/preseason/season=2026/season_proj_half_ppr_*.parquet"
        )
    )[-1]
)
pre = (
    pre[pre.position.isin(["QB", "RB", "WR", "TE"])]
    .sort_values("projected_season_points", ascending=False)
    .reset_index(drop=True)
)
curve = pre.projected_season_points.tolist()
pre_pts = {
    (normalize_name(n), p): float(v)
    for n, p, v in zip(pre.player_name, pre.position, pre.projected_season_points)
}
reg = load_sleeper_players()
inj = {
    normalize_name(m.get("full_name") or ""): m.get("injury_status")
    for m in reg.values()
    if isinstance(m, dict) and m.get("position") in ("QB", "RB", "WR", "TE")
}
REMAIN = 16 / 17


def value(name, pos):
    key = (normalize_name(name), pos)
    r = fp_rank.get(key)
    v = curve[min(r - 1, len(curve) - 1)] if r else pre_pts.get(key, 0.0) * 0.8
    st = inj.get(key[0])
    if st in ("IR", "PUP", "Out", "Sus"):
        v = v * (0.0 if st in ("IR", "PUP") else 0.5)
    return round(v * REMAIN, 1)


# ---- rosters ----------------------------------------------------------------
teams = {}
if LEAGUE == "feetball":
    for line in open(f"{DRAFT}/feetball_2026_league_rosters.txt", encoding="utf-8"):
        if "|" not in line:
            continue
        n, p, t = line.strip().split("|")
        teams.setdefault(t, []).append((n, p))
elif LEAGUE == "la_liga":
    for line in open(f"{DRAFT}/la_liga_2026_league_rosters.txt", encoding="utf-8"):
        m = re.match(r"(.+?) \[.*?\]: (.*)", line.strip())
        if not m:
            continue
        for item in m.group(2).split(", "):
            mm = re.match(r"(.+?) \((QB|RB|WR|TE)", item)
            if mm:
                teams.setdefault(m.group(1), []).append((mm.group(1), mm.group(2)))
else:
    from src import config, sleeper_http

    lid = config.LEAGUE_PRESETS["mantis"]["league_id"]
    users = {
        u["user_id"]: u.get("display_name") for u in sleeper_http.get_league_users(lid)
    }
    for r in sleeper_http.get_league_rosters(lid):
        for pid in r.get("players") or []:
            m = reg.get(str(pid), {})
            if m.get("position") in ("QB", "RB", "WR", "TE"):
                teams.setdefault(users.get(r.get("owner_id")), []).append(
                    (m["full_name"], m["position"])
                )

vals = {t: [(n, p, value(n, p)) for n, p in ps] for t, ps in teams.items()}


def lineup(players):
    """Greedy optimal lineup -> (total, starters, bench)."""
    pool = sorted(players, key=lambda x: -x[2])
    used, starters = set(), []
    for pos in ("QB", "RB", "WR", "TE"):
        k = SLOTS.get(pos, 0)
        for x in pool:
            if k == 0:
                break
            if x[1] == pos and x[0] not in used:
                used.add(x[0])
                starters.append((pos, x))
                k -= 1
    for slot, elig in (
        ("FLEX", ("RB", "WR", "TE")),
        ("SFLEX", ("QB", "RB", "WR", "TE")),
    ):
        k = SLOTS.get(slot, 0)
        for x in pool:
            if k == 0:
                break
            if x[1] in elig and x[0] not in used:
                used.add(x[0])
                starters.append((slot, x))
                k -= 1
    bench = [x for x in pool if x[0] not in used]
    return round(sum(x[2] for _, x in starters), 1), starters, bench


print(f"===== {LEAGUE}: optimal lineups by ROS value =====")
base = {}
for t, ps in sorted(vals.items(), key=lambda kv: -lineup(kv[1])[0]):
    tot, st, bn = lineup(ps)
    base[t] = tot
    weak = {
        pos: min([x[2] for s, x in st if x[1] == pos] or [0])
        for pos in ("QB", "RB", "WR", "TE")
    }
    bench_top = ", ".join(f"{x[0]} {x[1]} {x[2]:.0f}" for x in bn[:4])
    weak_s = " ".join(f"{p}{weak[p]:.0f}" for p in ("QB", "RB", "WR", "TE"))
    print(f"{t[:24]:24} starters {tot:6.1f} | weakest {weak_s} | bench: {bench_top}")

me = vals[ME]
my_tot, my_st, my_bn = lineup(me)
print(f"\nMY STARTERS: " + ", ".join(f"{s}:{x[0]} {x[2]:.0f}" for s, x in my_st))
print("MY BENCH:    " + ", ".join(f"{x[0]} {x[1]} {x[2]:.0f}" for x in my_bn))

# ---- trade search -----------------------------------------------------------
print(
    f"\n===== trades that raise MY starting total (target position {NEED_POS}); partner delta shown ====="
)
found = []
my_names = [x for x in me]
for t, ps in vals.items():
    if t == ME:
        continue
    their_tot = base[t]
    targets = [x for x in ps if x[1] == NEED_POS]
    for give_n in (1, 2):
        for give in itertools.combinations(me, give_n):
            if any(g[1] == NEED_POS for g in give):
                continue
            for get_n in (1, 2):
                for get in itertools.combinations(ps, get_n):
                    if not any(g[1] == NEED_POS for g in get):
                        continue
                    if get_n == 2 and give_n == 1:
                        continue
                    my_new = lineup([x for x in me if x not in give] + list(get))[0]
                    th_new = lineup([x for x in ps if x not in get] + list(give))[0]
                    d_me, d_th = round(my_new - my_tot, 1), round(th_new - their_tot, 1)
                    if d_me >= 8 and d_th >= -6:
                        found.append((d_me, d_th, t, give, get))
found.sort(key=lambda f: -(f[0] + 0.5 * max(f[1], 0)))
seen = set()
for d_me, d_th, t, give, get in found:
    key = (t, tuple(sorted(g[0] for g in give)), tuple(sorted(g[0] for g in get)))
    if key in seen:
        continue
    seen.add(key)
    print(
        f"me {d_me:+5.1f} | them {d_th:+5.1f} | {t[:22]:22} | GIVE "
        + " + ".join(f"{g[0]} ({g[1]} {g[2]:.0f})" for g in give)
        + "  FOR  "
        + " + ".join(f"{g[0]} ({g[1]} {g[2]:.0f})" for g in get)
    )
    if len(seen) >= 25:
        break
