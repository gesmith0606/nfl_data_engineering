# 2026 Draft Prep Boards — La Liga (ESPN) + Feetball (Yahoo)

**Generated 2026-08-29 evening** by the draft agent (`scripts/draft_value_report.py`).
Data vintage: ADP refreshed 2026-08-29 (ESPN + FFC + Sleeper), projections
`output/projections/preseason_2026_half_ppr_20260828_173755.csv` (post-cut-downs),
roster/news snapshot 2026-08-29. **Stale after a few days — regenerate before draft night:**

```bash
python scripts/refresh_adp.py --source espn --scoring standard
python scripts/refresh_adp.py --source ffc --scoring half_ppr
python scripts/refresh_adp.py --source sleeper --scoring half_ppr
python scripts/draft_value_report.py --league la_liga  --sources espn,ffc,sleeper --csv
python scripts/draft_value_report.py --league feetball --sources ffc,sleeper --csv
```

Raw full reports from this run: `output/draft_reports/value_report_la_liga_espn_20260829.txt`
and `value_report_feetball_20260829.txt` (+ CSVs alongside). Doctrine rules cited by § number
are in `docs/DRAFT_DOCTRINE.md`. Honesty rule applies throughout: **RB projections are the
model's weak spot** — RB-driven calls are marked ⚠️RB.

**Do NOT pipe the report through `head`** — SIGPIPE truncates sections silently.

---

## NEWS advisories (BOTH leagues — verify each before drafting or fading)

Keyword tags are ADVISORY (co-occurrence, known false positives), not exclusions.
Highest urgency first:

| Player | Range | Tag | Read |
|---|---|---|---|
| **Josh Jacobs** RB | ADP 27–33 | charges 2026-08-29 (filed TODAY) | Verify same-day before any draft |
| **Puka Nacua** WR | ADP 3–4 | suspension 2026-08-28 | §36 profile at the top of R1 — verify length before paying ADP |
| George Kittle TE | ADP 79–111 | PUP 2026-08-23 | He's a top value IF activated — status check decides |
| Ashton Jeanty RB | ADP 14–24 | injury 2026-08-25 | check |
| Breece Hall RB | ADP 30–33 | injury 2026-08-24 | check |
| Chris Olave WR | ADP 22–31 | injury 2026-08-25 | check |
| Tyler Warren TE | ADP 46–72 | injury 2026-08-20 | check — he's also a value flag |
| Jayden Daniels QB | ADP 47–74 | "retiring" 2026-08-27 | almost certainly a false positive (article mention) |
| Matthew Stafford QB | ADP 70–106 | suspension 2026-08-23 | check |
| Also tagged | — | — | Jameson Williams, Alec Pierce (surgery 8/28), Jonathon Brooks, Chuba Hubbard, Kyle Monangai, Rachaad White, Kyler Murray, Alvin Kamara, Jeremiyah Love |

---

## LA LIGA — ESPN, 12-team, half-PPR, roster `espn_la_liga`

> **RULE CHANGES 2026-08-31 (draft day, verified live in ESPN settings):**
> 1. **NO KICKERS** — K starters 0 / max 0 league-wide. Roster is now 16 spots
>    (9 starters + 7 BN) → **16-round draft**. Never queue or recommend a K.
>    `espn_la_liga` in config.py updated to match.
> 2. **DRAFT ORDER IS RANDOMIZED 1hr before draft** (Aug 31 7:30 PM EDT, 90s/pick).
>    The old "MY PICK 1.01" assumption is DEAD — slot revealed ~6:30 PM. Prep is
>    slot-agnostic; set `my_pick` in config.py LEAGUE_PRESETS once revealed.
> 3. Divisions removed (single 12-team table); playoff seeding tiebreak Total Points For.
> The 1.01-specific narrative below predates the randomization — reread it as
> "if I land pick 1" and lean on tiers + cost-of-waiting for any other slot.

**1.01: Jahmyr Gibbs** ⚠️RB — model #1 = ESPN ADP #1. Model and room agree on the entire
top 5 (Gibbs, Bijan, Chase, Nacua†, CMC — † NEWS tag above), so R1 is landmine-avoidance,
not edge-hunting. These top-5 VBD names are the board's "MVP candidates."

**Room read: TE is what this room misprices.** 6 of the top 10 cross-source values are TEs.

### Values (model ≥1 round ahead of ESPN ADP, §10)
| Player | Pos | Model | ADP | Gap | Notes |
|---|---|---|---|---|---|
| Kyren Williams | RB | 21 | 36 | +15 | ⚠️RB — likely still there at 24/25 |
| Cam Skattebo | RB | 28 | 40 | +12 | ⚠️RB; value on all 3 sources |
| Colston Loveland | TE | 29 | 41 | +12 | §30/31 vacated + §29 young |
| George Kittle | TE | 30 | 79 | +49 | NEWS: PUP — verify |
| Tyler Warren | TE | 34 | 46 | +12 | NEWS: injury 8/20 |

### Busts (fade at ADP, §20/§27)
Kenny Gainwell RB (122 vs ADP 105), Rachaad White RB (143/126, NEWS), Tank Dell WR
(279/155), Isiah Pacheco RB (202/164, age cliff), Mike Washington RB (222/166, low-sample).

### Breakouts (§29-34)
High-confidence (model's strong positions): **Jaxon Smith-Njigba WR** (§30/31 vacated),
**Brock Bowers TE** (17 vs ADP 24, §29). ⚠️RB flags: Bijan (§21 top-5 repeat), Achane (§21),
Omarion Hampton (15 vs ADP 23, §29).

### Deep sleepers (ADP > 120)
Quentin Johnston WR (75/132), Dalton Kincaid TE (80/121), RJ Harvey RB (81/129 ⚠️RB).
(§29 auto-section returned `(none)` for ESPN — threshold quirk, pulled manually from VALUES.)

### Value on 2+ sources (highest-confidence buys)
Skattebo RB, Loveland TE, Kittle TE†, Tucker Kraft TE, Tyler Warren TE†, TreVeyon
Henderson RB, Sam LaPorta TE, Harold Fannin Jr. TE, Jadarian Price RB, Rhamondre
Stevenson RB. († = NEWS tag)

### Picks 24/25 plan
TE1 cliff lands here (McBride gone ~21; Bowers ADP 24.3 = coinflip). Hampton (ADP 24.2)
is the last consensus startable RB2 before a gap to NEWS-tagged Breece Hall (34).
Kyren Williams (ADP 36) is the value most likely to survive to you. WR is deep enough
(Pickens 30, Collins 27, Olave 31†) not to force it here.

---

## FEETBALL — Yahoo, 10-team, half-PPR, roster `yahoo_feetball` (3 WR), draft Sep 7 8:30pm
Keepers: Loveland R13, Burden R9 → **no picks in rounds 9 or 13**. Loveland is OURS —
ignore every Loveland value flag below (off the board for the room too).

**Shape strategy:** 3rd WR slot pushes WR replacement to WR36 (12-team-like depth) while
10 teams make QB/TE replacement shallow (QB11/TE13) → **buy WR3 early; stream QB/TE late.**

**Yahoo timing adjustment (§11):** this board prices off FFC+Sleeper composite (Yahoo has
no headless ADP). Yahoo rooms take QB/TE 10–20 picks earlier → treat every QB/TE value
below as **one round more urgent** in the live room. RB/WR values need no discount.

### Values (§10)
| Player | Pos | VBD | ADP ffc/slpr | Notes |
|---|---|---|---|---|
| Trey McBride | TE | 12 | 40 / 24 | biggest value on the board |
| Josh Allen | QB | 14 | 34 / — | TD-dependent (50% of pts) |
| Brock Bowers | TE | 15 | 45 / — | §29 |
| George Kittle | TE | 31 | 111 / 86 | NEWS: PUP — verify |
| Tyler Warren | TE | 33 | 72 / 50 | NEWS: injury |
| Rashee Rice | WR | 17 | — / 30 | sleeper-source value |

### Busts (§20/§27 — RB age-cliff sweep; rule back-tested 46% vs 32%)
Travis Etienne (65 vs ADP 38–42), David Montgomery (83/46–57), Rhamondre Stevenson
(84/62), Jaylen Warren (96/63–69), Tony Pollard (108/70), Chuba Hubbard (124/78†),
Jadarian Price (75/58, low-sample).

### Breakouts (§29-34)
JSN WR (§30/31), CeeDee Lamb WR (§34 positive TD regression), Brock Bowers TE,
Tucker Kraft TE (32 vs ADP 65–99), Brenton Strange TE (116/167), Brian Thomas Jr. WR.
⚠️RB flags: Bijan, Achane (§21).

### Deep sleepers (ADP > 120)
Sam LaPorta TE (43/129), Travis Kelce TE (56/126), Justin Herbert QB (87/114),
Dallas Goedert TE (60/126), Brock Purdy QB (74/123), Patrick Mahomes QB (82/109–112).

### Value on both sources (cross-platform)
TE-and-QB-heavy: McBride, Kittle†, Kraft, Warren†, LaPorta, Fannin, Kelce, Pitts,
Goedert, Andrews (TE); Hurts, Purdy, Dart, Lawrence, Mahomes, Nix, Mayfield, Love (QB);
Quentin Johnston, Stefon Diggs (WR). **Names most likely to vanish early in the live
Yahoo room: Kittle, LaPorta, Kelce, Hurts, Purdy** — don't bank on composite ADP for them.

---

## Known report quirks (this run)
- ESPN §29 deep-sleeper auto-section returns `(none)` — threshold stricter than ADP>120
  (fix queued).
- A "Duplicate Player" (WR, CHI) placeholder row appears in bust lists — registry
  artifact, ignore (fix queued).
- `ffopportunity 2025 unavailable — §22 xTD disabled` is expected, not breakage.
