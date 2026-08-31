# Feetball 2026 — Full Draft Strategy (The Oracle, slot 6)

Built 2026-08-30 for the live Yahoo draft Mon Sep 7, 8:30pm EDT. League 658684, 10-team,
half-PPR, roster `yahoo_feetball` (QB/2RB/3WR/TE/FLEX/K/DEF/7BN/3IR — 9 starters, 16 total
roster spots at draft time). Sources: `docs/FEETBALL_2026_DRAFT_ORDER.md` (pick inventory +
25-player league keeper list), `docs/DRAFT_DOCTRINE.md` (rule numbers cited below),
`docs/DRAFT_PREP_2026.md` (2026-08-29 prep board). ADP refreshed today (`adp_ffc_half_ppr.csv`,
`adp_sleeper_half_ppr.csv`, both 2026-08-30); value report regenerated today:
`output/draft_reports/value_report_half_ppr_20260830_201020.csv` (`python scripts/draft_value_report.py
--league feetball --sources ffc,sleeper --csv`). Projections vintage: `preseason_2026_half_ppr_20260828_173755.csv`
(2 days old, fine for a Sep 7 draft — regenerate once more the morning of if anything material breaks).

**Every live-pool number below already excludes all 25 league keepers** (Loveland/Burden
ours; the other 23 belong to 8 rival teams — see §6 Threats). Honesty rule: ⚠️RB marks any
call resting on an RB projection (the model's weak spot).

---

## 1. Shape strategy

George owns **7 of the first 35 picks** (#6,13,15,21,26,34,35) then one pick every round
through #75, then keepers eat R9/R13 and trades eat R10/R14, leaving #106,115,146,155 as
pure value/depth/K/DST picks. That's 14 live picks + 2 keepers = 16 slots.

**TE and 1 WR slot are pre-solved.** Loveland (TE, kept R13) and Burden (WR, kept R9) arrive
"free" — no live capital spent, no starter-slot pressure. That changes the math on this
specific report's own read (the Feetball prep board flagged "6+ of the top values are TEs" —
McBride/Kittle/Kraft/Warren/LaPorta/Bowers-keeper). **Do not chase that read.** House rule
§0 (starters first) + §39 (never TE2 before round 9-10) hard-block a second TE while
QB/RB/WR/FLEX starters are open — even McBride's stupid #12 overall model value (223 pts,
+82 VORP, biggest single mispricing in the FFC pool) is a demoted pick here, not a target,
until the very late rounds where he'd cost nothing.

**Roster-construction target given this specific pick set** (§38 benchmarks, adjusted for the
Burden freebie): by round 6 (picks #6,13,15,21,26,34,35,46,55 already thrown — we're deep
into round 6 by our own pick count) have **2+ RB / 3+ WR live-drafted** (Burden makes it
effectively 4 WR-equivalents); by round 10, **4-5 RB / 5-6 WR total incl. Burden**; finish
5-7 RB / 6-7 WR per the Underdog benchmark, same as any other draft — the keepers don't
change the target *counts*, they just make hitting them cheaper.

**RB dead zone alert specific to this inventory**: 5 of our first 7 picks (#21, 26, 34, 35,
46) plus #55 and #66 fall in rounds 3-7 — the confirmed RB dead-zone window (§15/§42,
back-tested 41% bust vs 33% base for RB picked there). Round 4 (picks #34/#35) is the single
**worst bust round in the entire back-test (50%)** — don't force RB into those two picks.
**Plan: Hero-RB+1** — grab a true bell-cow at 1.06, double up at 2.03/2.05 while the last
clean RB1 tier is still up (Henry/Barkley/Jeanty/Hampton/Walker), then pivot hard to WR
through rounds 3-5, take the QB1 window at #21/#26 (below), and only re-enter RB at the
doctrine's hottest cell — **round 6 (#55), 41% league-winner hit rate** — and round 7-8
(#66, #75) once the dead zone empties out and the bust rate drops.

**QB pool is gutted by keepers** (Daniels, Maye, Stafford, Caleb Williams, Dart — 5 useful
arms gone) — see §3 for the specific trigger this forces.

---

## 2. Pick-by-pick plan

For each pick: "live players gone" = actual draft-pool depletion at that slot (keeper
rounds don't consume the pool — computed directly from the custom snake order, not raw
overall pick number). Names are what the live-pool ADP/VBD blend says is realistically
there; always re-check the room in the moment (`draft_live.py` if run, or manual read).

### #6 (R1.06) — 5 live players gone
Board: Gibbs/Bijan/Chase/CMC/Jonathan Taylor are the 5 most likely already off (their
composite ADP is 1-6). Next tier: **Amon-Ra St. Brown (WR, DET)** — vbd #8, zero
age/injury/TD-regression flags, elite target-share anchor — **primary**. Fallback:
**James Cook (RB, BUF)** ⚠️RB (vbd #9, clean 26.9yo bell-cow). **Derrick Henry (RB, BAL)**
⚠️RB (vbd #10) is deliberately DEMOTED to third: our own §20 RB age-cliff rule fires on him
at 32.7yo, and §41 says rounds 1-3 are for safety — don't let the model rank override the
bust rule at the safest pick of the night. *Rule: §41 — take the zero-flag stud.*

### #13 (R2.03) — 12 gone
**Saquon Barkley (RB, PHI)** ⚠️RB (vbd #13) or whichever of Henry/Barkley survived pick 6 —
primary. Fallbacks: **Ashton Jeanty (RB, LV)** ⚠️RB — verify the 8/25 injury tag first — or
**Omarion Hampton (RB, LAC)** ⚠️RB, both clean 22-23yo committee-winners. *Rule: §15/§42
Hero-RB — get RB #2 from the last true bell-cow tier before the dead zone closes.*

### #15 (R2.05) — 14 gone (Achane Smokin' picks in between at #14, but they're keeper-stacked
at RB and unlikely to take from this tier — see §6)
Two coequal branches here — NOT a primary/fallback (amended 2026-08-31):
- **RB double**: whichever of Jeanty/Hampton/**Kenneth Walker III (KC)** ⚠️RB survived.
  Honesty check: this makes #13+#15 a double bet on the model's documented weakest
  position (RB, +0.26 vs consensus), and Walker at ADP 18-20 is at-market, not a steal.
- **Split**: take **Drake London** (ADP 13-21) or **A.J. Brown** (ADP 18-19) here and push
  RB2 to #21/#26 — you start 3 WR + FLEX, so a second elite WR is never wasted, and the
  clean-RB fallbacks (Hampton/Walker tier) sometimes survive to #21.
Decide live by which tier gapped harder by #15. *Rule: §15 Hero-RB math vs §10 value —
either branch banks a top-20 player; avoid only the flagged names.*

### #21 (R3.01) — 20 gone
**Josh Allen (QB, BUF)** — vbd #14, model's biggest non-TE mispricing (+82 VORP vs a 34-pick
ADP), and the Yahoo timing adjustment (§11) means the room takes him ~10-20 picks before
that composite number — #21 may be the *last* shot. **Primary, and see §3 for why this is
the trigger pick.** Fallbacks: **Malik Nabers (WR, NYG)** or **Tee Higgins (WR, CIN)**, both
clean WR2/1 value if Allen is already gone. *Rule: §40 QB elite window (R3-5) pays +17 pts
over slot; never wait into R6-8 (the worst QB cell, -61).*

### #26 (R3.06) — 25 gone
If Allen went at #21: take the best surviving WR — **DeVonta Smith**, **Zay Flowers**, or
**Garrett Wilson** (all clean, vbd #40-45 range). If Allen somehow survived to #26 (unlikely
given Yahoo timing), take him here instead and treat #21 as a second WR/RB pick.
Secondary fallback: **Lamar Jackson (QB, BAL)** — only if Allen is gone AND you want to
gamble a 2nd elite-QB insurance pick, but house rule §0 blocks rostering 2 QBs, so this is
an "instead of," not "in addition to." *Rule: §10 value + §41 — WR2 depth in the dead zone
is safer than reaching for a 3rd RB here.*

### #34 (R4.04) — 33 gone — **worst bust round in the back-test (50%), avoid forcing RB**
**Ladd McConkey (WR, LAC)** or **Jaylen Waddle (WR, DEN)** — both clean vbd #55-63, real
target volume. Fallback: **Terry McLaurin (WR, WAS)** (clean, vbd #59). Avoid reaching for
RB names in this specific window (Montgomery/Stevenson/Etienne/Dobbins are all flagged §20
bust in the report right around here). *Rule: §42 round-4 RB is independently confirmed
unprofitable 6 straight years — sit out the position this pick.*

### #35 (R4.05) — 34 gone (second half of the double)
Round out the WR corps or take the first clean skill-position RB flier: **DJ Moore (WR,
BUF)**, **Jameson Williams (WR, DET — verify the 8/18 injury tag)**, or **Rome Odunze (WR,
CHI)** (breakout signal, §30). If WR feels saturated, **TreVeyon Henderson (RB, NE)** ⚠️RB
is the cleanest non-flagged RB left (23.9yo, no bust tags) and worth taking a pick early
rather than risk him vanishing before #55. *Rule: by round 4 we're already past the §38
2RB/3WR round-6 checkpoint — this pick can go to best-player-available.*

### #46 (R5.06) — 39 gone
**Brian Thomas Jr. (WR, JAX)** — §30/§34 breakout: young, vacated-opportunity, positive TD
regression signal — primary. Fallbacks: **Marvin Harrison Jr. (WR, ARI)** (buy-low WR2) or
**DK Metcalf (WR, PIT)**. Explicitly **not** Tyler Warren (TE, vbd #33) despite the model
loving him — TE2 stays demoted per §39 even at this value. *Rule: still inside the RB dead
zone (rounds 3-7) — stay WR, save the RB push for the round-6 hot cell next pick.*

### #55 (R6.05) — 46 gone — **the doctrine's hottest cell (RB round 6, 41% league-winner rate)**
**TreVeyon Henderson (RB, NE)** ⚠️RB if he survived #35, otherwise the best clean RB left —
check the board for **Rico Dowdle (RB, PIT)** (flagged §20 age-cliff *and* §37 faded
mid-tier "often real value" — mixed signal, verify role clarity live) or **Carnell Tate
(WR, TEN)** as a WR pivot if every remaining RB is bust-flagged. *Rule: §41 — this specific
round/position cell is the single highest-value cell in the entire back-test; don't skip it
for a marginal WR unless every RB option is flagged.*

### #66 (R7.06) — 55 gone — last dead-zone pick
**Jordan Addison (WR, MIN)** (§30/§34 breakout tag) or **Chris Godwin Jr. (WR, TB)** —
primary. RB options here (Dowdle, J.K. Dobbins, Chuba Hubbard) are all §20 age-cliff or
NEWS-flagged (Hubbard injury 8/25) — take one only if a specific role report (not just ADP)
justifies it. *Rule: §15 dead zone closes after round 7 — the back-test's bust rate drops
from here on, so it's fine to punt one more round if the RB board looks contaminated.*

### #75 (R8.05) — 62 gone — dead zone is over, upside window opens (§41)
**RJ Harvey (RB, DEN)** ⚠️RB — deep committee-back flier, or **Quentin Johnston (WR, LAC)**
(sleeper flag, vbd #66) — primary either way depending on roster count at this point (take
RB if still short of 4 total). Fallback: **Jayden Reed (WR, GB)**. *Rule: §45 — round 8+ is
where the iconic ADP-beaters live; spend on upside, not floor.*

**Structural note on #66/#75 (amended 2026-08-31): these two picks are upside-only.**
After #75, two of your four remaining picks are earmarked K/DST, so **#106 and #115 are
your entire bench-building budget** — and 31-pick dead gaps (R8→R11, R12→R15) mean the
whole league drafts around you while you sit out. Safe veteran depth is what a 10-team
waiver wire replaces for free; ceiling is what it can't. Spend #66/#75 on the swings
(Henderson/Harvey/Croskey-Merritt profiles), never on floor.

### R9 (Burden keeper) / R10 (no pick — traded) — nothing to do, roster fills itself.

### #106 (R11.06) — 82 gone
**Stefon Diggs (WR, WAS)** (clean veteran target earner, buy-low) — primary. Fallbacks:
**Jakobi Meyers (WR, JAX)** or **Jacory Croskey-Merritt (RB, WAS)** — a genuine
vacated-opportunity flier this deep (§31). *Rule: §45 deep-round vacated-opportunity shot
list territory — VORP is flat here, profile/role matters more than rank.*

### #115 (R12.05) — 90 gone
Best remaining RB-count filler — **Jordan Mason (RB, MIN)** or **Blake Corum (RB, LA)**
⚠️RB — to push toward the 5-7 RB finish target. This is also the honest window for the
doctrine's "free TE2 dart" exception (§14/§39) if nothing else stands out: **Travis Kelce**
or **Dallas Goedert** at their true cost here (vbd #56/#60, ADP ~110-125) is the one point
in the draft where taking a TE2 is *actually* free, not a reach. *Rule: your call between
RB-count and the TE luxury dart — RB-count wins if you're still short of 5 live RBs.*

### R13 (Loveland keeper) / R14 (no pick — traded) — nothing to do.

### #146 (R15.06) — 120 gone — **first of the final two picks, house rule §0 says K/DST now**
**Best available DST** — from the board at this depth, New England Defense (ADP ~135) or
Pittsburgh Defense (ADP ~139) lead the remaining tier; take DST here since the DST tiers are
marginally steeper than K at this ADP band.

### #155 (R16.05) — 129 gone — **final pick, K**
**Best remaining K** — Cameron Dicker, Jason Myers, Ka'imi Fairbairn, or Tyler Bass are all
still on the board around here and functionally interchangeable (K is famously flat/random
— never worth reaching for). Take whichever is left; it doesn't matter which.

---

## 3. QB plan — the specific trigger

The keeper list removed **5 useful arms from the live pool**: Jayden Daniels, Drake Maye,
Matthew Stafford, Caleb Williams, Jaxson Dart. In a normal draft those 5 anchor the
"QB7-16 flat tier, wait to round 8+" plan (§13). Here, that tier is **structurally thinner**
— the report's own deep-sleeper section for this league clusters the remaining
value QBs (Purdy, Mahomes, Herbert) all the way out at ADP 103-124, later than the
usual 90-110 band, because the mid-tier got gutted.

**Demand-side correction (amended 2026-08-31): every kept QB also removed a TEAM from the
QB market.** Only 5 teams need a starting QB: The Oracle, Achane Smokin', Amon Ra, Bird
Gang, Crazy Eddie's. Four rivals competing for the Hurts/Burrow/Herbert/Purdy/Mahomes/
Lawrence tier is not a shortage — the #75+ fallback is materially safer than the supply-only
read above implies. So the trigger below is a **value trigger, held loosely — not a
must-fire**:

**Trigger: take Josh Allen at #21 if he's there (Sleeper ADP 20 — genuine coin-flip), or
Lamar Jackson at #26.** Both sit in the doctrine's proven elite window (§40, R3-5, +17 pts
over slot) and the Yahoo timing adjustment (§11) puts Allen's real room slot near ~20.
**Never reach for Allen at #15 over London/A.J. Brown.** Live tell: exactly two QB-needy
teams pick between #15 and #21 — **Achane Smokin' at #14 and Amon Ra at #20**. If both
pass, Allen falls to you; if one takes him, shrug and stay on WR — you lose a luxury, not
the plan.

**If both Allen and Lamar are gone by #26**: do **not** force a QB in rounds 4-7 (picks
#34-66) — that is exactly the doctrine's worst QB cell (§40, round 6-8, -61 pts). Instead
wait until **pick #75 (round 8) or later** and take whichever of Trevor Lawrence, Justin
Herbert, Brock Purdy, or Patrick Mahomes remains — accepting a lower ceiling than the
un-gutted-pool plan would have gotten, because the streaming safety net normally provided
by Daniels/Maye/Dart/Stafford/Caleb Williams doesn't exist in this room. House rule §0
still applies throughout: never a 2nd QB regardless of value.

---

## 4. K/DEF plan

Exactly two live picks remain after every skill-position/bench slot is filled: **#146 and
#155**, and exactly two open slots need them (K, DEF) — a clean match with house rule §0
("no K/DST until the final open-slots+1 picks"). Take **DST at #146** (New England or
Pittsburgh, marginally steeper tier at that ADP band) and **K at #155** (Dicker/Myers/
Fairbairn/Bass are functionally interchangeable — take whichever is left). Do not spend a
single pick earlier than this on either position, even for a name-brand K/DST.

---

## 5. Pre-draft rankings queue (Yahoo queue order, ~60 names, keepers excluded)

Ordered by model VBD/ADP blend, with two manual overrides applied and flagged inline:
(1) non-Loveland TEs are **demoted** below the WR/RB/QB pool per §0/§39 (a TE2 is never a
starter-slot need here — don't let raw model value pull one into an early pick), and
(2) Josh Allen/Lamar Jackson are annotated as the QB-window trigger picks from §3.
NEWS-advisory tags are informational — verify before drafting or fading (§36), not a hard
exclude.

| # | Player | Pos | Team | ADP (ffc/slpr) | Flag |
|---|---|---|---|---|---|
| 1 | Jahmyr Gibbs | RB | DET | 1/1 | |
| 2 | Bijan Robinson | RB | ATL | 2/2 | |
| 3 | Ja'Marr Chase | WR | CIN | 4/3 | |
| 4 | Christian McCaffrey | RB | SF | 7/4 | ⚠️RB age 30.2 |
| 5 | Jonathan Taylor | RB | IND | 6/6 | |
| 6 | Amon-Ra St. Brown | WR | DET | 8/8 | |
| 7 | James Cook | RB | BUF | 9/9 | ⚠️RB |
| 8 | Derrick Henry | RB | BAL | 10/16 | ⚠️RB §20 age cliff (32.7) |
| 9 | Saquon Barkley | RB | PHI | 17/10 | ⚠️RB |
| 10 | **Josh Allen** | QB | BUF | 34/20 | QB elite window §40 — PRIMARY, Yahoo timing pulls him to ~pick 20 |
| 11 | CeeDee Lamb | WR | DAL | 12/11 | |
| 12 | Drake London | WR | ATL | 13/21 | |
| 13 | Ashton Jeanty | RB | LV | 24/13 | ⚠️RB — NEWS injury 8/25, verify |
| 14 | Omarion Hampton | RB | LAC | 23/15 | ⚠️RB |
| 15 | A.J. Brown | WR | NE | 18/19 | |
| 16 | George Pickens | WR | DAL | 19/23 | |
| 17 | Justin Jefferson | WR | MIN | 14/12 | |
| 18 | Jeremiyah Love | RB | ARI | 30/27 | ⚠️RB breakout §30 |
| 19 | Malik Nabers | WR | NYG | 26/28 | |
| 20 | Tee Higgins | WR | CIN | 37/38 | |
| 21 | Kenneth Walker III | RB | KC | 20/18 | ⚠️RB |
| 22 | Josh Jacobs | RB | GB | 27/29 | ⚠️RB — NEWS charges 8/29, verify same-day |
| 23 | Davante Adams | WR | LA | 39/55 | §36 market-faded star — verify before paying |
| 24 | Tetairoa McMillan | WR | CAR | 29/36 | |
| 25 | **Lamar Jackson** | QB | BAL | 55/35 | QB elite window §40 — fallback QB target |
| 26 | Zay Flowers | WR | BAL | 25/42 | |
| 27 | Cam Skattebo | RB | NYG | 41/37 | ⚠️RB |
| 28 | Garrett Wilson | WR | NYJ | 32/44 | |
| 29 | DeVonta Smith | WR | PHI | 31/34 | |
| 30 | Jalen Hurts | QB | PHI | 81/62 | do not draft — QB slot filled by #10/#25 |
| 31 | Breece Hall | RB | NYJ | 33/32 | ⚠️RB — NEWS injury 8/24, verify |
| 32 | Joe Burrow | QB | CIN | 59/54 | do not draft — QB slot filled |
| 33 | Jameson Williams | WR | DET | 42/57 | NEWS injury 8/18, verify |
| 34 | D'Andre Swift | RB | CHI | 45/47 | ⚠️RB |
| 35 | Emeka Egbuka | WR | TB | 36/39 | |
| 36 | Ladd McConkey | WR | LAC | 43/40 | |
| 37 | Courtland Sutton | WR | DEN | 60/82 | |
| 38 | Terry McLaurin | WR | WAS | 46/53 | |
| 39 | Mike Evans | WR | SF | 54/61 | |
| 40 | Jaylen Waddle | WR | DEN | 48/48 | |
| 41 | Travis Etienne | RB | NO | 38/41 | ⚠️RB §20 age-cliff bust flag |
| 42 | Quentin Johnston | WR | LAC | 89/105 | sleeper §29 |
| 43 | DK Metcalf | WR | PIT | 67/77 | |
| 44 | Carnell Tate | WR | TEN | 78/67 | |
| 45 | TreVeyon Henderson | RB | NE | 62/52 | ⚠️RB clean, no bust flags |
| 46 | Brian Thomas Jr. | WR | JAX | 71/72 | breakout §30/§34 |
| 47 | Brock Purdy | QB | SF | 87/124 | do not draft — QB slot filled |
| 48 | Jadarian Price | RB | SEA | 75/58 | ⚠️RB low-sample §28 |
| 49 | Stefon Diggs | WR | WAS | 97/114 | |
| 50 | DJ Moore | WR | BUF | 47/56 | |
| 51 | Trevor Lawrence | QB | JAX | 92/98 | do not draft — QB slot filled |
| 52 | Chris Godwin Jr. | WR | TB | 79/90 | |
| 53 | Patrick Mahomes | QB | KC | 110/112 | do not draft — QB slot filled |
| 54 | David Montgomery | RB | HOU | 57/46 | ⚠️RB §20 age-cliff bust — avoid |
| 55 | Rhamondre Stevenson | RB | NE | 64/75 | ⚠️RB §20 age-cliff bust — avoid |
| 56 | Trey McBride | TE | ARI | 40/25 | TE2 dart only §39 — do not draft ahead of starters despite #12 model value |
| 57 | George Kittle | TE | SF | 102/86 | TE2 dart only §39 — NEWS PUP 8/23, verify |
| 58 | Tucker Kraft | TE | GB | 99/65 | TE2 dart only §39 |
| 59 | Tyler Warren | TE | IND | 72/50 | TE2 dart only §39 — NEWS injury 8/20, verify |
| 60 | Sam LaPorta | TE | DET | 129/64 | TE2 dart only §39 |

Beyond #60 for reference (fill in live if the top-60 board runs dry before the later picks):
RJ Harvey (RB, DEN), Harold Fannin Jr. (TE — demoted, dart only), Jordan Addison (WR, MIN,
breakout), Jakobi Meyers (WR, JAX), Travis Kelce (TE — demoted, dart only), Dallas Goedert
(TE — demoted, dart only), Jacory Croskey-Merritt (RB, WAS, vacated-opportunity flier),
Jordan Mason (RB, MIN), Blake Corum (RB, LA), then DST/K per §4.

---

## 6. Threats — rival keeper cores and pick-position collisions

| Rival team | Keepers (position mix) | Collision with Oracle |
|---|---|---|
| **Murtaugh & Riggs** | Chase Brown RB, Jayden Daniels QB, Parker Washington WR (1RB/1QB/1WR — balanced) | **Picks immediately before Oracle in R1, R3, R5, R7, R11, R15** (every odd round where Oracle sits at position 6, Murtaugh sits at 5) — the single most recurring direct threat in the whole draft. Still needs RB/WR live, so expect them to take from the same tiers right before every one of those picks. |
| **Achane Smokin'** | De'Von Achane RB, Puka Nacua WR, Quinshon Judkins RB (2RB/1WR, RB-heavy) | Picks *between* Oracle's two R2 selections (#13/#15) at #14. Already RB-stacked via keepers — lower risk they snipe the RB tier there, higher risk they take a top WR or Josh Allen instead. |
| **Bird Gang** | Jaxon Smith-Njigba WR, Christian Watson WR (2WR, WR-heavy) | Picks immediately before Oracle in **R4** (#33, right before #34) — already flush at WR, so likely to grab RB or QB there, a real snipe risk against the round-4 WR pivot plan (§2). |
| **One Giant Mess** | Drake Maye QB (QB solved, no RB/WR cushion) | Picks right before Oracle in **R7 (#64) and R8 (#74)** — with no keeper cushion at RB/WR, this team is the biggest threat to the round 7-8 upside targets (Henderson, RJ Harvey, Johnston) right as the dead zone clears. |
| **Nico$uave** | Nico Collins WR, Chris Olave WR, Matthew Stafford QB (2WR/1QB) | Picks right before Oracle's second R3 pick (#23, before #26) — already 2-deep at WR, so more likely to reach RB or a 2nd elite WR (Nabers-tier) than pure need, worth a glance live. |
| **Amon Ra the Sun God** | Kyren Williams RB, Rashee Rice WR, Bucky Irving RB (2RB/1WR) | Picks 1.01 overall and last in most rounds — not adjacent to Oracle's slot, but already RB-stacked, which slightly *thins* early RB competition for everyone else (a tailwind, not a threat). |
| **Dude I got a Dell** | Brock Bowers TE, Javonte Williams RB, Caleb Williams QB (TE+RB+QB) | TE is *also* solved for this team — one less room competitor for a TE run, which is a mild tailwind if the room otherwise panics on McBride/Kittle/Kraft mid-draft. |
| **I'm a Billiever** | Zach Charbonnet RB, Jaxson Dart QB (1RB/1QB, no WR keeper) | Still needs WR badly — a threat to the WR pool generally, though not seated directly adjacent to most Oracle picks. |
| **Crazy Eddie's** | Travis Etienne RB, Michael Wilson WR, Darnell Mooney WR (1RB/2WR) | Balanced, not seated adjacent to most Oracle picks — lower direct collision risk. |

**Biggest single takeaway**: watch Murtaugh & Riggs at every one of your odd-round picks —
they draft one slot ahead of you almost the entire night. Watch One Giant Mess specifically
around #66/#75 — the least keeper-cushioned team is drafting right into your RB dead-zone-exit
targets.

---

## 7. Deep value shots + waiver watchlist (added 2026-08-31)

Pulled from tonight's value report (RB/WR, ADP 95+, model ≥30 spots ahead, keepers
excluded) plus the UC1 vacated-opportunity sleeper board (`scripts/sleeper_board.py`).

**Honest headline: the model finds essentially ZERO deep RB value this year** — every RB
past ADP ~90 is §20/§28 flagged or pure noise (Jordyn Tyson at vbd 119/ADP 180 is the lone
FFC deep hit, and it's a WR). Deep value in this pool is WR-shaped; RB upside must be
bought at #66/#75 (Henderson/Harvey) or via the UC1 handcuff watchlist, not found late.

**Draftable deep darts — the menu for #106/#115 (and #146 only if a DST-worthy dart
demands it):**
| Player | Pos | vbd/ADP (sleeper) | Note |
|---|---|---|---|
| Quentin Johnston | WR LAC | 66 / 105 | already the #75 fallback — best deep value on the board |
| Stefon Diggs | WR WAS | 77 / 114 | #106 primary, confirmed by fresh report |
| Jakobi Meyers | WR JAX | 88 / 126 | #106 fallback, confirmed |
| Jauan Jennings | WR SF | 123 / 218 | free at #115+, real target history |
| Jordyn Tyson | WR ARI | 119 / 180 (ffc) | rookie dart, only FFC deep value |
| Jerry Jeudy / Calvin Ridley | WR | 164/215 · 186/256 | veteran floor darts, last-pick tier |
| Troy Franklin / Tory Horton / Germie Bernard | WR | 209-223 / 242-278 | pure lottery, waiver-adjacent |

**UC1 waiver watchlist (consensus-UNRANKED — do not draft, monitor from week 1):**
Isaac Guerendo (RB SF — clearest handcuff-to-value path), Cole Kmet (TE CHI — Bears-bye
insurance for Loveland, ironically), AJ Dillon / Montrell Johnson (RB CAR backfield vacuum),
Nate Carter (RB ATL), Luke Musgrave (TE GB), Jahan Dotson (WR ATL), Jalen Tolbert (WR MIA).

## 8. Rookie targets (added 2026-08-31)

**Honesty note first:** our engine's rookie point projections are NOT market-grade
(positional-baseline fallback — a documented limitation), so rookie edges here come from
**NFL draft capital + landing spot + cross-source ADP momentum** (Sleeper runs sharper than
FFC; a big gap = the market is still moving up on the player), per §29 young-breakout
doctrine — not from our VBD ranks.

2026 class joined against both ADP sources (`data/bronze/draft_picks/season=2026`):

| Rookie | Capital | ADP ffc/slpr | Verdict |
|---|---|---|---|
| **Carnell Tate (WR, TEN)** | 1.04 | 78 / 67 | **Best rookie buy — top-5 NFL pick priced like a WR3.** Target at **#66** (he will not reach #75 in a Yahoo room). Already the plan's WR pivot at #55 if RBs are contaminated. |
| **Makai Lemon (WR, PHI)** | 1.20 | 124 / 88 | 36-spot cross-source gap = market momentum. Round-1 capital free at **#106**. Target. |
| **Jordyn Tyson (WR, NO)** | 1.08 | 180 / 96 | 84-spot gap, top-10 capital — the FFC number is stale. Must be taken at **#106** if wanted (Sleeper says he goes ~96; the R8→R11 dead gap will eat him otherwise). |
| Denzel Boston (WR, CLE) | 2.39 | 148 / 159 | mild model value (vbd 139) — **#115** dart. |
| De'Zhaun Stribling (WR, SF) | 2.33 | 131 / 120 | at market — take only as best-available. |
| Jeremiyah Love (RB, ARI) | 1.03 | 30 / 27 | Fully priced (vbd 26 ≈ ADP) AND carries an active NEWS tag — **no edge, verify before ever paying ADP**. ⚠️RB |
| Jadarian Price (RB, SEA) | 1.32 | 75 / 58 | §28 low-sample bust flag stands — **fade at cost**. ⚠️RB |
| Kenyon Sadiq (TE, NYJ) / Eli Stowers (TE, PHI) | 1.16 / 2.54 | 176 / 252 | model likes both (vbd 117/136) but TE is demoted for us (§39) — trade-bait knowledge, not picks. |

**Net effect on the pick-by-pick plan:** Tate joins the #66 primary list alongside Addison/
Godwin; Lemon + Tyson become the top of the #106 menu (ahead of Diggs if you want ceiling
over floor — consistent with the #66/#75 upside-only note); Boston slots into #115. The
rookie RBs are the trap this year, not the treat.

## 9. Post-draft action item — Caleb Williams trade (Bears triple-stack)

George wants to explore stacking **Caleb Williams (QB, CHI)** with his Burden + Loveland
keepers — a full Bears passing-game stack whose ceiling weeks correlate (UC3 QB-stack logic).
Caleb is NOT draftable: he's kept by **Dude I got a Dell** at 10.09.

- **Do not alter the draft plan for this.** The QB trigger stands (Allen #21 / Lamar #26 /
  else wait to #75+). Even a successful Caleb trade would slot him as a starter over a
  #75+ fallback QB, not over Allen/Lamar.
- **After the draft**, float an offer to Dude I got a Dell. They are not QB-desperate
  (Bowers + Javonte also kept), so the price is a real player — but Caleb is worth more
  to The Oracle than to anyone else in the league (he upgrades Burden and Loveland via
  correlation). With 7 top-35 picks, George will have surplus early-round bench depth
  to deal from without touching starters.
- If the draft's QB fallback fires (no Allen/Lamar, streaming from #75+), the trade case
  strengthens: Caleb-for-depth then upgrades QB *and* activates the stack in one move.
- **Concentration cost (amended 2026-08-31):** Burden + Loveland (+ Caleb if traded) share
  the CHI bye and sink together in bad Bears game scripts. Not a reason to unwind — but
  pencil the CHI bye in as a mandatory WR/TE streaming week, and it slightly raises the
  value of the #115 TE2 dart (§14/§39) the plan otherwise calls a pure luxury.
