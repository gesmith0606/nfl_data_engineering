---
phase: 79-audit-provenance-version-probe
plan: 02
type: execute
wave: 2
depends_on: [79-01]
files_modified:
  - scripts/audit_event_coverage.py
  - scripts/audit_advisor_tools_evt05.py
  - scripts/audit_advisor_tools.py
  - tests/test_audit_script_provenance.py
autonomous: true
requirements: [DQ-01]
must_haves:
  truths:
    - "scripts/audit_event_coverage.py JSON output contains a top-level script_provenance: {sha, dirty, resolved_at} block"
    - "scripts/audit_advisor_tools_evt05.py JSON output contains the same script_provenance block at the top level"
    - "scripts/audit_advisor_tools.py emits a sibling JSON file (TOOL-AUDIT.json) alongside its existing TOOL-AUDIT.md, containing script_provenance + the per-tool probe results"
    - "All three scripts import get_script_sha from src.utils with a single line"
    - "None of the v7.1 historical audit JSONs (event_coverage.json, advisor_tools_72.json) are touched — D-08 forward-only"
  artifacts:
    - path: "scripts/audit_event_coverage.py"
      provides: "Audit script with script_provenance embedded in _build_json_payload output"
      contains: "from src.utils import get_script_sha"
    - path: "scripts/audit_advisor_tools_evt05.py"
      provides: "Audit script with script_provenance embedded in _build_payload output"
      contains: "from src.utils import get_script_sha"
    - path: "scripts/audit_advisor_tools.py"
      provides: "Audit script that writes TOOL-AUDIT.md AND a sibling TOOL-AUDIT.json containing script_provenance"
      contains: "from src.utils import get_script_sha"
    - path: "tests/test_audit_script_provenance.py"
      provides: "Tests asserting each script's JSON-output builder embeds script_provenance correctly"
      contains: "def test_"
  key_links:
    - from: "scripts/audit_event_coverage.py::_build_json_payload"
      to: "src/utils.py::get_script_sha"
      via: "module-level import + call inside _build_json_payload"
      pattern: "script_provenance.*get_script_sha"
    - from: "scripts/audit_advisor_tools_evt05.py::_build_payload"
      to: "src/utils.py::get_script_sha"
      via: "module-level import + call inside _build_payload"
      pattern: "script_provenance.*get_script_sha"
    - from: "scripts/audit_advisor_tools.py::main"
      to: "TOOL-AUDIT.json sidecar"
      via: "json.dump with script_provenance + per-tool results"
      pattern: "TOOL-AUDIT\\.json"
---

<objective>
Wire the `get_script_sha()` helper (Plan 79-01) into all three current audit scripts so every fresh audit JSON carries forensic provenance.

Two scripts (`audit_event_coverage.py`, `audit_advisor_tools_evt05.py`) already write JSON — the change is one new top-level key (`script_provenance`) added to their existing payload builders. The third (`audit_advisor_tools.py`) currently writes markdown only — per planner discretion (CONTEXT.md "Claude's Discretion" §1, line 52), this plan adds a sibling `TOOL-AUDIT.json` so Phase 84's DEPLOY-04 consumer has a uniform JSON surface across all three scripts.

Per D-08: existing v7.1 audit JSONs (`event_coverage.json`, `advisor_tools_72.json` already on disk under `.planning/milestones/v7.1-phases/72-event-flag-expansion/audit/`) are NOT modified or backfilled. Forward-only.

Purpose: Phase 84 DEPLOY-04 reads `script_provenance.sha` and rejects audit evidence whose SHA does not match a known-good audit-script commit. This plan ships the producer half; Phase 84 ships the consumer.

Output: three audit scripts emitting `script_provenance`-stamped JSON; one new test file proving each script's payload builder embeds the field.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md
@scripts/audit_event_coverage.py
@scripts/audit_advisor_tools_evt05.py
@scripts/audit_advisor_tools.py

<interfaces>
<!-- Contract from Plan 79-01 -->

From src/utils.py (landed in Plan 79-01):

```python
def get_script_sha(script_path: str) -> Dict[str, Any]:
    """Returns {"sha": str, "dirty": bool, "resolved_at": str}.
    sha is 40-char hex or "unknown". dirty is bool. resolved_at is ISO-8601 UTC.
    """
```

<!-- Existing payload builders that get the new field -->

From scripts/audit_event_coverage.py (line 179):

```python
def _build_json_payload(*, base_url, season, weeks, rows, teams_with_events, passed) -> Dict[str, Any]:
    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        ...
    }
```

From scripts/audit_advisor_tools_evt05.py (line 146):

```python
def _build_payload(*, base_url, season, weeks, feed_limit, player_teams, team_teams) -> Dict[str, Any]:
    player_pass = len(player_teams) >= EVT_05_PLAYER_GATE
    ...
    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        ...
    }
```

From scripts/audit_advisor_tools.py:
- Currently writes ONLY markdown via `write_audit_markdown()` (line 457).
- `main()` (line 582) calls `write_audit_markdown()` after `run_audit()`.
- `DEFAULT_OUTPUT_PATH` = `.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.md`.
- The new sibling JSON path: `DEFAULT_OUTPUT_PATH.with_suffix(".json")` = `.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.json`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Embed script_provenance in audit_event_coverage.py JSON payload</name>
  <files>scripts/audit_event_coverage.py</files>
  <read_first>
    - scripts/audit_event_coverage.py (FULL FILE — lines 179-208 contain the _build_json_payload function being modified)
    - src/utils.py (confirm get_script_sha signature from Plan 79-01)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-01, D-02, D-03, D-08)
  </read_first>
  <behavior>
    - Running the script writes a JSON whose top-level keys include `script_provenance`
    - `script_provenance` value is exactly the dict returned by `get_script_sha(__file__)`
    - All other top-level keys (`audited_at`, `base_url`, `season`, `weeks`, `gate`, `teams_with_events`, `passed`, `per_team`) are preserved unchanged
    - The historical v7.1 file at `.planning/milestones/v7.1-phases/72-event-flag-expansion/audit/event_coverage.json` is NOT touched by this code change (only re-runs of the script overwrite it; verify nothing in the script forces an in-place rewrite at import time)
  </behavior>
  <action>
    Make two surgical edits to `scripts/audit_event_coverage.py`:

    **Edit 1 — Add the import.** Add this line to the existing top-level imports (right after `import httpx` near line 41):
    ```python
    from src.utils import get_script_sha
    ```

    The script currently runs from the repository root, so `from src.utils import ...` resolves through Python's default sys.path. The test in Task 4 verifies the import resolves.

    **Edit 2 — Embed `script_provenance` in `_build_json_payload`.** Modify the function (currently lines 179-208) to add ONE new top-level key. The new key goes BETWEEN `audited_at` and `base_url` so the file's git provenance sits next to the run timestamp.

    Replace the current return statement with:
    ```python
        return {
            "audited_at": datetime.now(timezone.utc).isoformat(),
            "script_provenance": get_script_sha(__file__),
            "base_url": base_url,
            "season": season,
            "weeks": list(weeks),
            "gate": EVT_04_GATE,
            "teams_with_events": teams_with_events,
            "passed": passed,
            "per_team": [
                {
                    "team": r.team,
                    "positive": r.positive,
                    "negative": r.negative,
                    "neutral": r.neutral,
                    "coach": r.coach,
                    "team_count": r.team_count,
                    "has_events": r.has_events,
                }
                for r in rows
            ],
        }
    ```

    Pass `__file__` (the absolute path of the running audit script). `get_script_sha` accepts absolute paths (Plan 79-01 helper does not require relative paths).

    Do NOT modify the markdown builder (`_build_markdown` at line 211) — markdown output stays unchanged. Phase 84 DEPLOY-04 consumes JSON.
  </action>
  <verify>
    <automated>python -c "import scripts.audit_event_coverage as m; p = m._build_json_payload(base_url='x', season=2025, weeks=(17,), rows=[], teams_with_events=0, passed=False); assert 'script_provenance' in p, list(p.keys()); assert set(p['script_provenance'].keys()) == {'sha', 'dirty', 'resolved_at'}, p['script_provenance']; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "from src.utils import get_script_sha" scripts/audit_event_coverage.py` returns exactly one match
    - `grep -n '"script_provenance"' scripts/audit_event_coverage.py` returns exactly one match (in `_build_json_payload`)
    - Direct call `_build_json_payload(...)` returns a dict with `script_provenance` key whose value has keys `{sha, dirty, resolved_at}`
    - `python scripts/audit_event_coverage.py --help` still succeeds (no syntax errors introduced)
    - The historical file `.planning/milestones/v7.1-phases/72-event-flag-expansion/audit/event_coverage.json` is unchanged on disk (verify via `git status` before any audit re-run)
  </acceptance_criteria>
  <done>
    audit_event_coverage.py imports get_script_sha and embeds `script_provenance` as a top-level JSON key. `_build_json_payload` is the only function modified; markdown output and CLI surface unchanged.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Embed script_provenance in audit_advisor_tools_evt05.py JSON payload</name>
  <files>scripts/audit_advisor_tools_evt05.py</files>
  <read_first>
    - scripts/audit_advisor_tools_evt05.py (FULL FILE — lines 146-186 contain _build_payload being modified)
    - src/utils.py (confirm get_script_sha signature)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-01, D-02, D-03)
  </read_first>
  <behavior>
    - Running the script writes a JSON with `script_provenance` as a top-level key
    - All other top-level keys (`audited_at`, `base_url`, `season`, `weeks`, `feed_limit`, `evt_05_gate_player_news`, `evt_05_gate_team_sentiment`, `non_empty_teams_player_news`, `non_empty_teams_team_sentiment`, `evt_05_passed`, `tool_results`) are preserved unchanged
    - The historical file `.planning/milestones/v7.1-phases/72-event-flag-expansion/audit/advisor_tools_72.json` is NOT modified by this code change
  </behavior>
  <action>
    Make two surgical edits to `scripts/audit_advisor_tools_evt05.py`:

    **Edit 1 — Add the import.** Add to the imports near line 43 (after `import httpx`):
    ```python
    from src.utils import get_script_sha
    ```

    **Edit 2 — Embed `script_provenance` in `_build_payload`.** Modify the function (currently lines 146-186) to add the new key BETWEEN `audited_at` and `base_url`. Replace the current return statement with:

    ```python
        return {
            "audited_at": datetime.now(timezone.utc).isoformat(),
            "script_provenance": get_script_sha(__file__),
            "base_url": base_url,
            "season": season,
            "weeks": list(weeks),
            "feed_limit": feed_limit,
            "evt_05_gate_player_news": EVT_05_PLAYER_GATE,
            "evt_05_gate_team_sentiment": EVT_05_TEAM_GATE,
            "non_empty_teams_player_news": len(player_teams),
            "non_empty_teams_team_sentiment": len(team_teams),
            "evt_05_passed": player_pass and team_pass,
            "tool_results": {
                "getPlayerNews": {
                    "endpoint": "/api/news/feed",
                    "params": {"season": season, "limit": feed_limit},
                    "unique_teams": sorted(player_teams),
                    "team_count": len(player_teams),
                    "gate": EVT_05_PLAYER_GATE,
                    "passed": player_pass,
                },
                "getTeamSentiment": {
                    "endpoint": "/api/news/team-events",
                    "params": {"season": season, "weeks": list(weeks)},
                    "unique_teams": sorted(team_teams),
                    "team_count": len(team_teams),
                    "gate": EVT_05_TEAM_GATE,
                    "passed": team_pass,
                },
            },
        }
    ```

    Use `__file__` for the SHA lookup. Do NOT modify the CLI parser, the probes (`_probe_player_news`, `_probe_team_sentiment`), or `main()`.
  </action>
  <verify>
    <automated>python -c "import scripts.audit_advisor_tools_evt05 as m; p = m._build_payload(base_url='x', season=2025, weeks=(17,18), feed_limit=200, player_teams=set(), team_teams=set()); assert 'script_provenance' in p, list(p.keys()); assert set(p['script_provenance'].keys()) == {'sha', 'dirty', 'resolved_at'}, p['script_provenance']; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "from src.utils import get_script_sha" scripts/audit_advisor_tools_evt05.py` returns exactly one match
    - `grep -n '"script_provenance"' scripts/audit_advisor_tools_evt05.py` returns exactly one match
    - Direct call `_build_payload(...)` returns a dict with `script_provenance` key whose value has keys `{sha, dirty, resolved_at}`
    - `python scripts/audit_advisor_tools_evt05.py --help` succeeds
    - The historical file `.planning/milestones/v7.1-phases/72-event-flag-expansion/audit/advisor_tools_72.json` is unchanged on disk
  </acceptance_criteria>
  <done>
    audit_advisor_tools_evt05.py imports get_script_sha and embeds `script_provenance` in _build_payload. Markdown output is not relevant — this script writes only JSON.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Add TOOL-AUDIT.json sidecar to audit_advisor_tools.py with script_provenance</name>
  <files>scripts/audit_advisor_tools.py</files>
  <read_first>
    - scripts/audit_advisor_tools.py (FULL FILE — focus on `write_audit_markdown` at line 457 and `main()` at line 582)
    - src/utils.py (confirm get_script_sha signature)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-01, D-02, D-03; specifically the discretion clause line 52 which lets the planner choose top-level vs nested key placement based on each script's existing structure)
  </read_first>
  <behavior>
    - Running the script writes BOTH `TOOL-AUDIT.md` (existing) AND `TOOL-AUDIT.json` (new sibling, same parent dir, only the suffix differs)
    - The new JSON contains: `audited_at`, `script_provenance`, `base_url`, `auth_header_present`, `summary` (pass/warn/fail counts), and `results` (the existing per-tool list-of-dicts already produced by `run_audit()`)
    - The existing markdown output is unchanged in content and location
    - The CLI signature is unchanged — no new flags
  </behavior>
  <action>
    Make three surgical edits to `scripts/audit_advisor_tools.py`:

    **Edit 1 — Add imports.** In the existing import block (near line 36 where `import httpx` is), add:
    ```python
    import json
    from src.utils import get_script_sha
    ```
    (`json` is not currently imported; the script writes only markdown today.)

    **Edit 2 — Add a new `write_audit_json` function** immediately after `write_audit_markdown` (after line 552). Insert:

    ```python
    def write_audit_json(
        results: list[dict[str, Any]],
        out_path: Path,
        *,
        base_url: str,
        auth_header_present: bool,
    ) -> None:
        """Write the TOOL-AUDIT.json sidecar with provenance + structured results.

        Sibling of ``TOOL-AUDIT.md``; same parent directory, ``.json`` suffix.
        Phase 84 DEPLOY-04 consumes ``script_provenance.sha`` from this file
        to gate audit evidence (Phase 79 DQ-01 contract).
        """
        pass_count = sum(1 for r in results if r["verdict"] == PASS)
        warn_count = sum(1 for r in results if r["verdict"] == WARN)
        fail_count = sum(1 for r in results if r["verdict"] == FAIL)

        payload: dict[str, Any] = {
            "audited_at": datetime.now(timezone.utc).isoformat(),
            "script_provenance": get_script_sha(__file__),
            "base_url": base_url,
            "auth_header_present": auth_header_present,
            "summary": {
                "pass": pass_count,
                "warn": warn_count,
                "fail": fail_count,
                "total": len(results),
            },
            "results": results,
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    ```

    **Edit 3 — Wire the new writer into `main()`.** In `main()` (around line 627 where `write_audit_markdown` is called), append a call to `write_audit_json` immediately after. Replace the existing block:

    ```python
        write_audit_markdown(
            results,
            args.output,
            base_url=base_url,
            auth_header_present=bool(api_key),
        )

        summary = f"AUDIT: {pass_count} PASS / {warn_count} WARN / {fail_count} FAIL"
        print(summary)
        log.info("Wrote %s", args.output)
    ```

    with:

    ```python
        write_audit_markdown(
            results,
            args.output,
            base_url=base_url,
            auth_header_present=bool(api_key),
        )
        json_output = args.output.with_suffix(".json")
        write_audit_json(
            results,
            json_output,
            base_url=base_url,
            auth_header_present=bool(api_key),
        )

        summary = f"AUDIT: {pass_count} PASS / {warn_count} WARN / {fail_count} FAIL"
        print(summary)
        log.info("Wrote %s", args.output)
        log.info("Wrote %s", json_output)
    ```

    Do NOT change `DEFAULT_OUTPUT_PATH`, `--output` arg semantics, or `write_audit_markdown` itself. The JSON path is derived: if the user passes `--output foo/bar.md`, the JSON lands at `foo/bar.json`.
  </action>
  <verify>
    <automated>python -c "import json, tempfile; from pathlib import Path; import scripts.audit_advisor_tools as m; tmp = Path(tempfile.mkdtemp()) / 'TOOL-AUDIT.json'; m.write_audit_json([{'verdict': 'PASS', 'tool_name': 't', 'endpoint': '/x', 'status_code': 200, 'latency_ms': 10, 'category': 'OK', 'reason': 'ok', 'sample': '', 'body_keys': '', 'error': '', 'params': {}}], tmp, base_url='x', auth_header_present=False); data = json.loads(tmp.read_text()); assert 'script_provenance' in data; assert set(data['script_provenance'].keys()) == {'sha', 'dirty', 'resolved_at'}; assert data['summary']['pass'] == 1; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "from src.utils import get_script_sha" scripts/audit_advisor_tools.py` returns exactly one match
    - `grep -n "def write_audit_json(" scripts/audit_advisor_tools.py` returns exactly one match
    - `grep -n "with_suffix(\".json\")" scripts/audit_advisor_tools.py` returns at least one match (in main())
    - `grep -n "TOOL-AUDIT" scripts/audit_advisor_tools.py` shows references to BOTH the .md and .json sibling outputs
    - `python scripts/audit_advisor_tools.py --dry-run` exits 0 (sanity check on TOOL_REGISTRY still passes)
    - Direct call to `write_audit_json` produces a JSON file with `script_provenance.sha`, `script_provenance.dirty`, `script_provenance.resolved_at` keys
  </acceptance_criteria>
  <done>
    audit_advisor_tools.py imports get_script_sha and json, defines write_audit_json, and main() writes both TOOL-AUDIT.md and TOOL-AUDIT.json. Pre-existing markdown content unchanged.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Add unit tests asserting script_provenance is embedded in all three audit script payloads</name>
  <files>tests/test_audit_script_provenance.py</files>
  <read_first>
    - scripts/audit_event_coverage.py (after Task 1 edits applied)
    - scripts/audit_advisor_tools_evt05.py (after Task 2 edits applied)
    - scripts/audit_advisor_tools.py (after Task 3 edits applied)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-08 forward-only constraint)
  </read_first>
  <behavior>
    - Test 1 verifies `audit_event_coverage._build_json_payload(...)` includes `script_provenance` with `{sha, dirty, resolved_at}` keys
    - Test 2 verifies `audit_advisor_tools_evt05._build_payload(...)` includes the same `script_provenance` key with the same shape
    - Test 3 verifies `audit_advisor_tools.write_audit_json(...)` writes a file containing `script_provenance` with the correct shape
    - Test 4 verifies the historical v7.1 audit JSONs have NOT been backfilled (D-08): the on-disk `event_coverage.json` and `advisor_tools_72.json` either lack the `script_provenance` key OR the test is skipped when the historical files are absent locally — must NOT fail just because the file lacks the field
  </behavior>
  <action>
    Create `tests/test_audit_script_provenance.py`:

    ```python
    """Tests asserting Phase 79 DQ-01 contract — every audit-script JSON payload
    embeds a script_provenance block with {sha, dirty, resolved_at} keys.

    Also asserts D-08: historical v7.1 audit JSONs are NOT backfilled in place.
    """

    from __future__ import annotations

    import json
    import tempfile
    from pathlib import Path

    import pytest

    PROVENANCE_KEYS = {"sha", "dirty", "resolved_at"}


    def _assert_provenance(provenance: dict) -> None:
        assert isinstance(provenance, dict), provenance
        assert set(provenance.keys()) == PROVENANCE_KEYS, provenance
        assert isinstance(provenance["sha"], str)
        assert provenance["sha"] == "unknown" or len(provenance["sha"]) == 40
        assert isinstance(provenance["dirty"], bool)
        assert isinstance(provenance["resolved_at"], str)


    # -----------------------------------------------------------------------
    # 1. audit_event_coverage._build_json_payload
    # -----------------------------------------------------------------------
    def test_event_coverage_payload_has_script_provenance() -> None:
        from scripts.audit_event_coverage import _build_json_payload

        payload = _build_json_payload(
            base_url="https://example.test",
            season=2025,
            weeks=(17, 18),
            rows=[],
            teams_with_events=0,
            passed=False,
        )

        assert "script_provenance" in payload, list(payload.keys())
        _assert_provenance(payload["script_provenance"])


    # -----------------------------------------------------------------------
    # 2. audit_advisor_tools_evt05._build_payload
    # -----------------------------------------------------------------------
    def test_evt05_payload_has_script_provenance() -> None:
        from scripts.audit_advisor_tools_evt05 import _build_payload

        payload = _build_payload(
            base_url="https://example.test",
            season=2025,
            weeks=(17, 18),
            feed_limit=200,
            player_teams=set(),
            team_teams=set(),
        )

        assert "script_provenance" in payload, list(payload.keys())
        _assert_provenance(payload["script_provenance"])


    # -----------------------------------------------------------------------
    # 3. audit_advisor_tools.write_audit_json
    # -----------------------------------------------------------------------
    def test_advisor_tools_json_sidecar_has_script_provenance(tmp_path: Path) -> None:
        from scripts.audit_advisor_tools import write_audit_json

        out = tmp_path / "TOOL-AUDIT.json"
        write_audit_json(
            results=[
                {
                    "verdict": "PASS",
                    "tool_name": "getX",
                    "endpoint": "/api/x",
                    "status_code": 200,
                    "latency_ms": 12,
                    "category": "OK",
                    "reason": "ok",
                    "sample": "",
                    "body_keys": "",
                    "error": "",
                    "params": {},
                }
            ],
            out_path=out,
            base_url="https://example.test",
            auth_header_present=False,
        )

        data = json.loads(out.read_text())
        assert "script_provenance" in data, list(data.keys())
        _assert_provenance(data["script_provenance"])
        assert data["summary"] == {"pass": 1, "warn": 0, "fail": 0, "total": 1}


    # -----------------------------------------------------------------------
    # 4. D-08 forward-only — historical v7.1 audit JSONs not backfilled
    # -----------------------------------------------------------------------
    HISTORICAL_PATHS = [
        Path(".planning/milestones/v7.1-phases/72-event-flag-expansion/audit/event_coverage.json"),
        Path(".planning/milestones/v7.1-phases/72-event-flag-expansion/audit/advisor_tools_72.json"),
    ]


    @pytest.mark.parametrize("rel_path", HISTORICAL_PATHS, ids=lambda p: p.name)
    def test_historical_audit_json_not_backfilled(rel_path: Path) -> None:
        """D-08: existing v7.1 evidence is preserved untouched. The Phase 79
        code change must not retroactively stamp these files. We assert that
        if the file exists, it does NOT contain script_provenance — i.e. the
        only re-stamping pathway is a fresh audit run, not an in-place edit.
        """
        if not rel_path.exists():
            pytest.skip(f"Historical evidence file not present locally: {rel_path}")

        data = json.loads(rel_path.read_text())
        assert "script_provenance" not in data, (
            f"D-08 violated: {rel_path} was backfilled in place. "
            "Phase 79 is forward-only — re-stamping happens only on fresh audit runs."
        )
    ```

    Place at `tests/test_audit_script_provenance.py`.
  </action>
  <verify>
    <automated>python -m pytest tests/test_audit_script_provenance.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_audit_script_provenance.py` exists
    - `pytest tests/test_audit_script_provenance.py -x -q` exits 0 with at least 5 tests collected (3 payload tests + 2 parametrised D-08 tests, the latter may skip locally)
    - The D-08 test FAILS LOUDLY if a historical file ever gains `script_provenance` (regression guard)
    - Tests do NOT hit the network — `_build_json_payload` and `_build_payload` are pure functions; `write_audit_json` writes to a tmp_path
  </acceptance_criteria>
  <done>
    Five tests pass: three confirming each script's payload builder embeds `script_provenance` with the correct shape, and two parametrised tests guarding D-08 forward-only invariant.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| audit script → src.utils.get_script_sha | Helper trusted (landed Plan 79-01 with shell-safe subprocess invocations and timeout handling) |
| audit script → fresh JSON file write | Output written to local filesystem under `.planning/...`. Existing audit-script behaviour. |
| Phase 84 consumer → audit JSON | Future contract: Phase 84 reads `script_provenance.sha` to gate evidence. This plan is the producer half. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-79-05 | I (Information Disclosure) — over-sharing in JSON | `script_provenance` field in audit JSON | accept | Field carries only `{sha, dirty, resolved_at}`. SHA is public-by-design (already in commit graph). dirty bool reveals only "uncommitted local edits exist", not their content. resolved_at is a wall-clock UTC timestamp. No file paths beyond what audit JSONs already contain. |
| T-79-06 | T (Tampering) — historical evidence rewrite | v7.1 audit JSONs on disk | mitigate | D-08 forward-only: code change does not modify existing files at import or run time. Test 4 in this plan FAILS if a future re-run silently stamps the historical files. |
| T-79-07 | R (Repudiation) — fresh audit JSON without provenance | Audit re-run after this plan ships | mitigate | All three audit-script payload builders ALWAYS call `get_script_sha(__file__)`. There is no opt-out flag. Phase 84's consumer can therefore treat "missing script_provenance" as "pre-Phase-79 evidence — manual review" with confidence. |
</threat_model>

<verification>
- All three audit scripts import `get_script_sha` from `src.utils`
- `_build_json_payload` (audit_event_coverage), `_build_payload` (audit_advisor_tools_evt05), and `write_audit_json` (audit_advisor_tools) all embed `script_provenance` with `{sha, dirty, resolved_at}` keys
- All four pytest tests pass: `pytest tests/test_audit_script_provenance.py -x -q`
- Existing test suites do not regress: `pytest tests/test_get_script_sha.py tests/test_news_router_live.py -x -q`
- D-08 forward-only: `git status` reports no modifications to `.planning/milestones/v7.1-phases/72-event-flag-expansion/audit/*.json`
- `python scripts/audit_event_coverage.py --help`, `python scripts/audit_advisor_tools_evt05.py --help`, `python scripts/audit_advisor_tools.py --dry-run` all exit 0
</verification>

<success_criteria>
- A fresh run of any of the three audit scripts (or direct call to its payload builder) produces JSON whose top-level keys include `script_provenance`
- The `script_provenance` block has exactly three keys: `sha`, `dirty`, `resolved_at`
- `audit_advisor_tools.py` writes both `TOOL-AUDIT.md` (preserved) and `TOOL-AUDIT.json` (new) on every run
- Historical v7.1 audit JSONs are unchanged on disk
- Phase 84 DEPLOY-04 has a uniform consumer surface across all three audit scripts (same `script_provenance.sha` field shape)
</success_criteria>

<output>
After completion, create `.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-02-SUMMARY.md` capturing:
- Three call sites wired
- New JSON sidecar path: `.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT.json`
- Test count + pass status
- Any deviation from action text (with rationale)
- Confirmation that v7.1 audit JSONs are untouched (D-08)
</output>
