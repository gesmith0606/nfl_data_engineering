#!/usr/bin/env python3
"""
Interactive Fantasy Football Draft Assistant

Runs an interactive CLI draft session with real-time recommendations,
ADP comparisons, and positional scarcity alerts.

Usage:
    python scripts/draft_assistant.py --scoring half_ppr --roster-format standard
    python scripts/draft_assistant.py --scoring ppr --teams 10 --my-pick 5
    python scripts/draft_assistant.py --scoring standard --projections-file output/projections/preseason_2026.csv
"""

import sys
import os
import argparse
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nfl_data_integration import NFLDataFetcher
from projection_engine import generate_preseason_projections
from scoring_calculator import list_scoring_formats
from draft_optimizer import DraftBoard, DraftAdvisor, compute_value_scores
import config

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

DIVIDER = "=" * 70
MINI_DIV = "-" * 70


def _sep():
    print(MINI_DIV)


def _header(text: str):
    print(f"\n{DIVIDER}")
    print(f"  {text}")
    print(DIVIDER)


def _display_players(df: pd.DataFrame, cols: list = None, max_rows: int = 20):
    if df.empty:
        print("  (none)")
        return
    if cols is None:
        possible = ['model_rank', 'player_name', 'position', 'recent_team',
                    'projected_season_points', 'projected_points',
                    'adp_rank', 'adp_diff', 'value_tier', 'vorp']
        cols = [c for c in possible if c in df.columns]
    print(df[cols].head(max_rows).to_string(index=False))


def _print_roster(board: DraftBoard):
    _sep()
    print("MY ROSTER:")
    if not board.my_roster:
        print("  (empty)")
        return
    for i, p in enumerate(board.my_roster, 1):
        pts = p.get('projected_season_points', p.get('projected_points', '?'))
        print(f"  {i:2}. {p.get('position','?'):<3}  {p.get('player_name','Unknown'):<25}  "
              f"{p.get('recent_team','?'):<4}  {pts:.1f} pts")

    needs = board.remaining_needs()
    needs_str = ", ".join(f"{p}×{n}" for p, n in needs.items() if n > 0) or "All starter slots filled"
    print(f"\n  Remaining needs: {needs_str}")


def _print_recommendations(advisor: DraftAdvisor, top_n: int = 8):
    recs, reasoning = advisor.recommend(top_n=top_n)
    _sep()
    print(f"RECOMMENDATIONS: {reasoning}")
    _sep()
    _display_players(recs, max_rows=top_n)


# ---------------------------------------------------------------------------
# Draft session
# ---------------------------------------------------------------------------

def run_draft_session(
    projections: pd.DataFrame,
    scoring_format: str,
    roster_format: str,
    n_teams: int,
    my_pick: int,
    adp_df: pd.DataFrame = None,
):
    """Run the interactive draft CLI loop."""

    # Compute value scores (adds model_rank, adp_diff, value_tier, vorp)
    enriched = compute_value_scores(projections, adp_df)

    board = DraftBoard(enriched, roster_format=roster_format, n_teams=n_teams)
    advisor = DraftAdvisor(board, scoring_format=scoring_format)

    _header(f"FANTASY DRAFT ASSISTANT  |  {scoring_format.upper()}  |  {n_teams}-Team  |  Pick #{my_pick}")

    print(f"\nTotal players in pool: {len(board.available):,}")
    print("Position breakdown:")
    _display_players(advisor.position_breakdown())

    pick_number = 0
    round_number = 1

    HELP_TEXT = """
Commands:
  draft <name>       - Mark another team as drafting this player
  pick <name>        - YOU draft this player
  best [pos]         - Show best available (optionally by position: QB/RB/WR/TE)
  rec                - Show recommendations for your next pick
  roster             - Show your current roster
  undervalued        - Show model's undervalued players
  overvalued         - Show ADP-overvalued players
  positions          - Position availability breakdown
  top [N]            - Show top-N available players (default 20)
  search <name>      - Search for a specific player
  undo               - Undo last pick (your pick only)
  skip               - Skip a round (another team picks, no input needed)
  quit / q           - Exit draft
  help / h           - Show this help
"""

    print(HELP_TEXT)

    my_roster_history = []  # for undo

    while True:
        pick_number += 1
        if pick_number > 1 and (pick_number - 1) % n_teams == 0:
            round_number += 1

        # Determine if this is my pick (snake draft)
        if round_number % 2 == 1:
            pick_in_round = (pick_number - 1) % n_teams + 1
            is_my_turn = (pick_in_round == my_pick)
        else:
            pick_in_round = n_teams - (pick_number - 1) % n_teams
            is_my_turn = (pick_in_round == my_pick)

        prompt_label = "YOUR PICK" if is_my_turn else f"Pick #{pick_number} (Round {round_number})"

        if is_my_turn:
            _print_recommendations(advisor, top_n=8)
            print(f"\n>>> {prompt_label} <<<")

        try:
            raw = input(f"\n[Rd {round_number} | Pick {pick_number}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDraft ended.")
            break

        if not raw:
            continue

        parts = raw.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # --- Commands ---
        if cmd in ('quit', 'q', 'exit'):
            print("\nDraft session ended.")
            break

        elif cmd in ('help', 'h', '?'):
            print(HELP_TEXT)

        elif cmd == 'draft':
            if not arg:
                print("Usage: draft <player name>")
                pick_number -= 1
                continue
            player = board.draft_by_name(arg, by_me=False)
            if player:
                print(f"  Drafted by another team: {player.get('player_name', arg)}"
                      f" ({player.get('position','?')}, {player.get('recent_team','?')})")
            else:
                print(f"  Player not found: '{arg}'")
                pick_number -= 1

        elif cmd == 'pick':
            if not arg:
                print("Usage: pick <player name>")
                pick_number -= 1
                continue
            player = board.draft_by_name(arg, by_me=True)
            if player:
                my_roster_history.append(player)
                pts = player.get('projected_season_points', player.get('projected_points', '?'))
                print(f"  YOU picked: {player.get('player_name', arg)}"
                      f" ({player.get('position','?')}, {player.get('recent_team','?')}) — {pts:.1f} pts")
                _print_roster(board)
            else:
                print(f"  Player not found: '{arg}'")
                pick_number -= 1

        elif cmd == 'best':
            positions = [arg.upper()] if arg else None
            bests = advisor.best_available(positions=positions, top_n=15)
            _sep()
            print(f"BEST AVAILABLE" + (f" — {arg.upper()}" if arg else ""))
            _display_players(bests, max_rows=15)
            pick_number -= 1

        elif cmd == 'rec':
            _print_recommendations(advisor, top_n=8)
            pick_number -= 1

        elif cmd == 'roster':
            _print_roster(board)
            pick_number -= 1

        elif cmd == 'undervalued':
            under = advisor.undervalued_players(top_n=10)
            _sep()
            print("UNDERVALUED (model rank >> ADP rank):")
            _display_players(under, max_rows=10)
            pick_number -= 1

        elif cmd == 'overvalued':
            over = advisor.overvalued_players(top_n=10)
            _sep()
            print("OVERVALUED (ADP rank >> model rank):")
            _display_players(over, max_rows=10)
            pick_number -= 1

        elif cmd == 'positions':
            print(advisor.position_breakdown().to_string(index=False))
            pick_number -= 1

        elif cmd == 'top':
            n = int(arg) if arg.isdigit() else 20
            top = advisor.best_available(top_n=n)
            _sep()
            print(f"TOP {n} AVAILABLE:")
            _display_players(top, max_rows=n)
            pick_number -= 1

        elif cmd == 'search':
            if not arg:
                print("Usage: search <name>")
                pick_number -= 1
                continue
            if 'player_name' in board.available.columns:
                mask = board.available['player_name'].str.lower().str.contains(arg.lower(), na=False)
                results = board.available[mask]
                _display_players(results, max_rows=10)
            pick_number -= 1

        elif cmd == 'undo':
            if my_roster_history:
                last = my_roster_history.pop()
                board.my_roster.remove(last)
                board.available = pd.concat(
                    [board.available, pd.DataFrame([last])], ignore_index=True
                ).sort_values('model_rank')
                print(f"  Undone: {last.get('player_name', '?')}")
                pick_number -= 2
            else:
                print("  Nothing to undo.")
                pick_number -= 1

        elif cmd == 'skip':
            print(f"  (skipped pick {pick_number})")

        else:
            print(f"  Unknown command: '{cmd}'. Type 'help' for options.")
            pick_number -= 1

    # Final roster summary
    _header("FINAL ROSTER")
    _print_roster(board)
    print("\nGood luck this season!\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_dotenv()

    formats = list_scoring_formats()
    roster_options = list(config.ROSTER_CONFIGS.keys())

    parser = argparse.ArgumentParser(description='Fantasy Football Draft Assistant')
    parser.add_argument('--scoring', choices=formats, default='half_ppr',
                        help='Scoring format (default: half_ppr)')
    parser.add_argument('--roster-format', choices=roster_options, default='standard',
                        help='Roster format (default: standard)')
    parser.add_argument('--teams', type=int, default=12, help='Number of teams (default: 12)')
    parser.add_argument('--my-pick', type=int, default=1, help='Your draft position (default: 1)')
    parser.add_argument('--season', type=int, default=2026, help='Target season (default: 2026)')
    parser.add_argument('--projections-file', type=str,
                        help='Path to a preseason projections CSV file (skips fetching)')
    parser.add_argument('--adp-file', type=str,
                        help='Path to ADP CSV with player_name and adp_rank columns')
    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Load or generate projections
    # -----------------------------------------------------------------------
    if args.projections_file and os.path.exists(args.projections_file):
        print(f"Loading projections from: {args.projections_file}")
        projections = pd.read_csv(args.projections_file)
    else:
        print(f"Generating pre-season projections for {args.season}...")
        fetcher = NFLDataFetcher()
        past_seasons = [args.season - 2, args.season - 1]
        try:
            seasonal_df = fetcher.fetch_player_seasonal(past_seasons)
        except Exception as e:
            print(f"ERROR: Could not fetch player data: {e}")
            print("Tip: Run 'python scripts/generate_projections.py --preseason --season 2026' first")
            return 1

        projections = generate_preseason_projections(
            seasonal_df,
            scoring_format=args.scoring,
            target_season=args.season,
        )

    if projections.empty:
        print("ERROR: No projection data available.")
        return 1

    # -----------------------------------------------------------------------
    # Load ADP data (optional)
    # -----------------------------------------------------------------------
    adp_df = None
    if args.adp_file and os.path.exists(args.adp_file):
        print(f"Loading ADP data from: {args.adp_file}")
        adp_df = pd.read_csv(args.adp_file)

    # -----------------------------------------------------------------------
    # Run draft session
    # -----------------------------------------------------------------------
    run_draft_session(
        projections=projections,
        scoring_format=args.scoring,
        roster_format=args.roster_format,
        n_teams=args.teams,
        my_pick=args.my_pick,
        adp_df=adp_df,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
