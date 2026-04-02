# Phase 48: Kicker Fantasy Projection System — Summary

## Delivered

Built a complete kicker (K) fantasy projection system that extracts kicker stats from PBP data, computes team/opponent opportunity features, and generates weekly kicker projections with game-script, venue/weather, and opponent-defense adjustments.

## New Files

| File | Purpose |
|------|---------|
| `src/kicker_analytics.py` | PBP stat extraction (FG/XP by distance bucket), team RZ stall rate, opponent RZ defense features |
| `src/kicker_projection.py` | Weekly kicker projection engine with game-script, venue/weather, opponent multipliers |
| `tests/test_kicker_projections.py` | 44 tests covering all kicker functionality |

## Modified Files

| File | Change |
|------|--------|
| `src/config.py` | Added `FANTASY_POSITIONS_WITH_K`, `KICKER_SCORING_SETTINGS` |
| `src/scoring_calculator.py` | Added kicker stat keys (fg_made, xp_made, fg_missed, etc.) to scoring map |
| `src/projection_engine.py` | Added `K` to `_FLOOR_CEILING_MULT` (0.40 variance) |
| `src/draft_optimizer.py` | Added `K: 13` to `REPLACEMENT_RANKS` for VORP calculation |
| `scripts/generate_projections.py` | Added `--include-kickers` flag for opt-in kicker projections |

## Projection Model

**Base projection** = team FG attempts/game x kicker FG accuracy x points/FG + XP projection

**Multipliers applied:**
- Game script: close games (|spread| < 7) = 1.10x, blowouts (|spread| > 14) = 0.85x
- Opponent RZ defense: stingy (< avg) = 1.10x, generous (> avg+10%) = 0.90x
- Venue: dome = 1.05x, high altitude (Denver) = 1.05x, high wind (>15mph) = 0.90x

**Kicker scoring:** FG made = 3 pts, FG 50+ = 5 pts, XP = 1 pt, FG/XP miss = -1 pt

**Floor/ceiling:** +/- 40% of projected points (kickers have high variance)

## CLI Usage

```bash
# Weekly projections with kickers
python scripts/generate_projections.py --week 5 --season 2024 --scoring half_ppr --include-kickers
```

## Test Results

- 44 new kicker tests: all passing
- 841 total tests: all passing (0 regressions)
- Opt-in design: `--include-kickers` flag means no impact on existing outputs

## Design Decisions

1. **Separate module** (`kicker_projection.py`) rather than modifying `projection_engine.py` — kickers use fundamentally different data (PBP field goals) vs. skill positions (player weekly stats)
2. **Opt-in CLI flag** — kickers are not included by default to preserve backward compatibility with existing workflows
3. **Rolling 3-week averages** with shift(1) — same lookback philosophy as the main projection engine
4. **Bye week zeroing** — same pattern as QB/RB/WR/TE (zero all stats, set is_bye_week=True)
