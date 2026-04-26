---
phase: 73-external-projections-comparison
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/ingest_external_projections_espn.py
  - scripts/ingest_external_projections_sleeper.py
  - scripts/ingest_external_projections_yahoo.py
  - src/sleeper_http.py
  - src/config.py
  - scripts/ingest_sentiment_sleeper.py
  - tests/test_external_projections_ingesters.py
  - tests/fixtures/external_projections/espn_sample.json
  - tests/fixtures/external_projections/sleeper_sample.json
  - tests/fixtures/external_projections/fantasypros_sample.html
autonomous: true
requirements: [EXTP-01]
must_haves:
  truths:
    - "Three Bronze ingester scripts exist (ESPN, Sleeper, Yahoo/FP) and write Parquet to data/bronze/external_projections/{source}/season=YYYY/week=WW/"
    - "Each ingester is invokable as `python scripts/ingest_external_projections_{source}.py --season Y --week W` and exits 0 on success"
    - "Each ingester captures source provenance — the Yahoo proxy script writes column source='yahoo_proxy_fp' (NOT 'yahoo')"
    - "All three ingesters fail-open per D-06: a network/HTTP error logs WARNING and exits 0 with no Parquet written (does not raise)"
    - "Tests use recorded fixtures (no live network in CI)"
  artifacts:
    - path: "scripts/ingest_external_projections_espn.py"
      provides: "ESPN public-league fantasy projections ingester"
      contains: "_SOURCE_LABEL = \"espn\""
    - path: "scripts/ingest_external_projections_sleeper.py"
      provides: "Sleeper projections ingester via existing Sleeper HTTP API"
      contains: "_SOURCE_LABEL = \"sleeper\""
    - path: "scripts/ingest_external_projections_yahoo.py"
      provides: "FantasyPros consensus → yahoo_proxy_fp ingester"
      contains: "_SOURCE_LABEL = \"yahoo_proxy_fp\""
    - path: "tests/test_external_projections_ingesters.py"
      provides: "Pytest coverage for all three ingesters via fixtures"
      contains: "def test_"
  key_links:
    - from: "ingester scripts"
      to: "data/bronze/external_projections/{source}/season=YYYY/week=WW/"
      via: "pd.DataFrame.to_parquet(index=False)"
      pattern: "to_parquet"
    - from: "ingester scripts"
      to: "src.player_name_resolver.PlayerNameResolver"
      via: "name → player_id resolution before write"
      pattern: "PlayerNameResolver|resolve_player_name"
---

<objective>
Implement three Bronze-layer ingesters that pull weekly fantasy projections from ESPN, Sleeper, and FantasyPros (Yahoo proxy). Each writes a timestamped Parquet under `data/bronze/external_projections/{source}/season=YYYY/week=WW/` per the standard S3 key convention. All three are independent (disjoint files) so they run in parallel in Wave 1.

Purpose: Establish the raw source of truth for the Phase 73 comparison feature. Bronze is immutable; Silver consolidation happens in Wave 2.
Output: 3 ingester scripts, 3 fixture files, 1 test file. Bronze partitions populated for at least 1 (season, week) when run locally.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/phases/73-external-projections-comparison/73-CONTEXT.md
@CLAUDE.md
@src/utils.py
@src/player_name_resolver.py
@scripts/ingest_sentiment_rss.py

<interfaces>
<!-- Existing utilities the ingesters consume -->

From src/player_name_resolver.py:
```python
class PlayerNameResolver:
    def __init__(self, bronze_root: Optional[Path] = None) -> None: ...
    def resolve(
        self,
        name: str,
        team: Optional[str] = None,
        position: Optional[str] = None,
    ) -> Optional[str]: ...
    def resolve_batch(
        self,
        names: List[str],
        team: Optional[str] = None,
        position: Optional[str] = None,
    ) -> Dict[str, Optional[str]]: ...

def resolve_player_name(
    name: str, team: Optional[str] = None, position: Optional[str] = None
) -> Optional[str]: ...
```

Bronze S3 key pattern (from CLAUDE.md):
```
data/bronze/external_projections/{source}/season=YYYY/week=WW/{source}_{YYYYMMDD_HHMMSS}.parquet
```

Bronze Parquet schema (per ingester, BEFORE Silver consolidation):
```
columns: player_name (str), player_id (Optional[str]), team (Optional[str]),
         position (Optional[str]), projected_points (float),
         scoring_format (str — "ppr" | "half_ppr" | "standard"),
         source (str — module-level _SOURCE_LABEL), season (int), week (int),
         projected_at (str — ISO 8601 UTC), raw_payload (str — original JSON/row text for traceability)
```

Source endpoints (from CONTEXT.md decisions):
- ESPN: `https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/0?view=mPlayer&view=kona_player_info` (no auth needed for league=0 public projections; default scoring is half_ppr-like — verify each player's `appliedTotal` per scoring period)
- Sleeper: `https://api.sleeper.app/v1/projections/nfl/regular/{season}/{week}` (already exposed via Sleeper MCP; this script uses the same HTTP endpoint for CLI runnability without MCP)
- FantasyPros consensus: `https://www.fantasypros.com/nfl/projections/{position}.php?week={week}&scoring={scoring}` HTML scrape (positions: qb, rb, wr, te, k)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement ESPN ingester + fixture-driven test</name>
  <files>
    scripts/ingest_external_projections_espn.py,
    tests/fixtures/external_projections/espn_sample.json,
    tests/test_external_projections_ingesters.py
  </files>
  <behavior>
    - `argparse`: required `--season`, `--week`, optional `--scoring half_ppr|ppr|standard` default `half_ppr`, optional `--out-root` default `data/bronze/external_projections`
    - Module-level constant `_SOURCE_LABEL = "espn"`
    - `fetch_espn_projections(season: int, week: int, scoring: str) -> pd.DataFrame` returns Bronze schema columns (see interfaces)
    - `_parse_espn_response(payload: dict, season: int, week: int, scoring: str) -> pd.DataFrame` extracts `players[].player.fullName`, `defaultPositionId`, `proTeamId`, `stats[].appliedTotal` per scoring period
    - Position ID → name map and team ID → abbr map are module-level `Final[Dict[int, str]]` constants (ESPN uses numeric IDs)
    - `_resolve_player_ids(df, resolver: PlayerNameResolver) -> pd.DataFrame` adds `player_id` column via `resolver.resolve(name, team, position)` per row; logs WARNING on unresolved
    - `_write_bronze(df: pd.DataFrame, out_root: Path, season: int, week: int) -> Path` writes timestamped Parquet (`espn_{YYYYMMDD_HHMMSS}.parquet`) and returns the path
    - `main()` orchestrates fetch → parse → resolve → write; on any `requests.RequestException` or `KeyError` logs WARNING and exits 0 (D-06 fail-open); never raises to caller
    - Test: `test_espn_parses_fixture` loads `espn_sample.json`, asserts ≥10 rows, `_SOURCE_LABEL == "espn"`, schema columns present, `projected_points` is non-negative float
    - Test: `test_espn_fail_open_on_network_error` monkeypatches `requests.get` to raise; `main(['--season', '2025', '--week', '1'])` exits 0 with no Parquet written
  </behavior>
  <action>
    1. Create `tests/fixtures/external_projections/espn_sample.json` — a minimal but realistic ESPN response with ≥15 players spanning QB/RB/WR/TE (real player names; obtain from a single curl of the public endpoint or hand-craft from public ESPN data). Commit fixture verbatim — no PII, no credentials.
    2. Create `scripts/ingest_external_projections_espn.py` following the patterns of `scripts/ingest_sentiment_rss.py` (argparse, logging via `logger = logging.getLogger(__name__)`, `if __name__ == "__main__":` guard, `sys.exit(0)` on fail-open path).
    3. Use `requests` library (already in requirements.txt — verify) with explicit `timeout=15` and `User-Agent: nfl-data-engineering/0.1`.
    4. Use Python 3.9 type hints (`Optional[str]`, `Dict[int, str]`, NOT `str | None`).
    5. Wire `PlayerNameResolver` lazily in `main()` (avoid per-test resolver rebuild) and pass into `_resolve_player_ids`.
    6. Fail-open contract: catch `requests.RequestException`, `KeyError`, `ValueError` at the top of `main()` — log WARNING with `_SOURCE_LABEL`, return 0. Per D-06.
    7. Create `tests/test_external_projections_ingesters.py` with the two ESPN tests above using `monkeypatch` and `tmp_path` fixtures. Use `pytest.mark.unit`.
    8. Run `python -m pytest tests/test_external_projections_ingesters.py::test_espn_parses_fixture tests/test_external_projections_ingesters.py::test_espn_fail_open_on_network_error -v` — both pass.
    9. Sanity-run the script locally with `--season 2025 --week 1` if a real ESPN fetch is feasible; otherwise the fixture-based tests are the gate.
  </action>
  <verify>
    <automated>python -m pytest tests/test_external_projections_ingesters.py -k "espn" -v</automated>
  </verify>
  <done>
    - Script exists and is executable as a CLI
    - 2 ESPN tests pass (parse-from-fixture, fail-open-on-network-error)
    - `_SOURCE_LABEL = "espn"` is a module-level constant
    - Bronze write path matches `data/bronze/external_projections/espn/season=YYYY/week=WW/espn_YYYYMMDD_HHMMSS.parquet`
    - Type hints are Python 3.9 compatible (no `|` union syntax)
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement Sleeper ingester (reuses existing Sleeper HTTP pattern) + fixture-driven test</name>
  <files>
    scripts/ingest_external_projections_sleeper.py,
    src/config.py,
    tests/fixtures/external_projections/sleeper_sample.json,
    tests/test_external_projections_ingesters.py
  </files>
  <behavior>
    - Mirrors ESPN structure (`_SOURCE_LABEL = "sleeper"`, same argparse, same Bronze schema, same fail-open contract)
    - HONORS D-01 ("use existing MCP-based fetch path; no new HTTP code"): the script does NOT introduce a new requests.get() call sequence for Sleeper. Instead it imports `_get_sleeper_json` (or equivalent fetch helper) from the existing `scripts/ingest_sentiment_sleeper.py` module — that helper is already the canonical Sleeper HTTP wrapper used in production by the daily sentiment cron. New URLs are added to `SENTIMENT_CONFIG` (or a new `SLEEPER_CONFIG` block) in `src/config.py`, NOT hardcoded in the script.
    - If `_get_sleeper_json` is not yet a public/importable helper in `scripts/ingest_sentiment_sleeper.py`, this task FIRST refactors it: extract the HTTP wrapper into `src/sleeper_http.py` (a new tiny module with `def fetch_sleeper_json(url: str, timeout: int = 15) -> dict` returning {} on error per D-06), then update `scripts/ingest_sentiment_sleeper.py` to import from the new shared module. The new external-projections ingester ALSO imports from `src/sleeper_http.py` — single source of truth for Sleeper HTTP.
    - URL added to `src/config.py`: `SLEEPER_PROJECTIONS_URL = "https://api.sleeper.app/v1/projections/nfl/regular/{season}/{week}"` — formatted with `.format(season=season, week=week)` at call time
    - `fetch_sleeper_projections(season, week) -> dict` calls `fetch_sleeper_json(SLEEPER_PROJECTIONS_URL.format(...))`
    - `_parse_sleeper_response(payload, season, week, scoring) -> pd.DataFrame` — Sleeper returns `{player_id: {pts_ppr, pts_half_ppr, pts_std, ...}}`; extract the column matching `scoring`
    - Sleeper player_id is Sleeper-internal numeric, NOT gsis. Resolution: read the existing committed roster Parquet (`data/bronze/players/rosters/season=YYYY/rosters_*.parquet`) for name+team+position, then route through PlayerNameResolver. If the roster lookup yields nothing, emit row with `player_id=""` (empty, NOT None — Silver consolidator handles).
    - Test: `test_sleeper_parses_fixture` mirrors ESPN test
    - Test: `test_sleeper_fail_open_on_network_error` mirrors ESPN test (mocks `fetch_sleeper_json` to return `{}`)
    - Test: `test_sleeper_uses_shared_http_helper_not_requests_directly` — asserts the new script does NOT contain a top-level `import requests` (greps the source) — this is the structural guard for D-01 compliance.
  </behavior>
  <action>
    1. Inspect `scripts/ingest_sentiment_sleeper.py` to find the existing Sleeper HTTP fetch helper (the function that wraps `requests.get(url, timeout=...)` and handles errors). If it is a private/local function, refactor it out into `src/sleeper_http.py` (single function `fetch_sleeper_json(url, timeout=15) -> dict`, returns `{}` on any error and logs WARNING). Update `scripts/ingest_sentiment_sleeper.py` to import from the new module — verify the existing sentiment Sleeper tests still pass (`python -m pytest tests/sentiment/ -k sleeper -v`).
    2. Add to `src/config.py`: `SLEEPER_PROJECTIONS_URL = "https://api.sleeper.app/v1/projections/nfl/regular/{season}/{week}"` adjacent to any existing Sleeper URL constants (or in a new `SLEEPER_CONFIG: Dict[str, str]` block if no existing pattern fits).
    3. Create `tests/fixtures/external_projections/sleeper_sample.json` — Sleeper response shape with ~10-15 player_id keys, each with pts_ppr/pts_half_ppr/pts_std (hand-craft from public Sleeper docs).
    4. Create `scripts/ingest_external_projections_sleeper.py`. Top of file: `from src.sleeper_http import fetch_sleeper_json` and `from src.config import SLEEPER_PROJECTIONS_URL`. CRITICAL: do NOT `import requests` in this file — D-01 compliance.
    5. Sleeper player_id → name/team/position via the committed `data/bronze/players/rosters/season=YYYY/rosters_*.parquet` file (per STATE.md "Bronze player rosters + depth_charts now version-controlled"). If a row has no roster match, emit `player_id=""` and continue (Silver layer handles unmapped rows).
    6. Per D-06, the `fetch_sleeper_json` helper already returns `{}` on error — main() detects empty payload and exits 0 without writing.
    7. Add 3 tests to `tests/test_external_projections_ingesters.py` (the 2 standard ones + the structural D-01 guard `test_sleeper_uses_shared_http_helper_not_requests_directly`).
    8. Run `python -m pytest tests/test_external_projections_ingesters.py -k "sleeper" -v` — all 3 pass. Also run `python -m pytest tests/sentiment/ -k sleeper -v` — no regressions in existing sentiment Sleeper tests.
  </action>
  <verify>
    <automated>python -m pytest tests/test_external_projections_ingesters.py -k "sleeper" tests/sentiment/ -k "sleeper" -v</automated>
  </verify>
  <done>
    - Script exists and is executable as a CLI
    - 3 Sleeper tests pass (parse, fail-open, D-01 structural guard)
    - `_SOURCE_LABEL = "sleeper"` is a module-level constant
    - `src/sleeper_http.py` exists as the single Sleeper HTTP source of truth (D-01)
    - `src/config.py` has `SLEEPER_PROJECTIONS_URL` constant
    - Existing sentiment Sleeper tests still pass (no regression from refactor)
    - Sleeper player_id → gsis mapping via committed roster Parquet documented in module docstring
    - Type hints are Python 3.9 compatible
    - Per D-01 (LOCKED): no new `import requests` in the new ingester
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Implement Yahoo (FantasyPros consensus proxy) ingester + fixture-driven test</name>
  <files>
    scripts/ingest_external_projections_yahoo.py,
    tests/fixtures/external_projections/fantasypros_sample.html,
    tests/test_external_projections_ingesters.py
  </files>
  <behavior>
    - Module-level constant `_SOURCE_LABEL = "yahoo_proxy_fp"` per CONTEXT D-03 (Yahoo via FantasyPros consensus aggregate; provenance label flags this as a proxy until real Yahoo OAuth lands in v8.0)
    - `fetch_fantasypros_projections(season, week, scoring) -> pd.DataFrame` iterates positions ['qb', 'rb', 'wr', 'te', 'k'], fetches `https://www.fantasypros.com/nfl/projections/{position}.php?week={week}&scoring={scoring}` and parses the HTML table
    - `_FP_SELECTORS: Final[Dict[str, str]]` module-level constant: stores the BeautifulSoup CSS selectors (`table#data tbody tr`, `td.player-cell`, etc.) so they're easy to update when FP HTML changes
    - `_parse_fp_position(html: str, position: str, season: int, week: int, scoring: str) -> pd.DataFrame` parses one position page using `bs4` (BeautifulSoup; verify in requirements.txt; if missing, plan must add to requirements.txt)
    - Same Bronze schema as ESPN/Sleeper; combines all positions into one Parquet
    - Same fail-open contract: per-position fetch errors log WARNING and skip that position, but don't kill the whole run; if ALL 5 positions fail, no Parquet is written and exit 0
    - Test: `test_fantasypros_parses_fixture_qb` loads `fantasypros_sample.html`, asserts ≥5 QB rows
    - Test: `test_yahoo_proxy_label_present` asserts the resulting DataFrame has `source == "yahoo_proxy_fp"` (NOT "yahoo")
    - Test: `test_fantasypros_fail_open_on_network_error` mirrors ESPN test
  </behavior>
  <action>
    1. Verify `beautifulsoup4` is in `requirements.txt`. If not, add it (`beautifulsoup4>=4.12`). Note in script docstring.
    2. Create `tests/fixtures/external_projections/fantasypros_sample.html` — a trimmed real FantasyPros QB projections page (only the `<table id="data">` portion, ≥5 rows). Public site, no auth.
    3. Implement script per Behavior. Use `requests` + `bs4`. Selectors live in `_FP_SELECTORS` constant for easy maintenance.
    4. PlayerNameResolver hook same as ESPN — resolve `player_name` + scraped team to gsis player_id.
    5. CRITICAL: `_SOURCE_LABEL = "yahoo_proxy_fp"` (NOT "yahoo") per CONTEXT D-03 — provenance transparency.
    6. Per-position try/except so one position 404 doesn't sink the run.
    7. Add 3 tests to `tests/test_external_projections_ingesters.py`.
    8. Run `python -m pytest tests/test_external_projections_ingesters.py -k "yahoo or fantasypros" -v` — all pass.
    9. Run the full file: `python -m pytest tests/test_external_projections_ingesters.py -v` — 7 tests pass total (2 ESPN + 2 Sleeper + 3 Yahoo).
  </action>
  <verify>
    <automated>python -m pytest tests/test_external_projections_ingesters.py -v</automated>
  </verify>
  <done>
    - Script exists and is executable as a CLI
    - 3 FantasyPros/Yahoo tests pass; total 7 ingester tests pass
    - `_SOURCE_LABEL = "yahoo_proxy_fp"` is a module-level constant — provenance label visible
    - `_FP_SELECTORS` is a module-level constant for HTML selector maintenance
    - `bs4` import is available (requirements.txt updated if needed)
    - `python -m flake8 scripts/ingest_external_projections_*.py` clean
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| External HTTP → ingester | Untrusted JSON/HTML from ESPN/Sleeper/FP servers crosses into local parser |
| Ingester → Bronze Parquet | Untrusted strings written verbatim into `raw_payload` column |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-73-01-01 | Tampering | ESPN/Sleeper/FP response | mitigate | Schema validation in `_parse_*` — required keys checked, missing keys → row skipped with WARNING; `projected_points` cast to float with try/except |
| T-73-01-02 | Denial of Service | requests.get timeout | mitigate | All `requests.get` calls have explicit `timeout=15`; per-position try/except in FP ingester so one slow page doesn't sink the run |
| T-73-01-03 | Information Disclosure | raw_payload column | accept | Public projection data only — no PII, no credentials. Fixtures in tests are public excerpts. |
| T-73-01-04 | Tampering | FantasyPros HTML selectors drift | mitigate | `_FP_SELECTORS` module-level constant + dedicated unit test using fixture; selector breakage caught by `test_fantasypros_parses_fixture_qb` failure |
| T-73-01-05 | Spoofing | Sleeper player_id collision with gsis | mitigate | Sleeper script keeps `player_id` as Sleeper-internal id at Bronze; Silver consolidation (Wave 2) is the join layer that bridges to gsis via PlayerNameResolver |
</threat_model>

<verification>
- All 7 ingester tests green: `python -m pytest tests/test_external_projections_ingesters.py -v`
- Flake8 clean on the 3 new scripts
- Manual sanity (optional, requires network): `python scripts/ingest_external_projections_espn.py --season 2025 --week 1` writes a Parquet; `python -c "import pandas as pd; print(pd.read_parquet('data/bronze/external_projections/espn/season=2025/week=1/').head())"` shows the expected columns
- Full test suite still green (no regressions): `python -m pytest tests/ -q`
</verification>

<success_criteria>
- [x] 3 Bronze ingester scripts exist and are CLI-runnable
- [x] Each ingester writes to `data/bronze/external_projections/{source}/season=YYYY/week=WW/` with the standard `{source}_YYYYMMDD_HHMMSS.parquet` naming
- [x] Yahoo proxy script uses `_SOURCE_LABEL = "yahoo_proxy_fp"` (not "yahoo") — provenance transparency
- [x] All 3 ingesters fail-open on network errors (D-06 contract)
- [x] 7 fixture-driven tests pass; no live network calls in CI
- [x] PlayerNameResolver wired in for ESPN + FP; Sleeper documents partial mapping (Silver fixes in Wave 2)
- [x] Type hints Python 3.9 compatible
</success_criteria>

<output>
After completion, create `.planning/phases/73-external-projections-comparison/73-01-SUMMARY.md` summarizing: scripts created, fixtures committed, test count, requirements covered (EXTP-01).
</output>
