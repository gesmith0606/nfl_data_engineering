# Draft Prep — 2026-08-18

Pre-season draft-prep refresh for all four leagues ahead of the Sept 7 feetball draft
(keepers due Aug 31). Ran the documented `CLAUDE.md` / `draft-prep` skill commands against
a fresh `git pull --rebase` (already up to date), refreshed ADP, regenerated preseason
projections in both scoring formats the four `LEAGUE_PRESETS` need, and pulled per-league
draft boards via `src.draft_optimizer.compute_value_scores` (the same VORP/ADP-diff engine
`draft_assistant.py` uses) using each league's real roster shape from `src/config.py`.

## What ran

| Step | Command | Result |
|---|---|---|
| Pull | `git pull --rebase` | Already up to date |
| ADP refresh | `scripts/refresh_adp.py --season 2026` | 221 players, source=ffc, half_ppr — saved to `data/adp_latest.csv` |
| Projections (half_ppr) | `scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr` | 1,026 players — `output/projections/preseason_2026_half_ppr_20260818_210359.csv` + Gold parquet |
| Projections (ppr) | `scripts/generate_projections.py --preseason --season 2026 --scoring ppr` | 1,026 players — `output/projections/preseason_2026_ppr_20260818_210407.csv` + Gold parquet |
| Draft boards (all 4 leagues) | `compute_value_scores(projections, adp_df, roster_format, n_teams)` per `LEAGUE_PRESETS` entry | VORP + ADP-diff board per league (below) |
| Simulate mode (all 4 leagues) | `scripts/draft_assistant.py --league <preset> --simulate` | Ran to completion for all four (see **Tool note** below on a late-round artifact) |

**Why two scoring formats:** `la_liga` and `feetball` are half_ppr; `gentlemen` and `mahomos`
are full ppr (`LEAGUE_PRESETS` in `src/config.py`). Generated both so every league's board
uses the right scoring.

**ADP coverage caveat:** `data/adp_latest.csv` (FFC source) only carries 221 ranked players,
so only 191 of the 1,026 projected players in each board have an `adp_rank` — value-gap /
fade tables below are restricted to that matched, realistically-draftable pool
(`adp_rank <= 150`).

## Tool note (report, not fixed — no source changes made)

`draft_assistant.py --simulate` ran cleanly for all four leagues (no errors), but its
late-round pick logic loops on kickers once skill-position value drops below a kicker's flat
~114.7-point baseline — the sim rosters (`YOU`) filled up to *8 kickers* in `la_liga`/`feetball`
(roster only needs 1 K) and, worse, drafted kickers repeatedly in `gentlemen`/`mahomos`, which
are **no-K leagues** (`sleeper_gentlemen`/`sleeper_mahomos` have no K slot in `ROSTER_CONFIGS`).
Because VORP is undefined for an undraftable position, this produced `NaN` team VORP and a
`D` draft grade for both Sleeper leagues — that grade is an artifact of the simulator's
late-round behavior, not a real read on roster quality (both sims actually built solid
RB/WR/TE cores through ~round 10 before the kicker loop kicked in). Recommend not relying on
`--simulate`'s final grade for no-K leagues until that's addressed; the VORP boards below
(computed directly, same engine minus the sim loop) are the trustworthy source for this report.

---

## la_liga (ESPN · half_ppr · 2-FLEX · 12 teams · **you pick #1 overall**)

### Top 15 overall by VORP
| Rk | Player | Pos | Team | Proj Pts | VORP | ADP |
|---|---|---|---|---|---|---|
| 1 | Jahmyr Gibbs | RB | DET | 330.6 | 162.3 | 1 |
| 2 | Bijan Robinson | RB | ATL | 326.6 | 158.3 | 2 |
| 3 | Christian McCaffrey | RB | SF | 314.9 | 146.6 | 7 |
| 4 | Jonathan Taylor | RB | IND | 311.2 | 142.9 | 6 |
| 5 | Ja'Marr Chase | WR | CIN | 301.4 | 139.7 | 4 |
| 6 | Puka Nacua | WR | LA | 298.4 | 136.7 | 3 |
| 7 | James Cook | RB | BUF | 290.3 | 122.0 | — |
| 8 | Derrick Henry | RB | BAL | 280.0 | 111.7 | 10 |
| 9 | De'Von Achane | RB | MIA | 278.8 | 110.5 | 11 |
| 10 | Jaxon Smith-Njigba | WR | SEA | 269.5 | 107.8 | 5 |
| 11 | Ashton Jeanty | RB | LV | 274.0 | 105.7 | 16 |
| 12 | Saquon Barkley | RB | PHI | 274.0 | 105.7 | 18 |
| 13 | Amon-Ra St. Brown | WR | DET | 267.1 | 105.4 | 8 |
| 14 | Trey McBride | TE | ARI | 223.4 | 91.0 | 40 |
| 15 | Omarion Hampton | RB | LAC | 258.1 | 89.8 | 23 |

*James Cook has no ADP match (not in the 221-player FFC pool) — treat his rank as a model call, worth a gut-check against a live ADP source on draft day.*

### Value gaps (our rank beats ADP, VORP > 0, ADP ≤ 150)
QB dominates this list — a known, real market inefficiency in single-QB formats: elite
QBs post huge raw points but the field waits on QB, so ADP pushes them 3-6+ rounds later
than their production justifies:

| Player | Pos | ADP | Model rank | ADP−model | VORP |
|---|---|---|---|---|---|
| Josh Allen | QB | 32 | 1 | +31 | 88.2 |
| Lamar Jackson | QB | 58 | 2 | +56 | 33.8 |
| Jalen Hurts | QB | 80 | 3 | +77 | 26.0 |
| Drake Maye | QB | 52 | 4 | +48 | 25.2 |
| Joe Burrow | QB | 57 | 6 | +51 | 22.7 |
| Jayden Daniels | QB | 73 | 8 | +65 | 16.3 |
| Brock Purdy | QB | 89 | 10 | +79 | 9.1 |
| George Kittle | TE | 119 | 97 | +22 | 53.7 |

### Fades (ADP loves them more than our model, ADP ≤ 150)
| Player | Pos | ADP | Model rank | VORP |
|---|---|---|---|---|
| Rashod Bateman | WR | 134 | 329 | −75.4 |
| Matthew Golden | WR | 110 | 229 | −53.3 |
| Jalen Nailor | WR | 149 | 241 | −56.1 |
| Denzel Boston | WR | 148 | 226 | −52.7 |
| Bhayshul Tuten | RB | 54 | 130 | −11.4 |
| Rome Odunze | WR | 47 | 113 | 8.6 |
| DJ Moore | WR | 50 | 111 | 10.5 |

### Pick #1 overall recommendation
**Jahmyr Gibbs (RB, DET).** Consensus #1 by both our model and market ADP — no debate here,
this is the correct anchor pick regardless of la_liga's 2-FLEX shape (RB is still the
scarcest high-floor position at replacement level).

### Round 2–3 targets (snake turn — picks 24 and 25)
With the 1-slot, your next picks land at #24 and #25 (back-to-back at the turn). Saquon
Barkley (ADP 18) and Omarion Hampton (ADP 23) will likely be gone by pick 24; realistic
best-available window (ADP 18–36) is:

| Player | Pos | ADP | VORP |
|---|---|---|---|
| Saquon Barkley | RB | 18 | 105.7 |
| Omarion Hampton | RB | 23 | 89.8 |
| Josh Jacobs | RB | 27 | 83.5 |
| Kyren Williams | RB | 26 | 65.1 |
| Nico Collins | WR | 21 | 64.1 |
| A.J. Brown | WR | 20 | 61.6 |
| George Pickens | WR | 19 | 59.1 |
| Malik Nabers | WR | 28 | 55.8 |
| Cam Skattebo | RB | 36 | 53.9 |

**Plan:** with 2 FLEX to fill, don't force position — if a top-4 WR (Collins/A.J. Brown/
Pickens/Nabers) is still on the board at 24, take it; if the RB run continues and Jacobs/
Williams slip to 24-25, RB-RB is fine too given how thin the position gets after pick ~30.

---

## feetball (Yahoo · half_ppr · 3-WR/1-FLEX · 10 teams · **keeper league, order set after Aug 31**)

### Top 15 overall by VORP
| Rk | Player | Pos | Team | Proj Pts | VORP | ADP |
|---|---|---|---|---|---|---|
| 1 | Jahmyr Gibbs | RB | DET | 330.6 | 141.5 | 1 |
| 2 | Ja'Marr Chase | WR | CIN | 301.4 | 139.4 | 4 |
| 3 | Bijan Robinson | RB | ATL | 326.6 | 137.5 | 2 |
| 4 | Puka Nacua | WR | LA | 298.4 | 136.4 | 3 |
| 5 | Christian McCaffrey | RB | SF | 314.9 | 125.8 | 7 |
| 6 | Jonathan Taylor | RB | IND | 311.2 | 122.1 | 6 |
| 7 | Jaxon Smith-Njigba | WR | SEA | 269.5 | 107.5 | 5 |
| 8 | Amon-Ra St. Brown | WR | DET | 267.1 | 105.1 | 8 |
| 9 | James Cook | RB | BUF | 290.3 | 101.2 | — |
| 10 | Derrick Henry | RB | BAL | 280.0 | 90.9 | 10 |
| 11 | De'Von Achane | RB | MIA | 278.8 | 89.7 | 11 |
| 12 | CeeDee Lamb | WR | DAL | 247.5 | 85.5 | 13 |
| 13 | Ashton Jeanty | RB | LV | 274.0 | 84.9 | 16 |
| 14 | Saquon Barkley | RB | PHI | 274.0 | 84.9 | 18 |
| 15 | Trey McBride | TE | ARI | 223.4 | 82.4 | 40 |

*3-WR format bumps WR ahead of RB relative to la_liga's 2-FLEX board — Chase/Nacua both jump above McCaffrey/Taylor.*

### Value gaps (VORP > 0, ADP ≤ 150)
Same single-QB "wait on QB" pattern as la_liga (Jaxson Dart, Trevor Lawrence, Brock Purdy,
Jalen Hurts, Caleb Williams, Jayden Daniels, Lamar Jackson, Joe Burrow, Drake Maye, Josh
Allen all beat their ADP by 30-80+ picks with positive VORP), plus **George Kittle (TE,
ADP 119, model rank 97, VORP 45.1)** as the clear non-QB standout.

### Fades (ADP ≤ 150)
Same list as la_liga: Rashod Bateman, Matthew Golden, Jalen Nailor, Denzel Boston, Bhayshul
Tuten — model rates all of these meaningfully worse than the market.

---

## Keeper math (feetball)

**The rule (as given):** keeper round = last year's (2025) draft round the player was
selected in, minus 3. This repo doesn't have your 2025 feetball roster or draft results on
file, so **we can't compute your actual keeper costs — please paste your current roster
plus the round each player went in last year**, and I'll run the real numbers before the
Aug 31 deadline.

**Confirm the "floor round 10" direction with your commissioner before deciding** — it reads
naturally as a lower bound (`keeper_round = max(drafted_round - 3, 10)`, i.e. no keeper ever
costs cheaper than a round-10 pick, which caps how much you can steal a 1st-rounder for) but
league bylaws sometimes use "floor" loosely to mean a cap on the high end instead. Either way,
the generic principle holds regardless of which direction "floor" points:

> **Any player currently priced in the top 3 rounds of this year's ADP (picks 1-30 of feetball's
> 10-team format) who you originally drafted late enough to land in the rounds 4-10 keeper
> band is an outstanding keep** — you'd be paying a mid-round pick for a player who'd otherwise
> cost you a 1st-3rd round pick to redraft.

This year's top-30-ADP talent, ranked by our model (check this against who's actually on your
2025 roster):

| Player | Pos | ADP | VORP |
|---|---|---|---|
| Jahmyr Gibbs | RB | 1 | 141.5 |
| Ja'Marr Chase | WR | 4 | 139.4 |
| Bijan Robinson | RB | 2 | 137.5 |
| Puka Nacua | WR | 3 | 136.4 |
| Christian McCaffrey | RB | 7 | 125.8 |
| Jonathan Taylor | RB | 6 | 122.1 |
| Jaxon Smith-Njigba | WR | 5 | 107.5 |
| Amon-Ra St. Brown | WR | 8 | 105.1 |
| Derrick Henry | RB | 10 | 90.9 |
| De'Von Achane | RB | 11 | 89.7 |
| CeeDee Lamb | WR | 13 | 85.5 |
| Ashton Jeanty | RB | 16 | 84.9 |
| Saquon Barkley | RB | 18 | 84.9 |
| Rashee Rice | WR | 17 | 76.4 |
| Drake London | WR | 12 | 73.4 |
| Omarion Hampton | RB | 23 | 69.0 |
| Nico Collins | WR | 21 | 63.8 |
| Josh Jacobs | RB | 27 | 62.7 |

If any of these was a mid-late-round flier for you last year and broke out, keep them — the
math works overwhelmingly in your favor at any reasonable reading of the rule.

---

## gentlemen (Sleeper · full PPR · 3-FLEX, no K · 12 teams)

### Top 15 overall by VORP
| Rk | Player | Pos | Team | Proj Pts | VORP | ADP |
|---|---|---|---|---|---|---|
| 1 | Jahmyr Gibbs | RB | DET | 364.9 | 196.8 | 1 |
| 2 | Bijan Robinson | RB | ATL | 363.1 | 195.0 | 2 |
| 3 | Christian McCaffrey | RB | SF | 348.3 | 180.2 | 7 |
| 4 | Ja'Marr Chase | WR | CIN | 367.3 | 177.8 | 4 |
| 5 | Puka Nacua | WR | LA | 364.1 | 174.6 | 3 |
| 6 | Jonathan Taylor | RB | IND | 341.4 | 173.3 | 6 |
| 7 | James Cook | RB | BUF | 317.1 | 149.0 | — |
| 8 | De'Von Achane | RB | MIA | 307.0 | 138.9 | 11 |
| 9 | Jaxon Smith-Njigba | WR | SEA | 327.8 | 138.3 | 5 |
| 10 | Amon-Ra St. Brown | WR | DET | 324.2 | 134.7 | 8 |
| 11 | Ashton Jeanty | RB | LV | 297.0 | 128.9 | 16 |
| 12 | Derrick Henry | RB | BAL | 296.8 | 128.7 | 10 |
| 13 | Saquon Barkley | RB | PHI | 293.3 | 125.2 | 18 |
| 14 | Omarion Hampton | RB | LAC | 287.4 | 119.3 | 23 |
| 15 | Trey McBride | TE | ARI | 276.4 | 117.5 | 40 |

### Value gaps (VORP > 0, ADP ≤ 150)
Same QB pattern (Josh Allen, Lamar Jackson, Jalen Hurts, Drake Maye, Joe Burrow, Jayden
Daniels) plus a **strong TE trio** this league's 3-FLEX/no-K shape rewards: **George Kittle**
(ADP 119, model 79, VORP 67.7), **Tucker Kraft** (ADP 97, model 85, VORP 60.5), **Travis
Kelce** (ADP 130, model 115, VORP 38.1).

### Fades (ADP ≤ 150)
Rashod Bateman, Matthew Golden, Jalen Nailor, Denzel Boston, Bhayshul Tuten — same names as
above; consistent across scoring formats.

---

## mahomos (Sleeper · full PPR · 3-FLEX, no K/DST · 12 teams)

Identical roster starters to gentlemen for RB/WR/TE/QB purposes (only the K/DST slots
differ, which don't affect skill-position VORP), so the skill-position board is the same as
gentlemen's above: same top-15 by VORP, same value gaps (QB "wait" pattern + Kittle/Kraft/
Kelce at TE), same fades.

---

## Data files refreshed

- `data/adp_latest.csv` (+ `data/adp/adp_ffc_half_ppr.csv`, `data/adp/adp_ffc_half_ppr_20260818.csv`)
- `data/gold/projections/preseason/season=2026/season_proj_20260818_210359.parquet` (half_ppr)
- `data/gold/projections/preseason/season=2026/season_proj_20260818_210407.parquet` (ppr)
- `output/projections/preseason_2026_half_ppr_20260818_210359.csv`, `output/projections/preseason_2026_ppr_20260818_210407.csv` (local CSV, not committed — gitignored `output/`)

## Open items for the user

1. **feetball keeper math** — need your actual 2025 feetball roster + the round each
   keeper-eligible player was drafted last year to compute real keeper costs before Aug 31.
2. **Confirm "floor round 10" direction** with your feetball commissioner (see Keeper math
   section) — changes which players are the best keeps at the margin.
3. **draft_assistant.py --simulate late-round kicker loop** (see Tool note) — cosmetic for
   this report (worked around by querying the board directly) but worth a look before relying
   on `--simulate`'s draft grade for `gentlemen`/`mahomos` on draft night.
