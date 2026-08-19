# FP-ECR History Coverage — DynastyProcess FantasyPros ECR Archive (2020-2024)

**Ingested:** 2026-08-18 via `scripts/ingest_fp_ecr_history.py --local-file <db_fpecr.csv.gz>`
**Purpose:** Bronze/Silver input for the pre-registered WR-ordinal experiment (owned
elsewhere — this doc covers ingestion only).
**Status:** Local-only data. See "Licensing / provenance" below — never commit the parquet.

## Source

- Repo: `github.com/dynastyprocess/data`, `files/db_fpecr.csv.gz` (in-season weekly
  FantasyPros consensus rankings, GitHub Action-refreshed) + `files/db_playerids.csv`
  (fantasypros_id ↔ gsis_id ↔ sleeper_id crosswalk).
- Archive size at ingestion: 1,528,918 total rows across every FantasyPros ranking page
  type (dynasty, redraft, best-ball, IDP, weekly, ...). Filtered to `page_type in
  {weekly-qb, weekly-rb, weekly-wr, weekly-te}` → 33,144 raw rows, **all of which mapped
  cleanly to a season/week** (zero dropped for missing schedule mapping — see "2025
  status" and the per-season gaps below for why). All 33,144 rows are written to Silver;
  the coverage table below (grouped by `position in {QB, RB, WR, TE}`) totals 33,141
  because 3 rows carry a mislabeled `pos` of DB/DL — see "Known archive quirks."

## 2025 status — checked, NOT resumed

The GitHub Action that refreshes `db_fpecr.csv.gz` last committed on **2025-08-08**
(verified via `GET /repos/dynastyprocess/data/commits?path=files/db_fpecr.csv.gz` at
ingestion time, 2026-08-18 — that commit is still the newest touching this file, over a
year stale). **There is no 2025 in-season weekly data in the archive.** The scrape did
not resume; this is not a filtering artifact on our end.

## Coverage table (season × position)

All rows are PPR-scored for RB/WR/TE and scoring-agnostic ("standard") for QB — see
"Scoring variant reality check" below.

| Season | Position | Rows | Weeks covered | Week range | gsis_id join rate | sleeper_id join rate |
|--------|----------|-----:|---------------:|-----------|-------------------:|----------------------:|
| 2020 | QB | 526  | 11 | 6–16 | 100.00% | 100.00% |
| 2020 | RB | 1439 | 11 | 6–16 | 100.00% | 100.00% |
| 2020 | TE | 1135 | 11 | 6–16 | 99.91%  | 99.91%  |
| 2020 | WR | 1962 | 11 | 6–16 | 99.95%  | 99.95%  |
| 2021 | QB | 840  | 17 | 1–17 | 100.00% | 100.00% |
| 2021 | RB | 2260 | 17 | 1–17 | 99.69%  | 99.73%  |
| 2021 | TE | 1802 | 17 | 1–17 | 99.83%  | 99.83%  |
| 2021 | WR | 3137 | 17 | 1–17 | 100.00% | 100.00% |
| 2022 | QB | 698  | 16 | 2–17 | 99.86%  | 99.86%  |
| 2022 | RB | 1950 | 16 | 2–17 | 99.90%  | 99.90%  |
| 2022 | TE | 1677 | 16 | 2–17 | 99.76%  | 99.76%  |
| 2022 | WR | 2745 | 16 | 2–17 | 99.78%  | 99.74%  |
| 2023 | QB | 682  | 16 | 2–17 | 100.00% | 100.00% |
| 2023 | RB | 1828 | 16 | 2–17 | 100.00% | 100.00% |
| 2023 | TE | 1577 | 16 | 2–17 | 99.43%  | 99.87%  |
| 2023 | WR | 2741 | 16 | 2–17 | 99.89%  | 99.89%  |
| 2024 | QB | 575  | 14 | 4–17 | 100.00% | 100.00% |
| 2024 | RB | 1638 | 14 | 4–17 | 99.88%  | 99.88%  |
| 2024 | TE | 1478 | 14 | 4–17 | 99.12%  | 99.32%  |
| 2024 | WR | 2451 | 14 | 4–17 | 99.80%  | 99.76%  |

**Total: 33,141 rows** (QB/RB/WR/TE only — 3 additional rows in 2022 carry a mislabeled
`pos` of DB/DL, see below) across **78 distinct scrape dates**, 2020-10-16 through
2024-12-27. gsis_id join rate is **≥99.1% in every season/position cell**, most at 100%
— no silent join collapse.

### Per-season gaps (honest accounting — the archive's own scrape cadence, not ours)

- **2020**: missing weeks 1–5 (first scrape 2020-10-16, well into the season — COVID
  schedule chaos may explain the late start) and week 17 (the season's last week;
  2020 was still a 17-week/16-game season).
- **2021**: fullest season — weeks 1–17 covered (missing only week 18, the meaningless
  extra week added when the season expanded to 18 weeks that year; most fantasy
  leagues' regular seasons + playoffs conclude by week 17 anyway).
- **2022 & 2023**: missing week 1 (first scrape lands after week 1's game window
  closes) and week 18.
- **2024**: missing weeks 1–3 and week 18 — the largest early-season gap of the five
  seasons (first scrape 2024-09-27, i.e. week 4).

None of these are join failures — they are calendar weeks the archive's own automation
never scraped. Downstream experiment design should not assume dense weeks-1-through-18
coverage for any season.

## Known archive quirks

- **3 rows (2022 only) carry a mislabeled position.** `Avery Williams` (Falcons
  CB/returner, week 2) and `Troy Hairston II` (Texans DL, weeks 7 & 10) appear on the
  `weekly-rb` / `ppr-rb.php` page with `pos = DB` / `DL` respectively, ranked at the
  bottom of the RB board (ecr 80–95, i.e. deep RB4/5 territory — likely a
  return-specialist/gadget listing bleeding onto the RB page in FantasyPros' own
  source data). Negligible (3/33,144 = 0.009%) — left in the Silver output as-is
  (their `position` column reflects the archive's own mislabel) rather than silently
  dropped, since dropping would hide a real data-quality signal from anyone querying
  this table later. Flagging here so nobody mistakes it for our bug.
- **Scoring variant reality check**: the task brief assumed half-PPR would be the
  primary scoring format with PPR/standard "surviving if cheap." The real archive does
  not support that — **weekly RB/WR/TE pages are PPR-only** (`fp_page` always
  `ppr-{rb,wr,te}.php`; no `half-ppr-*.php` or `wr.php`/`rb.php`/`te.php` weekly variant
  exists anywhere in 1.53M archive rows), and **weekly QB pages are scoring-agnostic**
  (`qb.php`, labeled `standard` here since passing/rushing points don't depend on
  receptions). The ingestion script's `scoring` column is still derived generically
  from `fp_page` (so it would pick up a half-PPR weekly variant for free if
  DynastyProcess ever adds one), but as of this ingestion **100% of rows are `ppr` or
  `standard` — there is no half-PPR weekly ECR to ingest.** Any WR-ordinal experiment
  design assuming half-PPR-specific weekly consensus should be aware it doesn't exist
  in this source; the PPR numbers are the closest available signal.

## Spot check — 2023 Week 5 weekly-wr top-5

Scrape date 2023-10-06 (Friday, within the week-5 game window 2023-10-05–2023-10-09).

| pos_rank | Player | ECR | sd | best | worst | gsis_id |
|---------:|--------|----:|---:|-----:|------:|---------|
| 1 | Tyreek Hill | 1.38 | 0.53 | 1 | 3 | 00-0033040 |
| 2 | Justin Jefferson | 1.64 | 0.48 | 1 | 2 | 00-0036322 |
| 3 | Stefon Diggs | 3.60 | 0.87 | 3 | 6 | 00-0031588 |
| 4 | Davante Adams | 4.04 | 0.90 | 3 | 6 | 00-0031381 |
| 5 | Ja'Marr Chase | 5.53 | 1.18 | 3 | 9 | 00-0036900 |

**Pass** — Justin Jefferson and Tyreek Hill both land in the top 3, as expected for a
real week-5 2023 WR consensus snapshot.

## Season/week mapping rule (the leakage boundary)

FantasyPros scrapes weekly consensus rankings a few times *before* that week's games
fully conclude (Tue–Mon of the game week), including scrapes that land after that
week's Thursday game has already been played. `scripts/ingest_fp_ecr_history.py` maps
each `scrape_date` to the smallest NFL week (from Bronze schedules, REG games only)
whose game window has **not yet fully concluded** as of `scrape_date` — i.e. the first
week where `scrape_date <= week_max_gameday`. Season is derived from the calendar
month: January/February dates belong to the *prior* season (NFL convention — a week
18/19 game in early January is still part of the previous season's schedule); all other
months belong to the same-year season. A scrape landing after the last REG week (18)
of a season concludes maps to no week and is dropped with a warning — this never fires
against the real archive (see "2025 status" and the per-season gaps above: no weekly-
position scrape in this archive falls in January for any season 2020-2024).

## Licensing / provenance — LOCAL-ONLY

`dynastyprocess/data` is GPL-3.0, and the underlying rankings are themselves scraped
from FantasyPros.com, a commercial site whose own ToS restricts redistribution. This
data is **private research use only**:

- Code (`scripts/ingest_fp_ecr_history.py`), tests
  (`tests/test_ingest_fp_ecr_history.py`), and this doc are committed.
- Parquet output (`data/bronze/fp_ecr_history/`, `data/silver/fp_ecr/`) is **never
  committed** — both paths are explicitly re-ignored in `.gitignore` (mirroring the
  `data/bronze/odds_api/props/season=*/props_archive_*.parquet` precedent from the
  DK/FanDuel props archive backfill), even though the repo's blanket `data/*` deny
  already covers them (neither path has an allowlist entry).
