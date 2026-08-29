#!/usr/bin/env python3
"""Cross-platform draft value report — VALUES / BUSTS / BREAKOUTS / DEEP SLEEPERS.

For each ADP source (the room you will draft in), prices every player against
our projections (room scoring) and fires the doctrine rules in
``src/draft_value.py`` (docs/DRAFT_DOCTRINE.md). Also reports players that are
VALUE on 2+ platforms ("everyone underprices him") and the biggest
cross-platform disagreements (where the same player is 2+ rounds apart).

    python scripts/draft_value_report.py --scoring standard --sources espn,ffc
    python scripts/draft_value_report.py --league la_liga
    python scripts/draft_value_report.py --scoring half_ppr --sources ffc --top 12 --csv

ADP files come from ``refresh_adp.py --source <src> --scoring <fmt>`` under
``data/adp/``; the newest matching file per source is used.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Doctrine rule tags use "§"/"≥"; the Windows console default (cp1252) cannot encode them.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402
from src.draft_optimizer import compute_value_scores  # noqa: E402
from src.draft_tiers import compute_tiers  # noqa: E402
from src.draft_value import attach_features, label_board, summarize  # noqa: E402


def latest_projections(season: int, scoring: str) -> Optional[str]:
    files = sorted(glob.glob(os.path.join("output", "projections", f"preseason_{season}_{scoring}_*.csv")))
    return files[-1] if files else None


def adp_file(source: str, scoring: str) -> Optional[str]:
    """Newest ADP board for *source*, preferring an exact *scoring* match.

    FFC and Sleeper publish genuinely different PPR and half-PPR boards — on
    the 2026 files the mean |delta rank| is 10.4 with 61 players a full round
    apart — so an mtime-only pick silently priced a half-PPR league off the
    PPR board. ESPN's own ADP is scoring-agnostic (the suffix just records the
    refresh flag), so it lands on the same board either way.
    """
    exact = os.path.join("data", "adp", f"adp_{source}_{scoring}.csv")
    if os.path.exists(exact):
        return exact
    cands = [
        p
        for p in glob.glob(os.path.join("data", "adp", f"adp_{source}_*.csv"))
        if not os.path.basename(p)[:-4].split("_")[-1].isdigit()
    ]
    if not cands and source == "ffc" and os.path.exists(os.path.join("data", "adp_latest.csv")):
        return os.path.join("data", "adp_latest.csv")
    return max(cands, key=os.path.getmtime) if cands else None


def _fmt(df: pd.DataFrame) -> str:
    if df.empty:
        return "  (none)"
    show = df.copy()
    for c in ("age", "td_share", "vorp", "projected_season_points"):
        if c in show.columns:
            show[c] = pd.to_numeric(show[c], errors="coerce").round(2 if c == "td_share" else 1)
    for c in ("adp_rank", "adp_gap", "years_exp", "model_rank", "vbd_rank"):
        if c in show.columns:
            show[c] = pd.to_numeric(show[c], errors="coerce").astype("Int64")
    return show.to_string(index=False)


def build(projections: pd.DataFrame, adp: pd.DataFrame, roster_format: str, teams: int, season: int) -> pd.DataFrame:
    board = compute_value_scores(projections, adp, roster_format=roster_format, n_teams=teams)
    board["tier"] = compute_tiers(board)
    return label_board(attach_features(board, season))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Draft value report: values / busts / breakouts per ADP source")
    p.add_argument("--league", choices=list(config.LEAGUE_PRESETS), help="League preset (sets scoring/roster/teams/source)")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--scoring", choices=["ppr", "half_ppr", "standard"])
    p.add_argument("--roster-format")
    p.add_argument("--teams", type=int)
    p.add_argument("--sources", help="Comma list of ADP sources: espn,ffc,sleeper,mfl (default: preset platform or espn,ffc)")
    p.add_argument("--projections-file")
    p.add_argument("--top", type=int, default=8)
    p.add_argument("--csv", action="store_true", help="Also write output/draft_reports/value_report_<scoring>_<ts>.csv")
    args = p.parse_args(argv)

    preset = config.LEAGUE_PRESETS.get(args.league, {}) if args.league else {}
    scoring = args.scoring or preset.get("scoring_format") or "half_ppr"
    roster_format = args.roster_format or preset.get("roster") or "standard"
    teams = args.teams or preset.get("teams") or 12
    platform = preset.get("platform")
    default_sources = {"espn": "espn,ffc", "sleeper": "sleeper,ffc", "yahoo": "ffc,espn"}.get(platform, "espn,ffc")
    sources = [s.strip() for s in (args.sources or default_sources).split(",") if s.strip()]

    proj_path = args.projections_file or latest_projections(args.season, scoring)
    if not proj_path or not os.path.exists(proj_path):
        print(f"ERROR: no projections for {scoring}. Run: python scripts/generate_projections.py --preseason --season {args.season} --scoring {scoring}")
        return 1
    projections = pd.read_csv(proj_path)
    projections = projections[projections["position"].isin(["QB", "RB", "WR", "TE", "K"])]
    print(f"Projections: {proj_path}  |  {scoring} | {roster_format} | {teams} teams")

    labeled: Dict[str, pd.DataFrame] = {}
    for src in sources:
        path = adp_file(src, scoring)
        if not path:
            print(f"\n[{src}] no ADP file — run: python scripts/refresh_adp.py --source {src} --scoring {scoring}")
            continue
        adp = pd.read_csv(path)
        lab = build(projections, adp, roster_format, teams, args.season)
        labeled[src] = lab
        s = summarize(lab, top=args.top)
        print("\n" + "=" * 96)
        print(f"[{src}] ADP: {path}  ({int(lab['adp_rank'].notna().sum())} players priced)")
        print("=" * 96)
        for title, key in (("VALUES — model ≥1 round ahead of ADP (§10)", "values"),
                           ("BUSTS — ADP inflation + age/TD/top-5 signals (§20-28)", "busts"),
                           ("BREAKOUTS — young + vacated opportunity / TD regression (§29-34)", "breakouts"),
                           ("DEEP SLEEPERS — ADP >100 with a startable rank (§29)", "deep_sleepers")):
            print(f"\n{title}")
            print(_fmt(s[key]))
        # ADVISORY keyword news (draft_value.load_news_risk): risk keywords in
        # the last ~14 days of ingested feeds. Tag-only — verify before
        # drafting; §36 (market-faded + NEWS) is the do-not-draft combination.
        if "news_risk" in lab.columns and lab["news_risk"].notna().any():
            adv = lab[lab["news_risk"].notna()].sort_values(
                "adp_rank", na_position="last"
            )
            cols = [c for c in ("player_name", "position", "vbd_rank", "adp_rank",
                                "news_risk", "roster_status") if c in adv.columns]
            print("\nNEWS ADVISORIES — keyword hits in recent news (verify before drafting; §36)")
            print(_fmt(adv[cols].head(max(args.top, 12))))

    if len(labeled) >= 2:
        merged = None
        for src, lab in labeled.items():
            part = lab[["player_name", "position", "vbd_rank", "adp_rank", "flag_value", "flag_bust"]].copy()
            part["adp_rank"] = part["adp_rank"].where(part["adp_rank"] <= 200)
            part = part.rename(columns={"adp_rank": f"adp_{src}", "flag_value": f"value_{src}", "flag_bust": f"bust_{src}"})
            merged = part if merged is None else merged.merge(part, on=["player_name", "position", "vbd_rank"], how="outer")
        vcols = [c for c in merged.columns if c.startswith("value_")]
        acols = [c for c in merged.columns if c.startswith("adp_")]
        merged["value_on"] = merged[vcols].fillna(False).sum(axis=1)
        merged["adp_spread"] = merged[acols].max(axis=1) - merged[acols].min(axis=1)
        print("\n" + "=" * 96)
        print("CROSS-PLATFORM: value on 2+ sources (everyone underprices him)")
        print("=" * 96)
        print(_fmt(merged[merged["value_on"] >= 2].sort_values("vbd_rank").head(args.top)[["player_name", "position", "vbd_rank"] + acols]))
        print("\nBIGGEST PLATFORM DISAGREEMENTS (≥2 rounds apart, both priced — draft him where he's cheap)")
        both = merged.dropna(subset=acols)
        print(_fmt(both[both["adp_spread"] >= 24].sort_values("adp_spread", ascending=False).head(args.top)[["player_name", "position", "vbd_rank"] + acols + ["adp_spread"]]))

    if args.csv and labeled:
        os.makedirs(os.path.join("output", "draft_reports"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = pd.concat([lab.assign(adp_source=src) for src, lab in labeled.items()])
        path = os.path.join("output", "draft_reports", f"value_report_{scoring}_{ts}.csv")
        out.to_csv(path, index=False)
        print(f"\nSaved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
