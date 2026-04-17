#!/usr/bin/env python3
"""
Generate NFL content packages for NotebookLM.

Produces rich markdown files from our projection, matchup, and sentiment
data that can be uploaded to NotebookLM for audio overview (podcast)
generation, summaries, and visual content.

Usage:
    python scripts/generate_notebooklm_content.py --type weekly --week 1 --season 2026
    python scripts/generate_notebooklm_content.py --type rankings --scoring half_ppr
    python scripts/generate_notebooklm_content.py --type matchup --teams "KC vs BUF" --week 1
"""

import argparse
import glob as globmod
import os
import sys
from datetime import datetime
from typing import Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "notebooklm")


def _load_projections(season: int, scoring: str = "half_ppr") -> pd.DataFrame:
    """Load latest preseason projections."""
    pattern = os.path.join(
        GOLD_DIR, f"projections/preseason/season={season}/season_proj_*.parquet"
    )
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _load_predictions(season: int, week: int) -> pd.DataFrame:
    """Load game predictions for a given week."""
    for w in [str(week), f"{week:02d}"]:
        pattern = os.path.join(
            GOLD_DIR, f"predictions/season={season}/week={w}/predictions_*.parquet"
        )
        files = sorted(globmod.glob(pattern))
        if files:
            return pd.read_parquet(files[-1])
    return pd.DataFrame()


def generate_weekly_content(
    season: int, week: int, scoring: str = "half_ppr"
) -> str:
    """Generate weekly podcast content."""
    proj = _load_projections(season, scoring)
    preds = _load_predictions(season, week)

    lines = [
        f"# NFL Fantasy Football Weekly Breakdown",
        f"## Season {season}, Week {week} | {scoring.replace('_', ' ').title()} Scoring",
        f"*Generated {datetime.now().strftime('%B %d, %Y')}*",
        "",
        "---",
        "",
    ]

    if not proj.empty:
        # Top 10 overall
        lines.append("## Top 10 Fantasy Plays This Week")
        lines.append("")
        top = proj.sort_values("projected_season_points", ascending=False).head(10)
        for i, (_, row) in enumerate(top.iterrows(), 1):
            name = row.get("player_name", "Unknown")
            pos = row.get("position", "?")
            team = row.get("recent_team", "?")
            pts = row.get("projected_season_points", 0)
            lines.append(f"{i}. **{name}** ({pos}, {team}) — {pts:.1f} projected points")
        lines.append("")

        # Position breakdowns
        for pos in ["QB", "RB", "WR", "TE"]:
            pos_df = proj[proj["position"] == pos].sort_values(
                "projected_season_points", ascending=False
            )
            lines.append(f"## {pos} Rankings")
            lines.append("")

            # Elite tier
            elite = pos_df.head(5)
            lines.append("### Must-Start (Elite Tier)")
            for _, row in elite.iterrows():
                name = row.get("player_name", "Unknown")
                team = row.get("recent_team", "?")
                pts = row.get("projected_season_points", 0)
                floor_val = pts * 0.7  # approximate
                ceil_val = pts * 1.3
                lines.append(
                    f"- **{name}** ({team}): {pts:.1f} pts "
                    f"(floor {floor_val:.0f}, ceiling {ceil_val:.0f})"
                )
            lines.append("")

            # Sleepers (ranked 15-25)
            sleepers = pos_df.iloc[14:25] if len(pos_df) > 25 else pos_df.tail(5)
            lines.append("### Sleeper Picks")
            for _, row in sleepers.iterrows():
                name = row.get("player_name", "Unknown")
                team = row.get("recent_team", "?")
                pts = row.get("projected_season_points", 0)
                lines.append(f"- **{name}** ({team}): {pts:.1f} pts — under the radar")
            lines.append("")

    # Game predictions
    if not preds.empty:
        lines.append("## Game Predictions")
        lines.append("")
        for _, row in preds.iterrows():
            away = row.get("away_team", "?")
            home = row.get("home_team", "?")
            spread = row.get("predicted_spread", 0)
            total = row.get("predicted_total", 0)
            tier = row.get("confidence_tier", "")
            fav = home if spread < 0 else away
            lines.append(
                f"- **{away} @ {home}**: {fav} by {abs(spread):.1f}, "
                f"total {total:.1f} ({tier} confidence)"
            )
        lines.append("")

    # Closing
    lines.extend([
        "## Key Takeaways",
        "",
        "1. The top-tier players remain must-starts regardless of matchup",
        "2. Look for value in the sleeper picks — these players have upside that isn't reflected in their ADP",
        "3. Pay attention to injury reports as game day approaches — late scratches create last-minute opportunities",
        "",
        "---",
        f"*Data sourced from NFL Data Engineering projection models. MAE: 4.80 (2022-2024 backtest).*",
    ])

    return "\n".join(lines)


def generate_rankings_content(
    season: int, scoring: str = "half_ppr"
) -> str:
    """Generate full rankings overview content."""
    proj = _load_projections(season, scoring)
    if proj.empty:
        return "# No projection data available"

    lines = [
        f"# {season} NFL Fantasy Football Rankings",
        f"## {scoring.replace('_', ' ').title()} Scoring — Complete Position Rankings",
        f"*Generated {datetime.now().strftime('%B %d, %Y')}*",
        "",
        "---",
        "",
    ]

    for pos, label, replacement in [
        ("QB", "Quarterback", 13),
        ("RB", "Running Back", 25),
        ("WR", "Wide Receiver", 30),
        ("TE", "Tight End", 13),
    ]:
        pos_df = proj[proj["position"] == pos].sort_values(
            "projected_season_points", ascending=False
        ).reset_index(drop=True)

        if pos_df.empty:
            continue

        lines.append(f"## {label} Rankings ({len(pos_df)} players)")
        lines.append("")

        # Tier assignments
        tier_cuts = {
            "QB": [2, 5, 12],
            "RB": [3, 10, 24],
            "WR": [4, 12, 30],
            "TE": [2, 5, 12],
        }
        elite, strong, starter = tier_cuts.get(pos, [2, 8, 20])
        tiers = [
            ("Elite (Must-Draft)", 0, elite),
            ("Strong Starter", elite, strong),
            ("Solid Starter", strong, starter),
            ("Bench/Flex", starter, min(40, len(pos_df))),
        ]

        for tier_name, start, end in tiers:
            tier_players = pos_df.iloc[start:end]
            if tier_players.empty:
                continue
            lines.append(f"### {tier_name}")
            for i, (_, row) in enumerate(tier_players.iterrows()):
                rank = start + i + 1
                name = row.get("player_name", "Unknown")
                team = row.get("recent_team", "?")
                pts = row.get("projected_season_points", 0)
                lines.append(f"{rank}. **{name}** ({team}) — {pts:.1f} pts")
            lines.append("")

        # Replacement level context
        if len(pos_df) > replacement:
            repl_player = pos_df.iloc[replacement - 1]
            lines.append(
                f"*Replacement level ({pos}{replacement}): "
                f"{repl_player.get('player_name', '?')} at "
                f"{repl_player.get('projected_season_points', 0):.1f} pts*"
            )
            lines.append("")

    # Overall top 25 by VORP
    if "vorp" in proj.columns:
        lines.append("## Overall Top 25 by Value Over Replacement (VORP)")
        lines.append("")
        top25 = proj.sort_values("vorp", ascending=False).head(25)
        for i, (_, row) in enumerate(top25.iterrows(), 1):
            name = row.get("player_name", "Unknown")
            pos = row.get("position", "?")
            team = row.get("recent_team", "?")
            vorp = row.get("vorp", 0)
            pts = row.get("projected_season_points", 0)
            lines.append(
                f"{i}. **{name}** ({pos}, {team}) — {pts:.1f} pts, VORP {vorp:.1f}"
            )
        lines.append("")

    lines.append("---")
    lines.append(
        f"*Rankings generated by NFL Data Engineering v4.1 projection models.*"
    )

    return "\n".join(lines)


def generate_matchup_content(
    teams: str, season: int, week: int, scoring: str = "half_ppr"
) -> str:
    """Generate matchup deep-dive content."""
    parts = [t.strip().upper() for t in teams.split("vs")]
    if len(parts) != 2:
        return f"# Error: Expected 'TEAM1 vs TEAM2', got '{teams}'"

    team1, team2 = parts
    proj = _load_projections(season, scoring)

    lines = [
        f"# Matchup Deep Dive: {team1} vs {team2}",
        f"## Season {season}, Week {week}",
        f"*Generated {datetime.now().strftime('%B %d, %Y')}*",
        "",
        "---",
        "",
    ]

    for team, label in [(team1, "Team 1"), (team2, "Team 2")]:
        team_players = proj[proj["recent_team"] == team].sort_values(
            "projected_season_points", ascending=False
        )
        lines.append(f"## {team} Offensive Weapons")
        lines.append("")
        if team_players.empty:
            lines.append(f"*No projection data found for {team}*")
        else:
            for _, row in team_players.head(10).iterrows():
                name = row.get("player_name", "Unknown")
                pos = row.get("position", "?")
                pts = row.get("projected_season_points", 0)
                lines.append(f"- **{name}** ({pos}): {pts:.1f} projected pts")
        lines.append("")

    lines.extend([
        "## Matchup Analysis",
        "",
        f"Look for key positional advantages in the {team1} vs {team2} matchup.",
        "Pay attention to offensive line health and cornerback matchups.",
        "",
        "---",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate NFL content for NotebookLM"
    )
    parser.add_argument(
        "--type",
        choices=["weekly", "rankings", "matchup"],
        required=True,
        help="Content type to generate",
    )
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int, default=1)
    parser.add_argument("--scoring", default="half_ppr")
    parser.add_argument("--teams", type=str, help="For matchup type: 'KC vs BUF'")
    parser.add_argument(
        "--output", type=str, help="Output file path (default: auto-generated)"
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.type == "weekly":
        content = generate_weekly_content(args.season, args.week, args.scoring)
        default_name = f"weekly_w{args.week}_{args.season}.md"
    elif args.type == "rankings":
        content = generate_rankings_content(args.season, args.scoring)
        default_name = f"rankings_{args.season}_{args.scoring}.md"
    elif args.type == "matchup":
        if not args.teams:
            print("ERROR: --teams required for matchup type (e.g., --teams 'KC vs BUF')")
            return 1
        content = generate_matchup_content(
            args.teams, args.season, args.week, args.scoring
        )
        safe_teams = args.teams.replace(" ", "_").replace("vs", "v")
        default_name = f"matchup_{safe_teams}_w{args.week}.md"
    else:
        return 1

    outpath = args.output or os.path.join(OUTPUT_DIR, default_name)
    os.makedirs(os.path.dirname(outpath), exist_ok=True)

    with open(outpath, "w") as f:
        f.write(content)

    print(f"Content generated: {outpath}")
    print(f"  Type: {args.type}")
    print(f"  Length: {len(content)} chars, {content.count(chr(10))} lines")
    print(f"\nNext steps:")
    print(f"  1. Upload to https://notebooklm.google.com")
    print(f"  2. Generate Audio Overview for podcast content")
    print(f"  3. Download MP3 → web/frontend/public/podcasts/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
