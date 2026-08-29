# Draft Prep — ESPN "La Liga" (league 1493260), 2026 Season

Generated 2026-08-27. Source of truth for league facts: `data/leagues/espn_la_liga_2026.json`
(live ESPN v3 API pull). Doctrine: `docs/DRAFT_DOCTRINE.md`.

## ⚠️ PICK ORDER IS PROVISIONAL

The league is `is_active: false` — the commissioner can still re-set or re-randomize the draft
order before it goes live. The order used below (`[1,10,7,4,11,13,5,15,12,14,2,16]`, George's
"The Oracle" at **slot 1**) has been stable since 2026-08-04 and is **not** just last year's order
carried over (2025's real order was `1,13,11,5,15,12,7,2,16,14,4,10` — different sequence,
same person happens to sit at 1 in both). So slot 1 is a reasonable working assumption, not a
certainty. **Section 4 below is written as the primary scenario ("if the order holds"). Section 3
(tiers, values, doctrine) is slot-independent and is the part to actually memorize. Section 5 gives
adaptable plans for early/mid/late slots** in case the commissioner reshuffles.

## 1. League facts

| | |
|---|---|
| Platform / league | ESPN, league 1493260, "La Liga" |
| Season | 2026, 12 teams |
| Scoring | Half-PPR (0.5 rec / 0.1 yd / 6 TD / 4 pass TD / 0.04 pass yd / -2 INT,fum) |
| Roster | QB1 / RB2 / WR2 / TE1 / FLEX2 (RB/WR/TE-eligible) / K1 / DST1 / BN7 — **17 rounds** |
| Draft | Snake, 90s/pick, date not yet set |
| My team | "The Oracle" (team_id 1), owner Smithg8929245 |
| My picks (if slot 1 holds) | 1, 24, 25, 48, 49, 72, 73, 96, 97, 120, 121, 144, 145, 168, 169, 192, 193 |
| Playoffs | Top 6 of 12, seeded by **total points scored all season** (not just record) — favors high-weekly-ceiling rosters, not just consistency |
| Waivers | $100 FAAB |
| Config preset | `la_liga` in `src/config.py::LEAGUE_PRESETS`, roster shape `espn_la_liga` |

## 2. Pipeline run (all commands executed, in order)

```
source venv/bin/activate
python scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr
  -> output/projections/preseason_2026_half_ppr_20260827_144926.csv
  -> data/gold/projections/preseason/season=2026/season_proj_half_ppr_20260827_144926.parquet
     (1,028 players; consensus anchor ON by default for all positions)

python scripts/refresh_adp.py --source espn --scoring half_ppr --season 2026 --teams 12
  -> data/adp/adp_espn_half_ppr.csv (400 players; ESPN is the correct source for this room per §0/§11)

python scripts/draft_value_report.py --league la_liga --top 200
  -> full VALUES/BUSTS/BREAKOUTS/DEEP-SLEEPERS report vs ESPN ADP, roster-shape-aware VORP
```

Both artifacts are fresh (generated today, 2026-08-27) and scoped correctly: half_ppr projections,
ESPN ADP (not Sleeper/FFC — doctrine §11 says ESPN rooms take QB/TE 10-20 picks earlier, and that
shows up below: Josh Allen ESPN ADP 19 vs our model's overall #1 raw-points QB).

## 3. SLOT-INDEPENDENT CORE (read this regardless of where the order lands)

### 3a. House rules (non-negotiable, §0)
- Never a 2nd QB while 1 is rostered (no superflex here).
- No K/DST until the final (2 open slots + 1) picks — realistically not before round 15-16.
- Starters first: no RB/WR/TE bench/handcuff while a starter or FLEX slot is open.
- ESPN ADP is the market for this room — never price against Sleeper/FFC ADP here.

### 3b. Roster-construction checkpoints for THIS league (§38-41)
- By round 6: 2 RB / 3 WR rostered. By round 10: 4 RB / 4-5 WR. Finish 5-7 RB / 6-7 WR.
- TE2 never before round 9-10. QB1 in the elite window (round 3-5) or after round 9 — never
  rounds 6-8 (§40; the worst historical cell on the board).
- Rounds 1-3 buy safety; **rounds 6-11 win this league** (RB round 6 hits league-winner 41% of
  the time historically) — spend those picks on upside, not floor vets (§45).
- This league's **total-points playoff seeding** raises the value of ceiling over floor all season,
  not just in the fantasy-playoff stretch — lean slightly toward the higher-ceiling player in any
  near-tie (§43's "signal not law" cuts the same way here).

### 3c. Value / Bust / Breakout / Deep-Sleeper report (vs ESPN ADP, half-PPR, espn_la_liga VORP)

**5 values (§10 — model ≥1 round ahead of ESPN ADP):**
| Player | Pos | ESPN ADP | Model VORP | Rule |
|---|---|---|---|---|
| Josh Jacobs (GB) | RB | 33 | +75.0 | §10 value; **but** §20 RB age-cliff flag (age 28.6) — price the value down |
| Kyren Williams (LA) | RB | 37 | +65.1 | §10 value |
| Cam Skattebo (NYG) | RB | 40 | +54.0 | §10 value + §29 young breakout profile |
| Colston Loveland (CHI) | TE | 41 | +53.6 | §10 value + §30/31 role step-up, age 22 |
| George Kittle (SF) | TE | 82 | +53.5 | §10 value — TE market inefficiency is the single biggest lever on this board |

**5 busts (§20/§27 — age cliff / ADP inflation the model doesn't support):**
| Player | Pos | ESPN ADP | Model VORP | Rule |
|---|---|---|---|---|
| Kenny Gainwell (TB) | RB | 108 | -11.6 | §27 ADP inflation + §20 age 27.5 + faded mid-tier note |
| Rachaad White (WAS) | RB | 129 | -21.9 | §27 + §20 (age 27.6) |
| Isiah Pacheco (DET) | RB | 165 | -56.1 | §27 + §20 (age 27.5) |
| Brian Robinson (ATL) | RB | 170 | -58.0 | §27 + §20 (age 27.4) |
| Jayden Higgins (HOU) | WR | -- | -49.5 | **[NEWS: Inactive]** roster-status flag — do not draft at any price (§36) |

**5 breakouts/sleepers (§29-34 — model likes more than the market, plausible role step-up):**
| Player | Pos | ESPN ADP | Model VORP | Rule |
|---|---|---|---|---|
| Brian Thomas Jr. (JAX) | WR | 94 | +5.8 | §30/31 + §34 positive TD regression (50+ tgt, <5 TD last yr) |
| Tucker Kraft (GB) | TE | 77 | +49.3 | §10 value + §30/31 role step-up |
| Tyler Warren (IND) | TE | 46 | +49.3 | §10 value + rookie role clarity |
| Jonathon Brooks (CAR) | RB | 127 | -2.2 | §10 value + §30/31 vacated opportunity |
| TreVeyon Henderson (NE) | RB | 68 | +33.8 | §10 value + §29 young, role step-up |

**3 deep sleepers (§29 — ADP > 100 with a startable model rank):**
| Player | Pos | ESPN ADP | Model VORP | Rule |
|---|---|---|---|---|
| George Kittle (SF) | TE | 112 (multi-source; 82 ESPN-specific) | +53.5 | §29 deep sleeper — cheapest top-3 TE outcome on the board |
| Travis Kelce (KC) | TE | 103 | +22.3 | §29 deep sleeper |
| Dallas Goedert (PHI) | TE | 128 | +18.9 | §29 deep sleeper — TE is where ALL of this year's deep value sits |

Note the pattern: nearly every "value" and "deep sleeper" on this board is a **TE** (5 of the top 8
lines in the full report). This room's ESPN ADP still prices TE the old way (McBride/Bowers early,
then a canyon) while the model — and the actual 2026 TE landscape — says the TE8-15 tier
(Loveland/Kraft/Warren/Kittle/Kelce/Goedert) is much tighter to TE1-2 than ADP thinks. **This is the
single biggest lever in this specific draft**, independent of slot.

### 3d. Position tiers (model VORP, espn_la_liga replacement levels) — cliffs marked

**RB** (replacement ~28th): Tier1 Gibbs/Bijan (162/158 VORP, no gap) → Tier2 CMC/Taylor (147/143)
→ Tier3 Cook alone (122) → **Tier4** Henry/Achane/Barkley (116/114/110) → **cliff** → Tier5
Jeanty/Hampton (92/90) → **cliff** → Tier6 (flat, picks ~33-40 ADP: Chase Brown, Jacobs\*, Jeremiyah
Love, K.Walker, Kyren Williams, 66-80 VORP) → Tier7 begins ~Skattebo (54). *Dead zone (§15/42)
starts inside Tier6* — several Tier6 names carry the RB age-27 flag (Jacobs). Bell-cow RBs
effectively run out around ADP 24 (Hampton).

**WR**: Tier1 Chase/Nacua (132/129) → **cliff** → Tier2 JSN/ARSB (101/98) → Tier3 Lamb alone (79)
→ Tier4 Rice/London (70/67) → Tier5 (flat, ADP 25-51: Collins, A.J. Brown, Pickens, Jefferson,
Nabers, Higgins — 47-57 VORP, essentially interchangeable, cost of waiting ≈ 0 inside the tier) →
Tier6 Olave (41) → Tier7 (flat dump: Adams/McMillan/Flowers/Wilson/D.Smith, 23-36 VORP).

**TE**: Tier1 McBride/Bowers (91/87) → **cliff** → Tier2 (flat: Loveland/Kittle/Kraft/Warren,
49-54 VORP, ADP 41-82 — huge ADP spread for equal model value, this is the arbitrage) → Tier3
LaPorta/Fannin (30-32) → Tier4 Kelce/Pitts/Goedert (19-22) → Tier5+ flat and thin from there.
**Tier2 surviving to the mid-rounds is the report's central finding.**

**QB**: **Tier1 is Josh Allen alone** (VORP 88, model's #1 overall by raw points) → **massive
cliff** → Tier2 is a huge flat block, Lamar Jackson through Kyler Murray (18 players, 34 down to
-17 VORP) that doesn't break again until pick ~150+. This is doctrine §13's "QB7-16 flat" taken to
an extreme this year — it argues for **not** paying an early premium for Allen (ESPN ADP 19 already
prices him fairly; he won't survive to any pick past ~20) and instead treating QB as a rounds-3-5-
or-after-9 decision per §40, because the replacement tier barely degrades in between.

## 4. PICK-1 PLAN (primary scenario — if slot 1 holds)

Ran `DraftAdvisor.recommend()` on the live board (roster `espn_la_liga`, 12 teams) with an
ADP-order proxy for the other 11 teams' picks, so these are grounded numbers, not guesses.

### Pick 1 (overall #1)
**Take Jahmyr Gibbs (RB, DET).** Cost-of-waiting (§6-8): RB value now (162 VORP) vs expected best
RB VORP still around at pick 24 (~87) = **~75-point cost of waiting**, the largest gap of any
position at this node (WR ~71, QB ~52 despite Allen's huge tier1-alone gap — because Allen's own
market (ESPN ADP 19) already prices in that he won't survive to pick 24 anyway, so "waiting" isn't
really an option for him). Gibbs is also the room's own consensus #1 (ESPN ADP 1.41) — zero
argument with the market here, just take the top of the board. Doctrine: §6-8 cost of waiting, §15/41/42
(RB capital in rounds 1-3 is fine and profitable; the dead zone is rounds 3-7, not round 1).

Fallbacks (if this were somehow not there — it will be): Bijan Robinson (RB, essentially tied),
Ja'Marr Chase (WR, tier1 alone with Nacua).

### The 24/25 turn (picks 24, 25 — back-to-back)
Simulated board state after Gibbs + an ADP-order field for picks 2-23:

- **Pick 24: Nico Collins (WR, HOU)** — cost-of-waiting recommendation edges A.J. Brown/George
  Pickens (all three are the same flat Tier5 WR block, §8: "flat tier, cost ≈ 0, take the one the
  board gives you"). Omarion Hampton (RB) is also live here (survival ~50% at pick 24 in the real
  ADP-stdev model) — **if Hampton is still there at 24, take him instead**: he's the last true
  Tier5 bell-cow RB before the age-flagged Tier6 dead-zone names, and RB survival craters fast
  after this pick (§15/42).
- **Pick 25: Omarion Hampton (RB, LAC)** if he survived pick 24, otherwise pivot to the next
  Tier5 WR (A.J. Brown / George Pickens) or gamble on Brock Bowers (TE) — Bowers has only ~28-39%
  survival to 24/25 per the real ADP-stdev availability model, so it's a coin-flip play, not a plan.
- **Archetype target for this turn given 2 FLEX (3 startable RB/WR-type slots beyond the base
  RB2/WR2):** lock in one more true 3-down piece (RB or true WR1) plus start the WR corps — you
  need 3 WR by round 6 per §38, and this turn is the natural place to bank the first two.
- **What survives to your next pick (48):** the RB pool by then is age-flagged dead-zone names
  (Jacobs, Rico Dowdle, Rhamondre Stevenson — all §20-flagged) unless a young value name
  (TreVeyon Henderson, Jonathon Brooks, Cam Skattebo) is still out there. The **TE Tier2 block
  (Loveland/Kittle/Kraft/Warren) is the piece most likely to still be sitting there** — that's
  the report's central arbitrage (3c/3d) playing out live.

### The 48/49 turn
Continuing the same simulation (Collins + Hampton banked, ADP-order field fills 26-47):

- **Pick 48: Tee Higgins (WR, CIN)** — cost-of-waiting favors the WR here over the flat QB pool
  (Hurts/Burrow) and even over TE Kittle/Kraft (49-54 VORP but the TE market moves slowly enough
  that waiting one more pick barely costs anything — the doctrine §14 point in action). This also
  satisfies §38: 2 RB / 3 WR by round 6 needs this pick to be a WR, not the QB.
- **Pick 49: Jalen Hurts (QB, PHI)** — the engine's own cost-of-waiting pick, and it's
  doctrine-legal: round 5 sits inside the §40 "elite QB window (R3-5)" — the one place besides
  round 9+ that QB is allowed. Hurts carries a real VORP gap (26) over the rest of the flat QB2
  tier and ADP 48 is fair, not a reach. **If you'd rather bank the checkpoint math more safely,
  take a Tier2 TE (Kittle/Kraft, still likely live at pick 49) instead and push QB to round 9+ —
  both are doctrine-legal; the QB call is the aggressive version of the same plan.**
- **Archetype target:** with 2 RB / 2 WR banked by pick 48, use 48-49 to grab the 3rd WR (checkpoint)
  and either the elite-window QB or a Tier2 TE — whichever the board leaves cheaper. Either way,
  round 6 (pick 72-73) should close out the "2RB/3WR by round 6" checkpoint and grab a value TE if
  still open (Kittle/Kraft plausibly survive that long — ESPN ADP 77-82 on players the model has
  in the TE1/2 tier).

## 5. If your slot moves (order is provisional — see banner)

**EARLY (slots 1-3):** Board realistically offers Gibbs/Bijan/CMC/Taylor/Chase/Nacua at the first
pick regardless of exact slot 1-3 — take the single best RB left (VORP dominates WR here by
~25-30 points at the very top) unless a true WR1 (Chase/Nacua) falls to you, which is a fine
alternative given the flat-tier WR market later. The turn-back pick (~22-27) lands you in the same
Tier5 RB (Hampton)/Tier5 WR (Collins/A.J. Brown/Pickens) flat mix described in section 4 — the
plan is identical, just shifted by 1-3 picks. Archetype: hero-RB or true-WR1-first, then use the
turn to grab the last bell-cow RB or bank WR depth.

**MID (slots 5-8):** First pick still lands in the RB1-tier4 cliff zone (CMC through Barkley/Achane,
all still RB-only options at this depth per the realistic-board projection) — same hero-RB logic
applies, RB VORP still clearly leads at this range. The turn-back gap here is the widest of any
slot group (~11-13 picks each way, §9) — by the time you pick again (~pick 17-19), Trey McBride
(the last Tier1 TE) and Josh Allen (the lone QB1) are both live coin-flips, and the RB pool has
already thinned into Tier5/6 (Hampton, Jacobs-with-age-flag, Kyren Williams). Archetype: take the
elite TE (McBride) or a value RB survivor at the turn rather than reaching for Allen — the QB2
tier is too flat (section 3d) to pay an early premium for tier1-alone.

**LATE/turn (slots 10-12):** The double-pick advantage is real here — picks 1-2 apart at the turn
(e.g. slot 12: picks 12 and 13). First pick still gets a RB3/4-tier or TE1 name (James
Cook/Henry/Barkley/Jeanty tier or McBride); the very next pick a few slots later lets you double up
on the same thinning tier before the room reacts (§9) — e.g. bank two Tier4/5 RBs back-to-back, or
pair a Tier1 RB with McBride (TE) before the next Tier1-adjacent name is gone. This slot group is
the best position to secure the last true difference-making TE alongside a workhorse RB, because
the double-pick neutralizes the normal one-at-a-time opportunity cost.

## 6. Queue seed — ESPN Pick Queue (~15 names, autodraft insurance for pick 1 + the 24/25 turn)

In priority order (best model player first; the platform auto-drafts the top still-available name
when your queue fires, so this covers pick 1 and, if you're away, both turn picks too):

1. Jahmyr Gibbs (RB)
2. Bijan Robinson (RB)
3. Christian McCaffrey (RB)
4. Ja'Marr Chase (WR)
5. Puka Nacua (WR)
6. Jonathan Taylor (RB)
7. Jaxon Smith-Njigba (WR)
8. Amon-Ra St. Brown (WR)
9. CeeDee Lamb (WR)
10. James Cook (RB)
11. De'Von Achane (RB)
12. Saquon Barkley (RB)
13. Trey McBride (TE)
14. Brock Bowers (TE)
15. Nico Collins (WR)

All 15 are starters-first, no 2nd-QB risk, no K/DST — safe to leave unattended through the first
two turns.

## 7. Data problems hit (worked around, didn't leave anything empty)

- `ffopportunity` files for 2025 are unavailable locally → the real xTD signal (§22) is disabled;
  the report falls back to the (rejected as standalone, per §10 backtest table) TD-share proxy,
  shown only as an "(info)" tag, never scored as a bust rule on its own.
- The low-sample rookie/UDFA synthesizer produces a long tail of ADP-less players (mostly inactive
  practice-squad names, plus one literal placeholder row: **"Duplicate Player" (WR, CHI)** —
  a data-quality artifact in the low-sample fallback, not a real player. None of this pollutes the
  top-200 report; it only shows up at the bottom of the bust list where ADP is NaN. Worth a ticket
  to filter placeholder rows out of the synthesizer, but it didn't affect any drafted-round pick.
- Several NEWS-flagged players (Jayden Higgins, Trey Benson, Jerome Ford, etc.) surface in the
  bust list purely because `load_roster_status` sees them as not Active in today's Sleeper roster
  snapshot — correctly excluded from the value/breakout lists per the news guard; flagged here
  only as an FYI, not as picks to consider.
- ESPN ADP source has no per-player stdev column, so `draft_availability` uses the fallback sigma
  (`max(3, 0.15·ADP)`) for all survival-probability numbers in this report — real, not FFC-grade
  precision, but directionally solid (matches the realistic ADP-order simulation closely).
