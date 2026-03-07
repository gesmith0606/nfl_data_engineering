#!/usr/bin/env python3
"""
Interactive Fantasy Football Draft Assistant

Runs an interactive CLI draft session with real-time recommendations,
ADP comparisons, and positional scarcity alerts.

Usage:
    python scripts/draft_assistant.py --scoring half_ppr --roster-format standard
    python scripts/draft_assistant.py --scoring ppr --teams 10 --my-pick 5
    python scripts/draft_assistant.py --scoring standard --projections-file output/projections/preseason_2026.csv

    # Mock draft simulation (non-interactive)
    python scripts/draft_assistant.py --simulate --my-pick 3 --teams 12

    # Auction draft mode
    python scripts/draft_assistant.py --auction --budget 200 --teams 12

    # Waiver wire lookups using a pre-existing rostered players file
    python scripts/draft_assistant.py --rostered-file rostered.csv
"""

import sys
import os
import argparse
import json
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from nfl_data_integration import NFLDataFetcher
from projection_engine import generate_preseason_projections
from scoring_calculator import list_scoring_formats
from draft_optimizer import (
    DraftBoard,
    DraftAdvisor,
    AuctionDraftBoard,
    MockDraftSimulator,
    compute_value_scores,
)
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
        possible = [
            'model_rank', 'player_name', 'position', 'recent_team',
            'projected_season_points', 'projected_points',
            'adp_rank', 'adp_diff', 'value_tier', 'vorp',
        ]
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
        print(
            f"  {i:2}. {p.get('position','?'):<3}  {p.get('player_name','Unknown'):<25}  "
            f"{p.get('recent_team','?'):<4}  {pts:.1f} pts"
        )

    needs = board.remaining_needs()
    needs_str = ", ".join(f"{p}x{n}" for p, n in needs.items() if n > 0) or "All starter slots filled"
    print(f"\n  Remaining needs: {needs_str}")


def _print_auction_roster(board: "AuctionDraftBoard"):
    """Print roster with auction costs alongside projected points."""
    _sep()
    print("MY ROSTER (auction):")
    if not board.my_roster:
        print("  (empty)")
        return
    total_cost = 0
    for i, p in enumerate(board.my_roster, 1):
        pts = p.get('projected_season_points', p.get('projected_points', '?'))
        name = p.get('player_name', 'Unknown')
        cost = board.player_costs.get(name, '?')
        cost_str = f"${cost}" if isinstance(cost, int) else cost
        total_cost += cost if isinstance(cost, int) else 0
        print(
            f"  {i:2}. {p.get('position','?'):<3}  {name:<25}  "
            f"{p.get('recent_team','?'):<4}  {pts:.1f} pts  {cost_str}"
        )
    print(f"\n  Total spent: ${total_cost}")

    needs = board.remaining_needs()
    needs_str = (
        ", ".join(f"{p}x{n}" for p, n in needs.items() if n > 0)
        or "All starter slots filled"
    )
    print(f"  Remaining needs: {needs_str}")


def _print_recommendations(advisor: DraftAdvisor, top_n: int = 8):
    recs, reasoning = advisor.recommend(top_n=top_n)
    _sep()
    print(f"RECOMMENDATIONS: {reasoning}")
    _sep()
    _display_players(recs, max_rows=top_n)


# ---------------------------------------------------------------------------
# Rostered-player file loader
# ---------------------------------------------------------------------------

def _load_rostered_file(path: str) -> list:
    """
    Load a list of rostered player names from a CSV or JSON file.

    CSV: one player name per line (no header required; first column used if header present).
    JSON: flat list of strings, e.g. ["Patrick Mahomes", "Justin Jefferson"].

    Args:
        path: Absolute or relative path to the file.

    Returns:
        List of player name strings. Empty list if loading fails.
    """
    if not os.path.exists(path):
        print(f"WARNING: --rostered-file '{path}' not found; waiver list will be empty.")
        return []

    try:
        if path.lower().endswith('.json'):
            with open(path, 'r') as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                print("WARNING: rostered JSON file must be a flat list of strings.")
                return []
            return [str(item) for item in data]

        # Default: CSV / plain text
        df = pd.read_csv(path, header=None)
        return df.iloc[:, 0].dropna().astype(str).tolist()

    except Exception as exc:
        print(f"WARNING: Could not load rostered file '{path}': {exc}")
        return []


# ---------------------------------------------------------------------------
# Simulation mode
# ---------------------------------------------------------------------------

def run_simulation(
    projections: pd.DataFrame,
    scoring_format: str,
    roster_format: str,
    n_teams: int,
    my_pick: int,
    adp_df: pd.DataFrame = None,
    randomness: int = 3,
):
    """
    Run a non-interactive mock draft simulation and print a full summary.

    Args:
        projections:    Pre-season projection DataFrame.
        scoring_format: Scoring format string.
        roster_format:  Roster configuration key.
        n_teams:        Number of teams in the league.
        my_pick:        User's draft position (1-based).
        adp_df:         Optional ADP DataFrame.
        randomness:     Max random offset for opponent picks (default 3).
    """
    enriched = compute_value_scores(projections, adp_df)
    board = DraftBoard(enriched, roster_format=roster_format, n_teams=n_teams)
    advisor = DraftAdvisor(board, scoring_format=scoring_format)
    simulator = MockDraftSimulator(board, user_pick=my_pick, n_teams=n_teams, randomness=randomness)

    _header(
        f"MOCK DRAFT SIMULATION  |  {scoring_format.upper()}  |  {n_teams}-Team  |  "
        f"Pick #{my_pick}  |  Randomness={randomness}"
    )
    print(f"  Players in pool: {len(board.available):,}\n")

    results = simulator.run_full_simulation(advisor)

    # Print each pick
    print(f"{'RD':<4} {'PK':<4} {'TEAM':<6} {'PLAYER':<26} {'POS':<4} {'ADP'}")
    _sep()
    for entry in results['picks']:
        adp_display = str(entry['adp']) if entry['adp'] != 'N/A' else 'N/A'
        print(
            f"  {entry['round']:<3} {entry['pick']:<4} {entry['team']:<6} "
            f"{entry['player_name']:<26} {entry['position']:<4} {adp_display}"
        )

    # Final summary
    _header("SIMULATION RESULTS")
    print(f"  Your roster ({len(results['my_roster'])} players):")
    pts_col = 'projected_season_points'
    for i, p in enumerate(results['my_roster'], 1):
        pts = p.get(pts_col, p.get('projected_points', '?'))
        pts_str = f"{pts:.1f}" if isinstance(pts, float) else str(pts)
        print(
            f"    {i:2}. {p.get('position','?'):<3}  {p.get('player_name','Unknown'):<25}  "
            f"{p.get('recent_team','?'):<4}  {pts_str} pts  "
            f"VORP: {p.get('vorp', 0.0):.1f}"
        )

    print()
    print(f"  Total Projected Points : {results['total_pts']:.1f}")
    print(f"  Total VORP             : {results['total_vorp']:.1f}")
    print(f"  Expected VORP (ADP opt): {results['expected_vorp']:.1f}")
    print(f"  Draft Grade            : {results['draft_grade']}")
    print()


# ---------------------------------------------------------------------------
# Auction draft session
# ---------------------------------------------------------------------------

def run_auction_session(
    projections: pd.DataFrame,
    scoring_format: str,
    roster_format: str,
    n_teams: int,
    budget: int,
    adp_df: pd.DataFrame = None,
    rostered_players: list = None,
):
    """
    Run an interactive auction draft CLI session.

    Supports nomination, bid recording, value analysis, and budget tracking.

    Args:
        projections:     Pre-season projection DataFrame.
        scoring_format:  Scoring format string.
        roster_format:   Roster configuration key.
        n_teams:         Number of teams in the league.
        budget:          Starting auction budget per team (default 200).
        adp_df:          Optional ADP DataFrame.
        rostered_players: Pre-loaded list of rostered player names for waiver lookups.
    """
    enriched = compute_value_scores(projections, adp_df)
    board = AuctionDraftBoard(
        enriched, roster_format=roster_format, n_teams=n_teams, budget_per_team=budget
    )
    advisor = DraftAdvisor(board, scoring_format=scoring_format)

    _header(
        f"AUCTION DRAFT ASSISTANT  |  {scoring_format.upper()}  |  "
        f"{n_teams}-Team  |  Budget: ${budget}"
    )
    print(f"  Players in pool: {len(board.available):,}")
    print("  Position breakdown:")
    _display_players(advisor.position_breakdown())

    AUCTION_HELP = """
Auction Commands:
  nominate <name>          - Surface player stats, projections, and suggested bid
  bid <name> <amount>      - Record that YOU won this player at this cost
  sold <name> <amount>     - Record that an OPPONENT won this player
  budget                   - Show remaining budget and spending summary
  value <name> <amount>    - Show value analysis at a given price
  roster                   - Show your roster with costs paid

Standard Commands:
  best [pos]               - Show best available (optionally by position)
  rec                      - Show recommendations for your next pick
  top [N]                  - Show top-N available players (default 20)
  search <name>            - Search for a specific player
  waiver [pos]             - Show top 10 waiver wire targets (optionally by position)
  undervalued              - Show model's undervalued players
  overvalued               - Show ADP-overvalued players
  positions                - Position availability breakdown
  quit / q                 - Exit draft
  help / h                 - Show this help
"""
    print(AUCTION_HELP)

    while True:
        summary = board.budget_summary()
        prompt_prefix = (
            f"[Budget: ${summary['budget_remaining']} | Spots: {summary['spots_remaining']} left]"
        )

        try:
            raw = input(f"\n{prompt_prefix} > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAuction session ended.")
            break

        if not raw:
            continue

        parts = raw.split(None, 2)
        cmd = parts[0].lower()
        arg1 = parts[1].strip() if len(parts) > 1 else ""
        arg2 = parts[2].strip() if len(parts) > 2 else ""

        if cmd in ('quit', 'q', 'exit'):
            print("\nAuction session ended.")
            break

        elif cmd in ('help', 'h', '?'):
            print(AUCTION_HELP)

        elif cmd == 'nominate':
            if not arg1:
                print("Usage: nominate <player name>")
                continue
            player = board.nominate_player(arg1)
            if player is None:
                print(f"  Player not found: '{arg1}'")
                continue
            pts_col = (
                'projected_season_points'
                if 'projected_season_points' in player.index
                else 'projected_points'
            )
            projected = float(player.get(pts_col, 0) or 0)
            fair_cost = projected / board._league_avg_pts_per_dollar if board._league_avg_pts_per_dollar > 0 else 0
            _sep()
            print(f"  NOMINATION: {player.get('player_name', arg1)}")
            print(f"  Position  : {player.get('position', '?')}")
            print(f"  Team      : {player.get('recent_team', '?')}")
            print(f"  Proj. Pts : {projected:.1f}")
            print(f"  VORP      : {float(player.get('vorp', 0) or 0):.1f}")
            adp = player.get('adp_rank', 'N/A')
            print(f"  ADP Rank  : {adp}")
            print(f"  Suggested bid (fair value): ${fair_cost:.0f}")

        elif cmd == 'bid':
            # bid <name> <amount>  — combined name+amount parsing
            # Allow multi-word names: last token is the dollar amount
            combined = (arg1 + " " + arg2).strip()
            tokens = combined.split()
            if len(tokens) < 2 or not tokens[-1].lstrip('$').isdigit():
                print("Usage: bid <player name> <amount>")
                continue
            cost = int(tokens[-1].lstrip('$'))
            player_name_query = " ".join(tokens[:-1])

            value_info = board.value_vs_cost(player_name_query, cost)
            player = board.win_bid(player_name_query, cost, by_me=True)
            if not player:
                print(f"  Player not found: '{player_name_query}'")
                continue

            resolved = player.get('player_name', player_name_query)
            pts = player.get('projected_season_points', player.get('projected_points', '?'))
            pts_str = f"{pts:.1f}" if isinstance(pts, float) else str(pts)
            print(
                f"  YOU won: {resolved} ({player.get('position','?')}, "
                f"{player.get('recent_team','?')}) for ${cost}  — {pts_str} proj. pts"
            )

            if value_info.get('is_overpay'):
                overpay_pct = value_info.get('overpay_pct', 0)
                fair = value_info.get('fair_value_cost', 0)
                print(
                    f"  WARNING: Possible overpay — fair value ~${fair:.0f}, "
                    f"you paid {overpay_pct:.0f}% above fair value"
                )

            remaining = board.my_budget_remaining
            new_summary = board.budget_summary()
            print(
                f"  Budget remaining: ${remaining}  |  "
                f"${new_summary['implied_per_spot']:.0f}/remaining spot"
            )

        elif cmd == 'sold':
            # sold <name> <amount>
            combined = (arg1 + " " + arg2).strip()
            tokens = combined.split()
            if len(tokens) < 2 or not tokens[-1].lstrip('$').isdigit():
                print("Usage: sold <player name> <amount>")
                continue
            cost = int(tokens[-1].lstrip('$'))
            player_name_query = " ".join(tokens[:-1])
            player = board.win_bid(player_name_query, cost, by_me=False)
            if not player:
                print(f"  Player not found: '{player_name_query}'")
            else:
                print(
                    f"  Opponent won: {player.get('player_name', player_name_query)} "
                    f"({player.get('position','?')}) for ${cost}"
                )

        elif cmd == 'budget':
            summ = board.budget_summary()
            _sep()
            print(f"  Budget Total        : ${summ['budget_total']}")
            print(f"  Budget Spent        : ${summ['budget_spent']}")
            print(f"  Budget Remaining    : ${summ['budget_remaining']}")
            print(f"  Roster Spots Filled : {summ['roster_spots_filled']} / {summ['roster_spots_total']}")
            print(f"  Spots Remaining     : {summ['spots_remaining']}")
            print(f"  Implied $/Spot      : ${summ['implied_per_spot']:.2f}")

        elif cmd == 'value':
            combined = (arg1 + " " + arg2).strip()
            tokens = combined.split()
            if len(tokens) < 2 or not tokens[-1].lstrip('$').isdigit():
                print("Usage: value <player name> <amount>")
                continue
            cost = int(tokens[-1].lstrip('$'))
            player_name_query = " ".join(tokens[:-1])
            info = board.value_vs_cost(player_name_query, cost)
            if not info:
                print(f"  Player not found: '{player_name_query}'")
            else:
                _sep()
                print(f"  VALUE ANALYSIS: {info['player_name']} at ${cost}")
                print(f"  Projected Pts    : {info['projected_pts']:.1f}")
                print(f"  Pts per Dollar   : {info['pts_per_dollar']:.2f}")
                print(f"  Fair Value Cost  : ${info['fair_value_cost']:.0f}")
                overpay_label = "OVERPAY" if info['is_overpay'] else "Good value"
                print(f"  Assessment       : {overpay_label} ({info['overpay_pct']:+.1f}% vs fair value)")

        elif cmd == 'roster':
            _print_auction_roster(board)

        elif cmd == 'best':
            positions = [arg1.upper()] if arg1 else None
            bests = advisor.best_available(positions=positions, top_n=15)
            _sep()
            print("BEST AVAILABLE" + (f" - {arg1.upper()}" if arg1 else ""))
            _display_players(bests, max_rows=15)

        elif cmd == 'rec':
            _print_recommendations(advisor, top_n=8)

        elif cmd == 'top':
            n = int(arg1) if arg1.isdigit() else 20
            top = advisor.best_available(top_n=n)
            _sep()
            print(f"TOP {n} AVAILABLE:")
            _display_players(top, max_rows=n)

        elif cmd == 'search':
            if not arg1:
                print("Usage: search <name>")
                continue
            query = (arg1 + " " + arg2).strip() if arg2 else arg1
            if 'player_name' in board.available.columns:
                mask = board.available['player_name'].str.lower().str.contains(
                    query.lower(), na=False
                )
                results = board.available[mask]
                _display_players(results, max_rows=10)

        elif cmd == 'waiver':
            pos_filter = arg1.upper() if arg1 else None
            waiver_recs = advisor.waiver_recommendations(
                rostered_players=rostered_players, position=pos_filter, top_n=10
            )
            _sep()
            title = "WAIVER WIRE" + (f" - {pos_filter}" if pos_filter else "")
            print(title)
            _display_players(waiver_recs, max_rows=10)

        elif cmd == 'undervalued':
            under = advisor.undervalued_players(top_n=10)
            _sep()
            print("UNDERVALUED (model rank >> ADP rank):")
            _display_players(under, max_rows=10)

        elif cmd == 'overvalued':
            over = advisor.overvalued_players(top_n=10)
            _sep()
            print("OVERVALUED (ADP rank >> model rank):")
            _display_players(over, max_rows=10)

        elif cmd == 'positions':
            print(advisor.position_breakdown().to_string(index=False))

        else:
            print(f"  Unknown command: '{cmd}'. Type 'help' for options.")

    # Final summary
    _header("FINAL AUCTION ROSTER")
    _print_auction_roster(board)
    print("\nGood luck this season!\n")


# ---------------------------------------------------------------------------
# Snake draft session (interactive)
# ---------------------------------------------------------------------------

def run_draft_session(
    projections: pd.DataFrame,
    scoring_format: str,
    roster_format: str,
    n_teams: int,
    my_pick: int,
    adp_df: pd.DataFrame = None,
    rostered_players: list = None,
):
    """
    Run the interactive snake-draft CLI loop.

    Args:
        projections:     Pre-season projection DataFrame.
        scoring_format:  Scoring format string.
        roster_format:   Roster configuration key.
        n_teams:         Number of teams in the league.
        my_pick:         User's draft position (1-based).
        adp_df:          Optional ADP DataFrame.
        rostered_players: Pre-loaded list of rostered player names for waiver lookups.
    """
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
  waiver [pos]       - Show top 10 waiver wire targets (optionally by position)
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
                print(
                    f"  Drafted by another team: {player.get('player_name', arg)}"
                    f" ({player.get('position','?')}, {player.get('recent_team','?')})"
                )
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
                print(
                    f"  YOU picked: {player.get('player_name', arg)}"
                    f" ({player.get('position','?')}, {player.get('recent_team','?')}) - {pts:.1f} pts"
                )
                _print_roster(board)
            else:
                print(f"  Player not found: '{arg}'")
                pick_number -= 1

        elif cmd == 'best':
            positions = [arg.upper()] if arg else None
            bests = advisor.best_available(positions=positions, top_n=15)
            _sep()
            print("BEST AVAILABLE" + (f" - {arg.upper()}" if arg else ""))
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

        elif cmd == 'waiver':
            pos_filter = arg.upper() if arg else None
            waiver_recs = advisor.waiver_recommendations(
                rostered_players=rostered_players, position=pos_filter, top_n=10
            )
            _sep()
            title = "WAIVER WIRE" + (f" - {pos_filter}" if pos_filter else "")
            print(title)
            _display_players(waiver_recs, max_rows=10)
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

    parser = argparse.ArgumentParser(
        description='Fantasy Football Draft Assistant',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- Core league settings ---
    parser.add_argument(
        '--scoring', choices=formats, default='half_ppr',
        help='Scoring format (default: half_ppr)',
    )
    parser.add_argument(
        '--roster-format', choices=roster_options, default='standard',
        help='Roster format (default: standard)',
    )
    parser.add_argument(
        '--teams', type=int, default=12,
        help='Number of teams in the league (default: 12)',
    )
    parser.add_argument(
        '--my-pick', type=int, default=1,
        help='Your draft position 1-based (default: 1)',
    )
    parser.add_argument(
        '--season', type=int, default=2026,
        help='Target projection season (default: 2026)',
    )
    parser.add_argument(
        '--projections-file', type=str,
        help='Path to a preseason projections CSV file (skips live data fetch)',
    )
    parser.add_argument(
        '--adp-file', type=str,
        help='Path to ADP CSV with player_name and adp_rank columns',
    )

    # --- Mode flags ---
    parser.add_argument(
        '--simulate', action='store_true',
        help=(
            'Run a non-interactive mock draft simulation. '
            'Opponents pick by ADP; advisor picks for you. '
            'Prints every pick, final roster, and a draft grade.'
        ),
    )
    parser.add_argument(
        '--simulate-randomness', type=int, default=3,
        metavar='N',
        help=(
            'Max random ADP-rank offset applied to opponent picks during simulation '
            '(default: 3). Higher values produce more variance.'
        ),
    )
    parser.add_argument(
        '--auction', action='store_true',
        help=(
            'Run in auction draft mode. Supports nominate/bid/sold/value/budget commands. '
            'Requires --budget (default 200).'
        ),
    )
    parser.add_argument(
        '--budget', type=int, default=200,
        help='Starting auction budget per team (default: 200). Only used with --auction.',
    )

    # --- Waiver wire ---
    parser.add_argument(
        '--rostered-file', type=str,
        metavar='PATH',
        help=(
            'Path to a CSV or JSON file listing already-rostered player names. '
            'CSV: one name per line. JSON: flat list of strings. '
            'Used by the "waiver" command to exclude rostered players.'
        ),
    )

    # --- ADP refresh ---
    parser.add_argument(
        '--refresh-adp', action='store_true',
        help='Fetch latest ADP data from Sleeper API before starting the draft session.',
    )

    args = parser.parse_args()

    # Validate mutual exclusivity of mode flags
    if args.simulate and args.auction:
        parser.error("--simulate and --auction cannot be used together.")

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
    # Refresh ADP from Sleeper (optional)
    # -----------------------------------------------------------------------
    if args.refresh_adp:
        print("Refreshing ADP data from Sleeper API...")
        import subprocess
        refresh_script = os.path.join(os.path.dirname(__file__), 'refresh_adp.py')
        result = subprocess.run(
            [sys.executable, refresh_script, '--season', str(args.season)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("ADP refresh complete.")
            if not args.adp_file:
                args.adp_file = os.path.join('data', 'adp_latest.csv')
        else:
            print(f"WARN: ADP refresh failed: {result.stderr[:200]}")

    # -----------------------------------------------------------------------
    # Load ADP data (optional)
    # -----------------------------------------------------------------------
    adp_df = None
    adp_path = args.adp_file
    if not adp_path:
        # Auto-detect latest ADP file
        default_adp = os.path.join('data', 'adp_latest.csv')
        if os.path.exists(default_adp):
            adp_path = default_adp
    if adp_path and os.path.exists(adp_path):
        print(f"Loading ADP data from: {adp_path}")
        adp_df = pd.read_csv(adp_path)

    # -----------------------------------------------------------------------
    # Load rostered players (optional, for waiver wire)
    # -----------------------------------------------------------------------
    rostered_players: list = []
    if args.rostered_file:
        rostered_players = _load_rostered_file(args.rostered_file)
        if rostered_players:
            print(f"Loaded {len(rostered_players)} rostered players from '{args.rostered_file}'")

    # -----------------------------------------------------------------------
    # Dispatch to appropriate mode
    # -----------------------------------------------------------------------
    if args.simulate:
        run_simulation(
            projections=projections,
            scoring_format=args.scoring,
            roster_format=args.roster_format,
            n_teams=args.teams,
            my_pick=args.my_pick,
            adp_df=adp_df,
            randomness=args.simulate_randomness,
        )
    elif args.auction:
        run_auction_session(
            projections=projections,
            scoring_format=args.scoring,
            roster_format=args.roster_format,
            n_teams=args.teams,
            budget=args.budget,
            adp_df=adp_df,
            rostered_players=rostered_players or None,
        )
    else:
        run_draft_session(
            projections=projections,
            scoring_format=args.scoring,
            roster_format=args.roster_format,
            n_teams=args.teams,
            my_pick=args.my_pick,
            adp_df=adp_df,
            rostered_players=rostered_players or None,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
