# Domain Pitfalls: Market Data Integration (v2.1)

**Domain:** Adding historical odds, line movement features, and CLV tracking to existing NFL prediction pipeline
**Researched:** 2026-03-27
**Baseline:** XGB+LGB+CB+Ridge ensemble, 53.0% ATS, +$3.09 profit on sealed 2024 holdout

## Critical Pitfalls

Mistakes that cause incorrect evaluation, data leakage, or false signal.

### Pitfall 1: Closing Line Leakage in Prediction Features
**What goes wrong:** Using closing line movement (closing_spread - opening_spread) as a model feature for live predictions. The closing line is only known at kickoff -- by which time your prediction is already placed.
**Why it happens:** Line movement features clearly correlate with outcomes in backtesting (because closing lines incorporate late information). It looks like "signal" but it is actually future information.
**Consequences:** Backtested model appears much better than it will perform live. False confidence in the model.
**Prevention:** Clearly separate features by temporal availability. `opening_spread` and `opening_total` are pre-game knowable. `spread_shift` and all closing-line-derived features are NOT. For backtesting ablation, document that closing line features are retrospective-only. For live use, only use opening line or mid-week snapshot.
**Detection:** If adding line movement features dramatically improves ATS accuracy (>5%), suspect leakage. Check whether the features use closing line data.

### Pitfall 2: Duplicate Closing Line Sources
**What goes wrong:** Ingesting closing spread/total from an external source alongside the nflverse spread_line/total_line, then treating them as independent data points or having disagreements.
**Why it happens:** External sources may define "closing" differently (e.g., Pinnacle close vs consensus close vs DraftKings close). Minor discrepancies (47.0 vs 47.5) are normal between books.
**Consequences:** Confusion about which is "truth," inconsistent CLV calculations, potential data quality issues.
**Prevention:** Use nflverse spread_line/total_line as the canonical closing line (this is what PBP and schedules already use). Only ingest opening lines from external sources. Cross-validate external closing lines against nflverse as a data quality check, but do not store both.
**Detection:** After ingestion, assert that external closing lines are within 1.0 point of nflverse closing lines for >95% of games.

### Pitfall 3: Team Name Mapping Errors
**What goes wrong:** External odds data uses different team abbreviations (e.g., "JAC" vs "JAX", "LAR" vs "LA", "WSH" vs "WAS") than nflverse, causing join failures.
**Why it happens:** No universal standard for NFL team abbreviations. Relocations (Oakland->Las Vegas, San Diego->LA Chargers, St. Louis->LA Rams, Washington name changes) add confusion.
**Consequences:** Rows silently fail to join; missing market data for some games; NaN features that the model may handle poorly.
**Prevention:** Build an explicit team name mapping dict in the ingestion script. Validate post-join: every game_id in Bronze schedules must have a matching odds row.
**Detection:** Count of joined rows must equal count of games in schedules for that season (+/- playoff games if excluded).

### Pitfall 4: game_id Construction Mismatch
**What goes wrong:** Constructing game_id from external odds data that does not match the nflverse game_id format (YYYY_WW_AWAY_HOME).
**Why it happens:** External data may have different date formats, team order conventions, or not include week numbers.
**Consequences:** Complete join failure between odds and schedules.
**Prevention:** Do not construct game_id independently. Instead, join external odds to nflverse schedules by (season, week, home_team, away_team) to inherit the correct game_id. Or join on (gameday, home_team) which is unique.
**Detection:** After merge, assert zero orphan rows in either direction.

## Moderate Pitfalls

### Pitfall 5: Sign Convention Confusion for Spreads
**What goes wrong:** Opening spread from external source uses opposite sign convention from nflverse (e.g., "-3" means different things in different sources).
**Why it happens:** Some sources express spread from the favorite's perspective, others from the home team's perspective. nflverse uses positive = home team is the underdog (home team getting points).
**Prevention:** Verify sign convention empirically: for games where the home team is clearly favored (e.g., KC at home), check that opening_spread is negative in the external source vs nflverse convention. Normalize to nflverse convention during ingestion.
**Detection:** Compute correlation between external opening spread and nflverse spread_line -- should be >0.95.

### Pitfall 6: Survivorship Bias in Line Movement Features
**What goes wrong:** Only having odds for games that were widely available for betting. International games, some early-season games, or off-market games may have missing or unreliable odds data.
**Why it happens:** Not all games attract equal betting interest. Opening lines for low-profile games may be set later or with wider margins.
**Consequences:** Missing data for some games, potentially biased toward high-profile matchups.
**Prevention:** Fill missing opening lines with closing lines (zero movement) as a conservative fallback. Track the percentage of games with real opening line data per season.
**Detection:** Monitor null rate for opening_spread by season. Flag if >10% of games are missing.

### Pitfall 7: Per-Team Reshape Errors for Symmetric Features
**What goes wrong:** When reshaping game-level market features to per-team-per-week rows, accidentally flipping features that should not flip or not flipping features that should.
**Why it happens:** Some market features are symmetric (spread_move_abs = same for both teams) and some are directional (opening_spread = flip sign for away team).
**Consequences:** Incorrect differential features in the model.
**Prevention:** Explicitly categorize each market feature as symmetric or directional. Write tests that verify: for any game, home_row[opening_spread] = -away_row[opening_spread].
**Detection:** Unit tests on reshape function.

### Pitfall 8: Opening Line as Feature Encodes Vegas Expectations
**What goes wrong:** Using opening_spread as a feature essentially lets the model "peek" at market consensus, which may dominate all other features.
**Why it happens:** The opening line is the market's best estimate of the true spread -- it is extremely informative by design.
**Consequences:** Model becomes a thin wrapper around the opening line rather than learning from team performance data. Feature importance concentrates on opening_spread. Philosophical question: is this a prediction model or a "how much does the market move from open to close" model?
**Prevention:** Run ablation both with and without opening line as a feature. Compare feature importance distributions. If opening_spread dominates (>30% of SHAP importance), it may be worth keeping but documenting that the model's value-add is limited.
**Detection:** SHAP importance report after ablation.

## Minor Pitfalls

### Pitfall 9: CLV Calculation Without No-Vig Adjustment
**What goes wrong:** Computing CLV as raw (model_line - closing_line) without accounting for the vig/juice.
**Why it happens:** Raw CLV is simpler to compute.
**Consequences:** Slightly overstated CLV because the vig creates a range where the "correct" line exists rather than a single point.
**Prevention:** For v2.1, raw CLV is acceptable as a first pass. Document that true CLV should use no-vig closing lines (computed from the odds on each side). Defer no-vig adjustment to v2.2 Betting Framework.
**Detection:** Document the limitation in the CLV output.

### Pitfall 10: Excel Parsing Edge Cases
**What goes wrong:** Historical Excel files from SBR may have inconsistent formatting: merged cells, header rows in unexpected positions, special characters in team names, empty rows between seasons.
**Why it happens:** These are manually maintained spreadsheets, not API outputs.
**Consequences:** Pandas read_excel fails or produces garbage.
**Prevention:** Download and inspect the exact Excel file format before writing the parser. Write defensive parsing with explicit column selection and row filtering. Validate row counts against expected game counts per season (256-272 games per season depending on year).
**Detection:** Assert game counts per season match expected values.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Bronze odds ingestion | Team name mapping (Pitfall 3), game_id matching (Pitfall 4), Excel parsing (Pitfall 10) | Defensive mapping dict, join via schedules, inspect file before coding parser |
| Silver line movement | Sign convention (Pitfall 5), per-team reshape (Pitfall 7) | Empirical sign check, explicit symmetric/directional categorization, unit tests |
| CLV + ablation | Closing line leakage (Pitfall 1), opening line domination (Pitfall 8) | Temporal feature categorization, SHAP importance check, documented limitations |

## Sources

- [CLV methodology](https://oddsjam.com/betting-education/closing-line-value) -- CLV concepts
- [Reverse line movement](https://www.actionnetwork.com/education/reverse-line-movement) -- line movement dynamics
- [Closing line as efficient market](https://vsin.com/how-to-bet/the-importance-of-closing-line-value/) -- why closing lines are strong
- Direct inspection of nflverse schedules data -- verified spread_line sign convention
- Direct inspection of feature_engineering.py -- verified leakage guard patterns
