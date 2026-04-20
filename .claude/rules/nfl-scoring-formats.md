---
paths:
  - "**/*.py"
---
# NFL Fantasy Scoring Formats

## Three Supported Formats

Defined in `src/config.py::SCORING_CONFIGS` (keys are lowercase: `"ppr"`, `"half_ppr"`, `"standard"`):

| Format    | Reception PPR | Rush/Rec Yard | Rush/Rec TD | Pass TD | Pass Yard | INT   | Fumble Lost |
|-----------|---------------|---------------|-------------|---------|-----------|-------|-------------|
| ppr       | 1.0           | 0.1           | 6.0         | 4.0     | 0.04      | -2.0  | -2.0        |
| half_ppr  | 0.5           | 0.1           | 6.0         | 4.0     | 0.04      | -2.0  | -2.0        |
| standard  | 0.0           | 0.1           | 6.0         | 4.0     | 0.04      | -2.0  | -2.0        |

Other shared rules: 2pt conversion = +2.0 for all formats.

## Scoring Calculator — Never Re-Derive Inline

Use `src/scoring_calculator.py` for all point calculations:

```python
from src.scoring_calculator import calculate_points, calculate_points_vectorized

# Single player dict
pts = calculate_points(stat_dict, scoring_format="half_ppr")

# Vectorized on a DataFrame
df["projected_points"] = calculate_points_vectorized(df, scoring_format="half_ppr")
```

Never compute scoring math inline — always call the calculator so the scoring config is the single source of truth.

## Projected Points Invariants

- `projected_points >= 0` for all skill positions (QB/RB/WR/TE)
- Bye week players: all stats zeroed, `is_bye_week=True` flag set
- Rookies without NFL history: positional fallbacks at 100% (starter) / 40% (backup) / 25% (unknown) of tier baseline

## Roster Formats

Defined in `src/config.py::ROSTER_CONFIGS` (keys: `"standard"`, `"superflex"`, `"2qb"`):

- `standard`: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 DST, 6 BN
- `superflex`: standard + 1 SFLEX slot (QB/RB/WR/TE eligible)
- `2qb`: standard + 1 extra QB slot

## VORP Replacement Ranks

Used by `src/draft_optimizer.py`. Replacement level = Nth player at position × 12 teams:

```python
REPLACEMENT_RANKS = {"QB": 13, "RB": 25, "WR": 30, "TE": 13, "K": 13}
```

VORP = `projected_season_points - replacement_level_points`

## CLI Usage

```bash
python scripts/generate_projections.py --week 1 --season 2026 --scoring half_ppr
python scripts/generate_projections.py --preseason --season 2026 --scoring ppr
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5
```

## Reference

See `src/config.py` for `SCORING_CONFIGS` and `ROSTER_CONFIGS` canonical dicts.
See `src/scoring_calculator.py` for `calculate_points()` and `calculate_points_vectorized()`.
See `src/draft_optimizer.py` for `REPLACEMENT_RANKS` and VORP computation.
