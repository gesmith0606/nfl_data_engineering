# Matchup View — Placeholder Inventory

**Phase:** 64-matchup-view-completion
**Plan:** 64-01 (Wave 1 — inventory/contract)
**Source file:** `web/frontend/src/features/nfl/components/matchup-view.tsx` (989 lines, committed in `defd6cc`)
**Audit date:** 2026-04-17

This document lists every placeholder, fake value, or data gap in `matchup-view.tsx` that the remaining plans in Phase 64 (64-02, 64-03, 64-04) must replace with real NFL data. Each entry names the file:line range, what it fakes, the MTCH-XX requirement it violates, and the exact data source + column set that will replace it.

---

## Placeholder Catalogue

### 1. `buildDefensiveRoster` — fully synthetic 11-man defense

- **Symbol + lines:** `buildDefensiveRoster(team)` — lines **718-750**. Depends on `slotHash(team, slot)` — lines **709-716**.
- **What it fakes:** Every defensive player on the opponent. Eleven slots (DE1/DT1/DT2/DE2/LB1/LB2/LB3/CB1/CB2/SS/FS) are populated from a hardcoded `defaults` dict mapping slot → `{name, rating}`. Player identity is `"${team} ${def.name}"` (e.g., "KC DE", "KC DT"). `player_id` is synthesised as `${team}-${slot}`. `position_rank`, `injury_status`, `projected_points` are all `null`. Ratings come from `base_rating + slotHash()`, which is a deterministic hash in the range `-5..+4` — purely cosmetic variance, **zero signal from reality**.
- **Requirement violated:** **MTCH-02** (primary — "Defensive roster uses actual NFL data (not placeholder hashes)") and **MTCH-03** (secondary — advantage diff uses these fake ratings).
- **Replacement source:**
  - **Names + slots:** `data/bronze/players/rosters/season=YYYY/rosters_*.parquet` via new endpoint `GET /api/teams/{team}/roster?side=defense&season=YYYY&week=WW` (see `API-CONTRACT.md` Endpoint B). Filter rows where `team == {team}` and `status in ('ACT','RES')` and `depth_chart_position in ('DE','DT','NT','OLB','ILB','MLB','CB','FS','SS','DB','LB')` (roster shows these granular positions despite `position` column being coarse like `LB`).
  - **Starter selection:** Left-join `data/bronze/players/snaps/season=YYYY/week=WW/snaps_*.parquet` on `player_name`; take top N players per `depth_chart_position` ordered by `defense_pct` descending. Map to slots: first two DE rows → DE1/DE2, first two DT/NT rows → DT1/DT2, first three OLB/ILB/MLB/LB rows → LB1/LB2/LB3, first two CB rows → CB1/CB2, first FS → FS, first SS → SS.
  - **Ratings:** Per-slot rating comes from team-level positional allowed-points percentile in `data/silver/defense/positional/season=YYYY/opp_rankings_*.parquet`, mapped through new endpoint `GET /api/teams/{team}/defense-metrics`. Formula: `rating = 101 - round(rank/32 * 49 + 50)` → rank 1 defense → 99 overall, rank 32 → 50. Defensive line slots use DL-oriented rank (proxy via `QB` rank inverted since QB pressure drives QB pts allowed), secondary slots use `WR` rank, LBs use blended `RB + TE` rank. See API-CONTRACT.md for exact mapping.
- **Risk / caveats:**
  - **2026 rosters not present locally** (confirmed: `ls data/bronze/players/rosters/season=2026/` is empty). Fallback: use most recent 2025 snapshot (`rosters_20260413_171612.parquet`) and mark response `fallback: true`.
  - `depth_chart_position` values observed in 2025 roster: `WR, CB, T, DT, RB, TE, G, OLB, DE, FS, QB, ILB, C, SS, MLB, K, DB, P, LS, NT, LB, FB` — no `EDGE` group (EDGE rushers show as `OLB` or `DE`). Matching logic must treat `DE` and `OLB` as interchangeable for DE1/DE2 slots if only one is present.
  - Snap counts in 2025 week=18 are available (1472 rows), but earlier preseason weeks may have zero snap data; starter selection must fall back to `depth_chart_position` alone when snaps are empty.
  - Silver defense positional is **team-level**, not player-level — individual CB1 does NOT get a unique rating. All secondary slots share the team's WR-allowed rank. This is acceptable per plan (slot variance via positional mapping), but do NOT present it as per-player grading.

---

### 2. `buildOffensiveRoster` — OL placeholder (5 slots with `rating: 65`)

- **Symbol + lines:** `buildOffensiveRoster(projections, team, ratingsMap)` — lines **142-188**. OL stub is the `if (slot.pos === 'OL')` branch at lines **162-175**.
- **What it fakes:** Five OL slots (LT, LG, C, RG, RT) are filled with a stub row: `player_id = ${team}-${slot}`, `player_name = slot.label` (literally "LT", "LG", "C", "RG", "RT"), `rating: 65` hardcoded, `projected_points: null`, `injury_status: null`. No OL name, no rating variance between teams, no tie to real roster.
- **Requirement violated:** **MTCH-01** ("Offensive roster shows real player projections and ratings") — the OL slots are part of the offense and currently fail this.
- **Replacement source:**
  - **Names + slots:** Same `GET /api/teams/{team}/roster?side=offense&season=YYYY&week=WW` endpoint. The 2025 roster file has `depth_chart_position in ('T','G','C')` (250 Ts, 199 Gs, 102 Cs) — there is **no native LT/LG/RG/RT distinction** at the roster layer.
  - **Slot assignment heuristic:** Within each team's `T` rows (2 or more), sort by `defense_pct + offense_pct` desc (use total snap involvement as starter proxy), then assign the first two to LT/RT. Rule: if jersey numbers are available, lower jersey → LT (NFL convention), but this is not reliable. Simpler: order by `offense_pct` descending — top two Ts become LT and RT (LT vs RT is truly indistinguishable from roster data alone; API returns two "T" starters and the frontend labels them LT/RT by ordering). Same pattern for Gs → LG/RG. `C` takes the single snap leader.
  - **Ratings:** There is **no per-player OL rating in the pipeline**. Fallback: team-level run-block proxy = percentile rank of `adj_off_epa` for run plays from `data/silver/teams/sos/season=YYYY/sos_*.parquet`. All five OL slots on a team share the same rating (mapped 1-32 rank → 50-99 scale). Acknowledge: this is a downgrade from per-player grading that PFF would provide; document in response as `rating_source: "team_run_block_proxy"`.
- **Risk / caveats:**
  - Roster does not disambiguate left/right OL positions — the frontend label (LT vs RT) is cosmetic, not data-driven.
  - Backup OL becomes the "starter" if the true starter is on IR (status=RES) and filtered out; this is the correct behavior (the next man up is the real starter) but the frontend should treat it as informational.
  - Fullbacks (FB, 17 rows in 2025) are not currently used by `OFFENSE_SLOTS`; inventory only. Out of scope for 64-01; this plan does not add an FB slot.
  - `adj_off_epa` from SOS is **not split by run/pass**. True run-block proxy needs PBP aggregation by play_type; for phase 64 we use overall `adj_off_epa` as a stand-in and flag as approximation.

---

### 3. `computeRatings` — offense-only, defense never passes through this

- **Symbol + lines:** `computeRatings(players)` — lines **103-137**.
- **What it fakes:** Not strictly a placeholder, but the rating pipeline **only accepts `PlayerProjection[]` (skill positions)** and uses `projected_points` percentile within position as the sole input. Defensive ratings never reach this function — they are synthesised in `buildDefensiveRoster` (see entry #1). OL ratings bypass this too (see entry #2).
- **Requirement violated:** **MTCH-03** ("Matchup advantages calculated from real data") — the asymmetry means offense ratings reflect projected fantasy output while defense ratings are hash-derived; subtracting one from the other (see `getAdvantage`, entry #4) compares apples to oranges.
- **Replacement source:** No direct replacement of `computeRatings` itself; it continues to drive skill-position (QB/RB/WR/TE) ratings from projections. The fix is upstream: `buildDefensiveRoster` must pull ratings from `GET /api/teams/{team}/defense-metrics` (see entry #1). After 64-02 + 64-03, both sides of the matchup use ratings derived from the same logical scale (1-32 rank → 50-99).
- **Risk / caveats:**
  - The 50-99 mapping for offense (percentile within position × 49 + 50) and the proposed 50-99 mapping for defense (rank-based × 49 + 50) are numerically comparable but measure different things (per-player projected-points percentile vs. team-level avg-pts-allowed percentile). Document this asymmetry in tooltips so users don't over-interpret an "84 WR1 vs 68 CB1" gap — it's a rank comparison, not PFF grades.

---

### 4. `getAdvantage` + `MatchupAdvantages` — diff is meaningful only after #1 and #3 land

- **Symbol + lines:** `getAdvantage(slot)` inside `TeamPanel` — lines **362-391**. `MatchupAdvantages` component — lines **574-645**.
- **What it fakes:** The advantage calculation (`diff = offPlayer.rating - avgDefRating`) is functionally sound, but its inputs are fake on the defense side (entry #1). Thresholds (`>= 15` = strong, `>= 5` = slight, `<= -10` = disadvantage) map to visual indicators. Currently a "strong advantage" is effectively `slotHash`-driven noise.
- **Requirement violated:** **MTCH-03** ("Matchup advantages calculated from real data").
- **Replacement source:**
  - No direct code change in 64-01; the advantage math is correct. Once 64-02/64-03 land real defense ratings from `GET /api/teams/{team}/defense-metrics`, the diff becomes real.
  - Enhancement (64-04 scope): surface `positional.rank` and `avg_pts_allowed` in the `MatchupAdvantages` tooltip so users see "WR1 85 vs CB-slot 72 — team ranks 22nd vs WRs, allowing 15.1 pts/g" instead of just a numeric badge.
- **Risk / caveats:**
  - The matchup map at lines **368-376** (`{ WR1: ['CB1'], WR2: ['CB2'], WR3: ['CB2','SS'], TE1: ['LB1','SS'], RB1: ['LB2'], RB2: ['LB3'], QB1: ['DE1','DE2'] }`) assumes slot-level coverage logic that does not exist in the data (no CB1 vs. CB2 distinction at the team-positional level). Averaging the same team-WR rank across CB1 and CB2 makes the per-slot variance in the table cosmetic only. Acceptable for V1; note in tooltip.
  - Threshold tuning (5 / 15 / -10) was chosen for the hash-derived ratings. After real data lands in 64-02/64-03, 64-04 must re-examine these cutoffs against observed rating spread.

---

### 5. Hardcoded season/week defaults — `useState(2026)` / `useState(1)`

- **Symbol + lines:** `useState(2026)` and `useState(1)` inside `MatchupView` — lines **783-784**. Season dropdown at lines **847-851** offers `[2026, 2025, 2024, 2023]` (2026 is not in the data lake). Week dropdown at lines **860-866** offers weeks 1-18.
- **What it fakes:** The view opens on **Season 2026 Week 1** regardless of real-world context. Today (2026-04-17) is the NFL offseason; Week 1 of season 2026 would be ~September 2026. There's no data at all for 2026, so the view hits empty projections and predictions until the user manually picks 2025.
- **Requirement violated:** **MTCH-04** ("Schedule-aware — shows correct weekly opponent").
- **Replacement source:**
  - New endpoint `GET /api/teams/current-week` → `{season: int, week: int, source: "schedule" | "fallback"}` (see `API-CONTRACT.md` Endpoint A).
  - Logic: open latest `data/bronze/schedules/season=YYYY/schedules_*.parquet`. Try current calendar year (2026) first; if missing, fall back to year-1 (2025). Find row(s) where today's date falls within `gameday .. gameday + 6 days`. Return that `(season, week)`. If none (offseason / bye gap), return max `(season, week)` present in schedule and set `source: "fallback"`.
  - Frontend change (64-04): replace initial `useState(2026)` / `useState(1)` with state seeded from a `useQuery` against this endpoint. Keep the dropdowns, but populate the `Season` options dynamically from the actual seasons found in the data lake rather than hardcoding `[2026, 2025, 2024, 2023]`.
- **Risk / caveats:**
  - 2026 schedule file is **not present locally** (confirmed via `ls`). Fallback to 2025 is mandatory until bronze_ingestion refreshes with 2026 data.
  - During the offseason, `today` won't fall inside any schedule range. The endpoint must return the final completed week of the latest season (e.g., Super Bowl week or Week 22 conference championships) with `source: "fallback"`.
  - The season dropdown currently includes 2026 — after this plan, 64-04 should strip seasons without local data OR rely on an `/api/teams/available-seasons` endpoint (out of scope for 64-01; note for 64-04 scope).

---

## Data Availability (audited 2026-04-17)

### Seasons present locally

| Dataset | Seasons present | Latest snapshot | 2026 present? |
|---|---|---|---|
| `data/bronze/schedules/` | 2016-2025 | `season=2025/schedules_20260311_193539.parquet` | **NO** |
| `data/bronze/players/rosters/` | 2016-2025 | `season=2025/rosters_20260413_171612.parquet` | **NO** |
| `data/bronze/players/snaps/` | 2016-2025 (weeks 1-22 for 2025) | `season=2025/week=22/...` | **NO** |
| `data/silver/defense/positional/` | 2016-2025 | `season=2025/opp_rankings_20260329_004549.parquet` | **NO** |
| `data/silver/teams/sos/` | 2016-2025 | `season=2025/sos_20260329_004612.parquet` | **NO** |

### 2026 Data Gap — Fallback Recommendation

**Finding:** No 2026 schedules, rosters, snap counts, defense rankings, or SOS files exist in `data/` at audit time. Today's calendar date is **2026-04-17** (NFL offseason — no week-to-week games).

**Recommendation for plan 64-02 / 64-04:**

1. **Default season:** max season present in `data/bronze/schedules/` (currently 2025).
2. **Default week:** max week present in `data/bronze/schedules/season=MAX_SEASON/` where the game has a completed `result`. For 2025 this is likely Week 22 (Super Bowl) or whatever postseason week ended most recently. If we are mid-offseason, the answer is the prior Super Bowl week.
3. **Response metadata:** both `GET /api/teams/current-week` and the roster/defense endpoints must return a `fallback: bool` flag so the frontend can display a banner: "Showing Week 22 of 2025 (2026 season not yet available)."
4. **Ingestion hook:** once 2026 bronze schedules/rosters arrive (typically August pre-season), the endpoints automatically begin returning live data — no frontend changes needed.

### Roster schema notes (2025 sample)

- **Status values:** `ACT` (1537), `DEV` (481), `CUT` (444), `RES` (435), `INA` (210), `RET` (23), `TRD` (3), `TRC` (1). Starter filter = `ACT` only; include `RES` only if a player is designated to return (backend logic out of scope here, kept as "ACT" until 64-02 confirms).
- **depth_chart_position values** (observed): `WR(401), CB(342), T(249), DT(239), RB(216), TE(206), G(199), OLB(195), DE(189), FS(132), QB(131), ILB(123), C(102), SS(99), MLB(72), K(50), DB(40), P(39), LS(39), NT(29), LB(25), FB(17)`. No `LT/RT/LG/RG` granularity.
- **Missing fields vs. plan interface:** plan frontmatter references `depth_chart_order` — **this column does not exist**. Starter selection must use `defense_pct` from snaps (defense) or `offense_pct` from snaps (offense) as the ordering key. Flag in API-CONTRACT.

---

## Summary Table

| symbol | lines | fakes | MTCH-XX | replacement_source |
|---|---|---|---|---|
| `buildDefensiveRoster` + `slotHash` | 709-750 | 11-man defense synthesised from team abbr + hash; no real names, ratings are `base + hash ∈ [-5,+4]` | MTCH-02 (primary), MTCH-03 | `GET /api/teams/{team}/roster?side=defense` (rosters parquet + snap pct) + `GET /api/teams/{team}/defense-metrics` (silver/defense/positional avg_pts_allowed rank) |
| `buildOffensiveRoster` OL branch | 162-175 | 5 OL slots hardcoded to `rating: 65`, `player_name = slot label` | MTCH-01 | `GET /api/teams/{team}/roster?side=offense` (roster depth_chart_position in T/G/C + snap pct) + team-level `adj_off_epa` proxy for rating |
| `computeRatings` (offense-only scope) | 103-137 | Only skill-position projections feed ratings; defense/OL bypass this path | MTCH-03 | Defensive ratings come from `/api/teams/{team}/defense-metrics` positional ranks; OL from team run-block proxy |
| `getAdvantage` + `MatchupAdvantages` | 362-391, 574-645 | Diff math is correct, but inputs are fake on defense side; tooltips omit underlying rank context | MTCH-03 | No code change in 64-01. After 64-02/64-03 land real defense ratings, add `positional.rank` + `avg_pts_allowed` to tooltips (64-04 scope) |
| `useState(2026)` / `useState(1)` | 783-784 | Hard-defaults to Season 2026 Week 1 (no data exists) | MTCH-04 | `GET /api/teams/current-week` returning `{season, week, source}` from latest schedule parquet; frontend seeds state from this query |

**Placeholder count:** 5 distinct replacement items covering all 4 MTCH requirements.

**MTCH coverage map:**
- MTCH-01 → rows 2, 3 (OL + overall offense rating scale)
- MTCH-02 → row 1 (defensive roster)
- MTCH-03 → rows 1, 3, 4 (advantage math needs real defense ratings on comparable scale)
- MTCH-04 → row 5 (season/week default)
