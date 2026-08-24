#!/usr/bin/env python3
"""Historical draft replay: advisor drafts 2021-2025 with point-in-time info only,
rosters scored by ACTUAL season results (Silver usage half-PPR).

Point-in-time legality: projections come from generate_preseason_projections on
seasons Y-2/Y-1 aggregated from Silver weekly usage (no consensus anchor - the
external ranking caches are 2026-only and would leak). ADP = that season's real
Sept-1 FFC snapshot. Opponents draft by that ADP + noise (the market's average
drafter). Bust metric parity with backtest_draft_flags.py.

Known replay handicaps vs production (both make this a LOWER bound on the
production stack): no consensus anchor, and no rookie projections (no
historical/college inputs passed) — the advisor cannot draft rookies at all
while the ADP bots do. Result 2026-08-24 (2 seeds): pooled mean rank 6.42/12
(field 6.5) — even with the market on actual results, season range 1.5 (2022)
to 10.0 (2025, a strong rookie year). The unfiltered first run (retirees +
1-game ghosts on the board) ranked 9.94/12 — the room-universe/market filter
is load-bearing; see docs/DRAFT_DOCTRINE.md §10.
"""
import sys, os, glob, random, collections, warnings; warnings.filterwarnings("ignore")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "src")); os.chdir(ROOT)
import numpy as np, pandas as pd, logging; logging.disable(logging.CRITICAL)
from draft_optimizer import compute_value_scores, DraftBoard, DraftAdvisor, MockDraftSimulator, name_key
from projection_engine import generate_preseason_projections

STATS = ["passing_yards","passing_tds","interceptions","rushing_yards","rushing_tds","carries",
         "receiving_yards","receiving_tds","receptions","targets"]
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 2

def usage(season):
    fs = sorted(glob.glob(f"data/silver/players/usage/season={season}/*.parquet"))
    if not fs: return None
    df = pd.read_parquet(fs[-1])
    if "season_type" in df.columns: df = df[df["season_type"]=="REG"]
    df = df[df["position"].isin(["QB","RB","WR","TE"])].copy()
    name = "player_display_name" if "player_display_name" in df.columns else "player_name"
    agg = {c:(c,"sum") for c in STATS if c in df.columns}
    g = df.groupby(["player_id","position"]).agg(player_name=(name,"first"), recent_team=("recent_team","last"),
        games=("week","nunique"), fp=("fantasy_points","sum"), rec=("receptions","sum"), **agg).reset_index()
    g["season"] = season
    g["actual_half_ppr"] = g["fp"] + 0.5*g["rec"]
    return g

def starters_points(roster):
    by = collections.defaultdict(list)
    for p in roster: by[p["pos"]].append(p["pts"])
    for k in by: by[k].sort(reverse=True)
    t = sum(by.get("QB",[0])[:1])+sum(by.get("RB",[0,0])[:2])+sum(by.get("WR",[0,0])[:2])+sum(by.get("TE",[0])[:1])
    flex = sorted(by.get("RB",[])[2:]+by.get("WR",[])[2:]+by.get("TE",[])[1:], reverse=True)
    return t + (flex[0] if flex else 0.0)

pooled_ranks, rows = [], []
for Y in range(2021, 2026):
    hist = [usage(Y-2), usage(Y-1)]; act = usage(Y)
    adp_path = f"data/adp/history/adp_ffc_half_ppr_{Y}.csv"
    if any(h is None for h in hist) or act is None or not os.path.exists(adp_path): continue
    seasonal = pd.concat(hist, ignore_index=True)
    proj = generate_preseason_projections(seasonal, scoring_format="half_ppr", target_season=Y)
    adp = pd.read_csv(adp_path)
    adp["adp_rank"] = adp["adp"].rank(method="first")
    board_df = compute_value_scores(proj, adp[["player_name","adp_rank","stdev"]], roster_format="espn_default", n_teams=12)
    # Room-universe filter: only players priced by that season's ADP. Without it
    # the heuristic pool offers retirees and 1-game artifacts (Gronk/AB/Wilkerson
    # in the 2023 diag) that no real room contains — production suppresses them
    # via the consensus anchor + low-sample market filter, absent here.
    board_df = board_df[board_df["adp_rank"].notna()].reset_index(drop=True)
    apts = dict(zip(act.player_name.map(name_key), act.actual_half_ppr))
    ranks, margins = [], []
    for slot in range(1,13):
        for seed in range(SEEDS):
            random.seed(100*Y+10*slot+seed); np.random.seed(100*Y+10*slot+seed)
            board = DraftBoard(board_df.copy(), roster_format="espn_default", n_teams=12)
            adv = DraftAdvisor(board, scoring_format="half_ppr")
            sim = MockDraftSimulator(board, user_pick=slot, n_teams=12, randomness=4)
            res = sim.run_full_simulation(adv, rounds=16)
            rosters = collections.defaultdict(list)
            for p in res["picks"]:
                i=(p["pick"]-1)%12; rnd=(p["pick"]-1)//12+1; s = 12-i if rnd%2==0 else i+1
                rosters[s].append({"pos": p["position"], "pts": float(apts.get(name_key(p["player_name"]), 0.0))})
            scores = {s: starters_points(r) for s,r in rosters.items()}
            my = scores.get(slot,0.0)
            ranks.append(1+sum(1 for s,v in scores.items() if s!=slot and v>my))
            margins.append(my-np.mean([v for s,v in scores.items() if s!=slot]))
    pooled_ranks += ranks
    rows.append({"season":Y,"sims":len(ranks),"mean_rank":round(np.mean(ranks),2),
                 "top3":round(np.mean([r<=3 for r in ranks]),2),"bottom3":round(np.mean([r>=10 for r in ranks]),2),
                 "margin_pts":round(np.mean(margins),0)})
    print(rows[-1], flush=True)
print("\nPOOLED", len(pooled_ranks), "sims | scored by ACTUAL season results")
print(f"mean rank {np.mean(pooled_ranks):.2f} (field 6.5) | median {np.median(pooled_ranks):.0f} | top-3 {np.mean([r<=3 for r in pooled_ranks]):.0%} | bottom-3 {np.mean([r>=10 for r in pooled_ranks]):.0%}")
