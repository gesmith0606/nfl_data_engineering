"""Price specific trade packages: both sides' starting-lineup delta under the trade_scan values.

    echo "Nico$uave|Ashton Jeanty,Luther Burden|Nico Collins,Chuba Hubbard" |
        python scripts/trade_eval.py feetball

stdin lines: "<partner team>|<my players, comma-separated>|<their players>" (prefix match on names).
"""

import contextlib
import io
import runpy
import sys

LEAGUE = sys.argv[1]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    sys.argv = ["trade_scan.py", LEAGUE]
    g = runpy.run_path("scripts/trade_scan.py", run_name="scan")
vals, lineup, ME = g["vals"], g["lineup"], g["ME"]
me = vals[ME]
my_tot = lineup(me)[0]


def find(team, name):
    for x in vals[team]:
        if x[0].lower().startswith(name.lower()):
            return x
    raise SystemExit(f"not found: {name} on {team}")


for line in sys.stdin:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    team, give, get = [s.strip() for s in line.split("|")]
    give = [find(ME, n) for n in give.split(",")]
    get = [find(team, n) for n in get.split(",")]
    my_new = lineup([x for x in me if x not in give] + get)[0]
    th_new = lineup([x for x in vals[team] if x not in get] + give)[0]
    print(
        f"me {my_new - my_tot:+6.1f} | them {th_new - lineup(vals[team])[0]:+6.1f}"
        f" | {team[:22]:22} | GIVE "
        + " + ".join(f"{g[0]} ({g[2]:.0f})" for g in give)
        + "  FOR  "
        + " + ".join(f"{g[0]} ({g[2]:.0f})" for g in get)
    )
