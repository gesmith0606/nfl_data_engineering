#!/usr/bin/env python3
"""Empirical best-drafts study on our own data (2021-2025):
1. League-winners per season = players beating ADP positional rank by >= 10 spots
   with a top-24 (RB/WR) / top-12 (QB/TE) actual finish.
2. Surplus value by draft round x position: actual half-PPR points minus the
   points of the baseline player at that ADP slot (what the round 'owed you').
3. Where do the top-5 value picks of each season come from (round, position, age)?

CAVEAT: the league-winner metric (beat positional ADP by >= 10 spots) is
definitionally near-impossible for rounds 1-3 — read early rounds off the
surplus-vs-slot table instead. Findings feed docs/DRAFT_DOCTRINE.md §38-41.
"""
import sys, os, importlib.util
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT); sys.path.insert(0, "src"); sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd, numpy as np, logging; logging.disable(logging.CRITICAL)
spec = importlib.util.spec_from_file_location("bt", "scripts/backtest_draft_flags.py"); bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
frames=[f for s in range(2021,2026) if (f:=bt.build_season(s, 200.0)) is not None]
df=pd.concat(frames, ignore_index=True)
df["adp_round"]=((df["adp"]-1)//12+1).astype(int)
# Expected points at each ADP slot = median actual points of that positional ADP rank across seasons
exp = df.groupby(["position","adp_pos_rank"])["points"].median().rename("expected_at_slot")
df = df.merge(exp, on=["position","adp_pos_rank"], how="left")
df["surplus"] = df["points"] - df["expected_at_slot"]
top_fin = {"RB":24,"WR":24,"QB":12,"TE":12}
df["league_winner"] = (df["adp_pos_rank"]-df["pos_rank"]>=10) & (df["pos_rank"]<=df["position"].map(top_fin))
print("== LEAGUE-WINNERS (beat positional ADP by >=10, finished startable), rate by ADP round")
lw = df.groupby("adp_round").agg(n=("league_winner","size"), winners=("league_winner","sum"))
lw["rate"]=(lw.winners/lw.n).round(3); print(lw.head(13).to_string())
print("\n== by round x position (winner rate, rounds 1-12)")
piv = df[df.adp_round<=12].pivot_table(index="position", columns="adp_round", values="league_winner", aggfunc="mean").round(2)
print(piv.to_string())
print("\n== mean SURPLUS points vs slot expectation, by round x position (rounds 1-10)")
piv2 = df[df.adp_round<=10].pivot_table(index="position", columns="adp_round", values="surplus", aggfunc="mean").round(0)
print(piv2.to_string())
print("\n== top 5 value picks per season (points over slot expectation)")
for y,g in df.groupby("season"):
    top=g.nlargest(5,"surplus")[["_name_key","position","adp","adp_round","age","points","surplus"]]
    print(y); print(top.to_string(index=False))
