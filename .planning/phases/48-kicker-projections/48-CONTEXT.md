# Phase 48: Kicker Projection Model - Context

**Gathered:** 2026-04-02
**Status:** Active

<domain>
## Phase Boundary

Build a kicker fantasy projection system using graph features. Kicker production is entirely team-dependent: FG attempts come from drives that stall in FG range, and game script (close games = more FGs) drives attempt volume. The game prediction model's spread prediction directly informs kicker projections.

Current system has no kicker projections — this is new functionality.

</domain>

<requirements>
## Requirements

- R-01: Red zone stall rate feature — teams with good offense but poor RZ conversion = kicker gold
- R-02: Opposing defense RZ strength — stingy RZ defenses create more FG attempts for opposing kicker
- R-03: Game script prediction — close games (|predicted_spread| < 7) generate more FG opportunities
- R-04: Kicker accuracy by distance bucket from PBP (< 40, 40-49, 50+)
- R-05: Venue/weather features — dome, altitude, wind from game_context Silver
- R-06: Historical kicker consistency (rolling FG accuracy, XP rate)
- R-07: Integration into projection engine (new position type)
- R-08: Backtest kicker projections against actuals
- R-09: Add kicker to draft optimizer
</requirements>
