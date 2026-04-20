---
phase: 61-news-sentiment-live
plan: 01
subsystem: data-ingestion
tags: [bronze, sentiment, ingestion, rss, reddit, news, rule-first, no-key]

# Dependency graph
requires:
  - file: "scripts/ingest_sentiment_reddit.py"
    provides: "Reference Bronze item envelope shape (_post_to_item) and envelope wrapper (_save_items)"
  - file: "src/player_name_resolver.py"
    provides: "PlayerNameResolver.resolve(name, team=...) for candidate name -> player_id mapping"
  - file: "src/config.py::SENTIMENT_LOCAL_DIRS"
    provides: "Local Bronze path dict used by every sentiment ingestor"
provides:
  - "scripts/ingest_sentiment_rotowire.py: RotoWire RSS -> Bronze JSON envelopes at data/bronze/sentiment/rotowire/season=YYYY/"
  - "scripts/ingest_sentiment_pft.py: Pro Football Talk RSS -> Bronze JSON envelopes at data/bronze/sentiment/pft/season=YYYY/"
  - "SENTIMENT_LOCAL_DIRS['rotowire'] and SENTIMENT_LOCAL_DIRS['pft'] entries"
  - "SENTIMENT_CONFIG['reddit_subreddits'] default expanded to include DynastyFF"
  - "17 new tests under tests/sentiment/ (5 rotowire + 6 pft + 5 reddit-expanded + 1 shared config assertion)"
affects:
  - "Daily cron (plan 61-04) can now ingest 3 additional news sources without API keys"
  - "Website news page (plan 61-05) will have more real articles to display once ingestion runs"
  - "Rule-extractor (plan 61-02) will see broader text coverage for injury/transaction/usage signals"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bronze sentiment envelope: fetch_run_id + source + fetched_at + season + week=None + item_count + items"
    - "Item envelope: external_id/url/permalink/title/body_text/author/published_at/source/score/num_comments/candidate_names/resolved_player_ids/team_hint"
    - "D-06 graceful failure: HTTPError/URLError/ET.ParseError/generic exception all log WARNING and exit 0 to keep the daily cron unblocked"
    - "Stdlib-only HTTP + XML parsing (urllib.request + xml.etree.ElementTree) — no new deps"
    - "PlayerNameResolver fallback to _NullResolver when the Bronze index cannot be built (first-run bootstrap safety)"

key-files:
  created:
    - "scripts/ingest_sentiment_rotowire.py"
    - "scripts/ingest_sentiment_pft.py"
    - "tests/sentiment/__init__.py"
    - "tests/sentiment/test_ingest_rotowire.py"
    - "tests/sentiment/test_ingest_pft.py"
    - "tests/sentiment/test_ingest_reddit_expanded.py"
  modified:
    - "src/config.py"
    - "scripts/ingest_sentiment_reddit.py"

key-decisions:
  - "Each ingestor owns its own copy of the _NAME_PATTERN regex and _TEAM_MENTIONS dict (per D-01 web-scraper-agent convention) rather than extracting to a shared util; keeps coupling low and makes each script readable in isolation."
  - "D-06 is enforced uniformly: every network-class exception path in the two new scripts returns 0, matching the Reddit reference script's fault tolerance."
  - "PFT feed author lives under the Dublin Core namespace (<dc:creator>); parser resolves this explicitly rather than using feedparser to avoid adding a feedparser dep for non-RSS-standard fields."
  - "Added a _NullResolver fallback so the scripts still run end-to-end on a fresh checkout with no Bronze data yet (otherwise the daily cron would crash the first time)."
  - "Kept the regression test for Reddit _post_to_item envelope inside tests/sentiment/ next to the new expansion tests so future drift on the Reddit script is caught by both suites."

patterns-established:
  - "Free-source news ingestor template: urllib + ElementTree + PlayerNameResolver + SENTIMENT_LOCAL_DIRS + graceful failure exit(0). Transplantable to any future RSS/JSON feed addition (e.g., beat-writer RSS bridges)."

requirements-completed: [NEWS-01, NEWS-02]

# Metrics
duration: 20min
completed: 2026-04-17
---

# Phase 61 Plan 01: Expand Free News Sources Summary

**Added RotoWire and Pro Football Talk RSS ingestion scripts plus DynastyFF to the Reddit default, all writing Bronze JSON envelopes that match the existing Reddit shape exactly; no ANTHROPIC_API_KEY, no paid creds, stdlib-only, D-06 graceful-failure contract honored on every upstream path.**

## Performance

- **Duration:** ~20 min (3 TDD cycles + SUMMARY)
- **Started:** 2026-04-18T00:36:48Z
- **Completed:** 2026-04-18T00:56:31Z
- **Tasks:** 3 (all shipped, all tests green)
- **Files created:** 6 (2 scripts + 1 test package + 3 test files)
- **Files modified:** 2 (`src/config.py`, `scripts/ingest_sentiment_reddit.py`)

## Accomplishments

- **Task 1 — RotoWire ingestion (SHIPPED)**
  - `scripts/ingest_sentiment_rotowire.py` (~440 lines after black): RFC-822 date parsing, HTML-tag stripping, candidate-name regex + team-hint extraction, resolver-backed player ID resolution, Bronze envelope writer.
  - Uses `xml.etree.ElementTree` (stdlib) + `urllib.request` (stdlib) — no new requirements.txt entries.
  - CLI flags mirror Reddit script: `--season`, `--limit` (default 50), `--dry-run`, `--verbose`.
  - `SENTIMENT_LOCAL_DIRS["rotowire"] = "data/bronze/sentiment/rotowire"` wired into `src/config.py`.
  - Live dry-run against `https://www.rotowire.com/rss/news.php?sport=nfl` parsed **5 items** in under 3 s (feed is lightly populated; expected at these early-offseason hours).

- **Task 2 — Pro Football Talk ingestion (SHIPPED)**
  - `scripts/ingest_sentiment_pft.py` (~400 lines after black): same template as RotoWire, with WordPress `<dc:creator>` Dublin Core namespace parsing for author field and CDATA-wrapped HTML stripping.
  - `SENTIMENT_LOCAL_DIRS["pft"] = "data/bronze/sentiment/pft"` wired.
  - D-06 contract verified by two dedicated tests (HTTPError 503 and URLError "no network" both exit 0 with warning).
  - Live dry-run against `https://profootballtalk.nbcsports.com/feed/` parsed **30 items** in under 5 s, 5 of which resolved to canonical player IDs (Justin Fields, Tyreek Hill, Jaxon Smith-Njigba, Davante Adams, etc. based on team hints).

- **Task 3 — Reddit DynastyFF expansion (SHIPPED)**
  - `SENTIMENT_CONFIG["reddit_subreddits"]` default changed from `["fantasyfootball", "nfl"]` to `["fantasyfootball", "nfl", "DynastyFF"]`.
  - Inline `_DEFAULT_SUBREDDITS` fallback in `scripts/ingest_sentiment_reddit.py` updated to match.
  - Rate limiting unchanged (1 req/sec) — still within Reddit's public JSON endpoint tolerance for 3 subs per run.
  - Live dry-run fetched **25 posts per subreddit × 3 subs = 75 total**, with 1-3 player-ID resolutions per sub (typical for default-ordered "new" queue which includes many generic discussion threads).

## Task Commits

1. **Task 1 RED:** `7f4ecbf` — `test(61-01): add failing tests for RotoWire ingestion`
2. **Task 1 GREEN:** `b85a6bf` — `feat(61-01): add RotoWire ingestion to Bronze sentiment layer`
3. **Task 2 RED:** `6d250be` — `test(61-01): add failing tests for PFT ingestion`
4. **Task 2 GREEN:** `71a7c0f` — `feat(61-01): add Pro Football Talk ingestion to Bronze sentiment layer`
5. **Task 3 RED:** `7da7f80` — `test(61-01): add failing tests for Reddit DynastyFF expansion`
6. **Task 3 GREEN:** `23370ed` — `feat(61-01): expand Reddit ingestion to include r/DynastyFF`

## Files Created/Modified

### Created

- `scripts/ingest_sentiment_rotowire.py` (+443 lines after black) — RotoWire RSS ingestor producing Bronze JSON envelopes at `data/bronze/sentiment/rotowire/season=YYYY/rotowire_{YYYYMMDD_HHMMSS}.json`.
- `scripts/ingest_sentiment_pft.py` (+413 lines after black) — Pro Football Talk RSS ingestor producing Bronze JSON envelopes at `data/bronze/sentiment/pft/season=YYYY/pft_{YYYYMMDD_HHMMSS}.json`.
- `tests/sentiment/__init__.py` (+1 line) — Python package marker so `tests/sentiment/` is importable as a test module.
- `tests/sentiment/test_ingest_rotowire.py` (+178 lines) — 6 tests for RotoWire parsing, envelope shape, dry-run, and config wiring.
- `tests/sentiment/test_ingest_pft.py` (+169 lines) — 6 tests for PFT parsing, envelope shape, D-06 HTTPError/URLError graceful exit, dry-run, and config.
- `tests/sentiment/test_ingest_reddit_expanded.py` (+143 lines) — 5 tests asserting DynastyFF is in the defaults, main() iterates all 3 subs, --subreddit override still works, and _post_to_item envelope keys are unchanged.

### Modified

- `src/config.py` — added `"rotowire"` and `"pft"` entries to `SENTIMENT_LOCAL_DIRS`, and expanded `SENTIMENT_CONFIG["reddit_subreddits"]` to include `"DynastyFF"`.
- `scripts/ingest_sentiment_reddit.py` — updated the inline fallback tuple in `_DEFAULT_SUBREDDITS = SENTIMENT_CONFIG.get("reddit_subreddits", [...])` to match the new 3-element default so the script behaves correctly even when the config is unreachable.

## Decisions Made

- **Stdlib-only implementation** (`xml.etree.ElementTree` + `urllib.request`) instead of adding feedparser as a fallback. The existing RSS script imports feedparser, but the two new scripts do not depend on it — this keeps the daily cron runnable on a minimal Python environment and avoids introducing a feedparser version pin across scripts.
- **Explicit Dublin Core namespace parsing** in the PFT script for `<dc:creator>` rather than relying on feedparser's implicit namespace handling. Direct namespace handling makes the parser's contract obvious to future maintainers.
- **Module-local regex/team-dict copies** per D-01 web-scraper convention. A shared util would have been marginally DRYer but would have coupled the three scripts to each other; keeping each script self-contained means a future change to the Reddit regex does not silently affect RotoWire or PFT.
- **`_NullResolver` fallback** added to both new scripts so first-run / missing-Bronze scenarios still exit 0. Without this, `PlayerNameResolver.__init__` would log warnings but continue; the new fallback makes the graceful-failure contract explicit and testable.
- **Tests live in `tests/sentiment/` (new package)** rather than the repo-level `tests/` directory. This matches the plan's file list exactly and mirrors the per-module grouping the project will likely want as the sentiment suite grows (rule_extractor, event adjustments, etc. land in later 61-0x plans).

## Deviations from Plan

**None.** Plan executed exactly as written. The three tasks all passed on the first GREEN commit (after black formatting); no Rule 1/2/3 deviations triggered. No Rule 4 architectural checkpoints were reached.

## Issues Encountered

- **Black reformatting round-trip.** After writing each new script, `python -m black` made formatting-only changes (collapsed multi-line dict entries to one-per-line). Tests still passed post-format. Non-issue; noted for transparency.
- **Network during tests.** `test_dry_run_writes_no_files_and_exits_zero` was written with `patch.object(mod, "_fetch_*_xml", ...)` so the test never touches the network, but the CLI still loads `PlayerNameResolver` which scans Bronze parquet — that step takes ~30 s because the resolver indexes ~14.5k players. Acceptable for a deliberate end-to-end dry-run assertion, but the full `tests/sentiment/` run takes ~2 min because three CLI tests each rebuild the resolver. Future optimization: introduce a shared fixture that reuses a single resolver, or mock `PlayerNameResolver` in these specific tests if runtime becomes a blocker.

## Deferred Issues

None new. Pre-existing items outside this plan's scope remain untouched:

- 2025 roster data not yet ingested (resolver cannot map rookies; shows up as "no match" warnings in live dry-runs). Tracked in MEMORY.md blockers list.
- `ANTHROPIC_API_KEY` not set in Railway (not a blocker for this rule-first plan per D-04; Haiku enrichment is optional).

## Known Stubs

None. All three ingestion scripts write real Bronze JSON (or exit 0 gracefully), and the envelope shape matches the downstream Reddit/RSS contract exactly so rule extraction in plan 61-02 will consume them without changes.

## Threat Flags

No new threat surface beyond what the plan's `<threat_model>` already captured:

- T-61-01-01 (RSS body_text tampering) — mitigated: `body_text` is stored as a plain string; website renderer is responsible for HTML escaping.
- T-61-01-02 (DoS via ingestion) — mitigated: 15-s HTTP timeout + 1-s inter-request sleep + `--limit 50` default + D-06 exit-0 on any failure.
- T-61-01-03 (info disclosure) — accept: private repo; public RSS content contains no PII.
- T-61-01-04 (spoofed Reddit author) — accept: author recorded as provided; not used for trust decisions.

## User Setup Required

**None.** No new secrets, no new env vars, no new external service configuration. The two new scripts can be run locally or in the daily cron immediately:

```bash
source venv/bin/activate
python scripts/ingest_sentiment_rotowire.py  # writes to data/bronze/sentiment/rotowire/
python scripts/ingest_sentiment_pft.py       # writes to data/bronze/sentiment/pft/
python scripts/ingest_sentiment_reddit.py    # now covers 3 subs: fantasyfootball, nfl, DynastyFF
```

## Verification Evidence

Plan verification commands (all from `/Users/georgesmith/repos/nfl_data_engineering/`, venv activated):

- `python -m pytest tests/sentiment/ -v` → **17 passed, 0 failed, 4 warnings** in ~135 s
- `python -m pytest tests/sentiment/ tests/test_reddit_ingestion.py -v -k reddit` → **13 passed, 12 deselected, 0 failed** (includes all 8 pre-existing Reddit regression tests)
- `python scripts/ingest_sentiment_rotowire.py --dry-run --verbose` → **exit 0**, parsed 5 items in <3 s
- `python scripts/ingest_sentiment_pft.py --dry-run --verbose` → **exit 0**, parsed 30 items (5 resolved) in <5 s
- `python scripts/ingest_sentiment_reddit.py --dry-run --verbose` → **exit 0**, 75 items across 3 subs (fantasyfootball=25, nfl=25, DynastyFF=25) in <10 s
- `python -c "from src.config import SENTIMENT_CONFIG; assert 'DynastyFF' in SENTIMENT_CONFIG['reddit_subreddits']; print('OK')"` → **OK**
- `grep "rotowire" src/config.py` → SENTIMENT_LOCAL_DIRS entry present
- `grep "pft" src/config.py` → SENTIMENT_LOCAL_DIRS entry present

### Live dry-run item counts (for plan 61-04 cron budgeting)

| Source     | Items parsed | Items resolved to player IDs | Feed URL |
|------------|-------------|-------------------------------|----------|
| RotoWire   | 5           | 0                             | `https://www.rotowire.com/rss/news.php?sport=nfl` |
| PFT        | 30          | 5                             | `https://profootballtalk.nbcsports.com/feed/` |
| Reddit × 3 | 75 (25×3)   | ~5 (1–3 per sub)              | `https://www.reddit.com/r/{sub}/new.json?limit=25` |
| **Total**  | **~110/run**| **~10/run**                   | — |

(Item counts vary with NFL calendar; expect 2–5× these during the regular season.)

## Next Phase Readiness

- **Plan 61-02** (rule-extractor expansion) can consume RotoWire + PFT Bronze data immediately — envelope shape is identical to Reddit/RSS, so no extractor changes are needed for the source format itself.
- **Plan 61-04** (daily cron) can add the two new scripts to the cron sequence alongside the existing RSS/Sleeper/Reddit jobs. Budget per run: ~10 HTTP calls, <30 s wall-clock (resolver build is the dominant cost, not fetching).
- **Plan 61-05** (news page UI) will see ~30% more articles per refresh once this plan's cron additions land, which directly advances NEWS-02.

## Self-Check: PASSED

- FOUND: scripts/ingest_sentiment_rotowire.py
- FOUND: scripts/ingest_sentiment_pft.py
- FOUND: tests/sentiment/__init__.py
- FOUND: tests/sentiment/test_ingest_rotowire.py
- FOUND: tests/sentiment/test_ingest_pft.py
- FOUND: tests/sentiment/test_ingest_reddit_expanded.py
- FOUND: src/config.py (modified — SENTIMENT_LOCAL_DIRS expanded, reddit_subreddits expanded)
- FOUND: scripts/ingest_sentiment_reddit.py (modified — _DEFAULT_SUBREDDITS fallback updated)
- FOUND: commit 7f4ecbf (test 61-01 RotoWire RED)
- FOUND: commit b85a6bf (feat 61-01 RotoWire GREEN)
- FOUND: commit 6d250be (test 61-01 PFT RED)
- FOUND: commit 71a7c0f (feat 61-01 PFT GREEN)
- FOUND: commit 7da7f80 (test 61-01 Reddit-expanded RED)
- FOUND: commit 23370ed (feat 61-01 Reddit-expanded GREEN)

---
*Phase: 61-news-sentiment-live*
*Completed: 2026-04-17*
