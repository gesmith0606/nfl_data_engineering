---
phase: 79-audit-provenance-version-probe
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - web/api/main.py
  - web/api/models/schemas.py
  - tests/test_web_api.py
autonomous: true
requirements: [DQ-02]
must_haves:
  truths:
    - "GET /api/version returns a JSON body with exactly seven keys: version, git_sha, build_id, deployed_at, llm_enrichment_ready, has_team_events_route, has_player_badges_route"
    - "The git_sha field is the FULL 40-character RAILWAY_GIT_COMMIT_SHA value (no [:8] truncation) — or 'unknown' when the env var is unset"
    - "The llm_enrichment_ready field is bool(os.environ.get('ANTHROPIC_API_KEY')) — same logic as /api/health (web/api/main.py:104)"
    - "The two diagnostic route flags (has_team_events_route, has_player_badges_route) are preserved unchanged"
    - "ANTHROPIC_API_KEY value is NEVER returned or logged — only its presence as a bool"
  artifacts:
    - path: "web/api/main.py"
      provides: "Updated version_info() endpoint returning the 7-key shape with full SHA + llm_enrichment_ready"
      contains: "llm_enrichment_ready"
    - path: "web/api/models/schemas.py"
      provides: "Optional VersionResponse pydantic model for the upgraded shape"
      contains: "class VersionResponse"
    - path: "tests/test_web_api.py"
      provides: "Tests asserting the 7-key shape, full-SHA semantics, and llm_enrichment_ready logic"
      contains: "TestVersion"
  key_links:
    - from: "web/api/main.py::version_info"
      to: "RAILWAY_GIT_COMMIT_SHA env var"
      via: "os.environ.get without [:8] truncation"
      pattern: "RAILWAY_GIT_COMMIT_SHA"
    - from: "web/api/main.py::version_info"
      to: "ANTHROPIC_API_KEY env var (bool only)"
      via: "bool(os.environ.get('ANTHROPIC_API_KEY')) — mirrors /api/health"
      pattern: "ANTHROPIC_API_KEY"
---

<objective>
Upgrade `/api/version` so it returns the full 40-character `git_sha` and a new `llm_enrichment_ready` bool. The existing diagnostic route flags (`has_team_events_route`, `has_player_badges_route`) — which proved their worth during the v7.1 silent-freeze — stay.

This is the producer side of the asymmetry-detection capability. Phase 84 DEPLOY-02 reads this endpoint and asserts `git_sha == GITHUB_SHA` against the just-pushed commit. Truncating to 8 chars (current behaviour) makes that comparison ambiguous; the full SHA gives clean equality semantics. Per CONTEXT D-04, the 32-byte payload bump is trivial.

Per CONTEXT D-05: ANTHROPIC_API_KEY presence is exposed as a bool ONLY. Never return or log the value itself.

Output:
- `web/api/main.py::version_info()` returns the new 7-key shape
- `web/api/models/schemas.py` gains an optional `VersionResponse` pydantic model (for type safety; planner discretion per CONTEXT line 53)
- `tests/test_web_api.py` gains a `TestVersion` class with three tests
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md
@web/api/main.py
@web/api/models/schemas.py

<interfaces>
<!-- CURRENT shape (web/api/main.py lines 113-127) — TO BE REPLACED -->

```python
@app.get("/api/version", tags=["health"])
def version_info() -> dict:
    """Build and git metadata — proves which code is actually deployed."""
    return {
        "version": API_VERSION,
        "git_sha": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown")[:8],
        "build_id": os.environ.get("RAILWAY_DEPLOYMENT_ID", "unknown")[:8],
        "deployed_at": os.environ.get("RAILWAY_GIT_COMMIT_TIMESTAMP", "unknown"),
        "has_team_events_route": any(...),
        "has_player_badges_route": any(...),
    }
```

<!-- TARGET shape (per CONTEXT D-04 + D-05) -->

```python
{
    "version": "0.1.0",                                        # API_VERSION constant
    "git_sha": "<full 40-char SHA>" | "unknown",               # FULL — no [:8]
    "build_id": "<RAILWAY_DEPLOYMENT_ID>" | "unknown",         # also drop [:8] for consistency
    "deployed_at": "<RAILWAY_GIT_COMMIT_TIMESTAMP>" | "unknown",
    "llm_enrichment_ready": True | False,                      # NEW — bool(ANTHROPIC_API_KEY)
    "has_team_events_route": True | False,                     # preserved
    "has_player_badges_route": True | False,                   # preserved
}
```

<!-- /api/health source pattern to mirror (web/api/main.py:104) -->

```python
llm_ready = bool(os.environ.get("ANTHROPIC_API_KEY"))
```

<!-- Existing schemas.py reference (web/api/models/schemas.py:330) — DO NOT MODIFY HealthResponse -->

```python
class HealthResponse(BaseModel):
    status: str
    version: str
    db_status: Optional[str] = None
    llm_enrichment_ready: bool = Field(default=False, description="...")
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add VersionResponse pydantic model in web/api/models/schemas.py</name>
  <files>web/api/models/schemas.py</files>
  <read_first>
    - web/api/models/schemas.py (read lines 320-360 — HealthResponse definition; new VersionResponse goes adjacent to it as a sibling response model)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-04, D-05)
  </read_first>
  <behavior>
    - VersionResponse is a pydantic BaseModel with seven fields matching the target shape
    - Field types: version: str, git_sha: str, build_id: str, deployed_at: str, llm_enrichment_ready: bool, has_team_events_route: bool, has_player_badges_route: bool
    - Field-level docstrings document the contract Phase 84 will consume
    - The model is importable from `web.api.models.schemas`
  </behavior>
  <action>
    Append a new pydantic model to `web/api/models/schemas.py` immediately AFTER the existing `HealthResponse` class (after line 342). The model uses `Field(...)` descriptions so the OpenAPI schema documents the contract.

    ```python
    class VersionResponse(BaseModel):
        """Build and git metadata — proves which code is actually deployed.

        Phase 84 DEPLOY-02 polls this endpoint and asserts ``git_sha`` equals
        the just-pushed commit's GITHUB_SHA. Phase 79 ships the producer
        contract; Phase 84 promotes the smoke check to fail-on-mismatch.
        """

        version: str = Field(description="API_VERSION constant from web.api.config")
        git_sha: str = Field(
            description=(
                "Full 40-character RAILWAY_GIT_COMMIT_SHA, or the literal "
                "string 'unknown' when the env var is unset. Phase 79 D-04 "
                "explicitly drops the prior [:8] truncation so Phase 84's "
                "asymmetry probe can do a clean equality check against the "
                "40-char ${{ github.sha }} from GitHub Actions."
            )
        )
        build_id: str = Field(
            description=(
                "RAILWAY_DEPLOYMENT_ID, or 'unknown' when unset. Useful for "
                "distinguishing two deploys that share the same git_sha "
                "(e.g. Railway env-var-only redeploy)."
            )
        )
        deployed_at: str = Field(
            description=(
                "RAILWAY_GIT_COMMIT_TIMESTAMP (ISO-8601 from Railway), or "
                "'unknown' when unset."
            )
        )
        llm_enrichment_ready: bool = Field(
            default=False,
            description=(
                "True when ANTHROPIC_API_KEY is set in the runtime "
                "environment. Mirrors /api/health logic (Phase 66 / "
                "HOTFIX-01). The key value itself is NEVER returned or "
                "logged — only its presence as a bool."
            ),
        )
        has_team_events_route: bool = Field(
            description=(
                "True when the news router has the /team-events route "
                "registered. Diagnostic flag retained from Phase 66 — "
                "proved its worth during v7.1 silent-freeze."
            )
        )
        has_player_badges_route: bool = Field(
            description=(
                "True when the news router has a player-badges route "
                "registered. Diagnostic flag retained from Phase 66."
            )
        )
    ```

    Do NOT modify HealthResponse. Do NOT add any other models. The import at the top of schemas.py already covers `BaseModel` and `Field` (HealthResponse uses both).
  </action>
  <verify>
    <automated>python -c "from web.api.models.schemas import VersionResponse; m = VersionResponse(version='0.1.0', git_sha='a'*40, build_id='b', deployed_at='2026-04-27T12:00:00Z', llm_enrichment_ready=True, has_team_events_route=True, has_player_badges_route=False); assert m.git_sha == 'a'*40; assert m.llm_enrichment_ready is True; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "class VersionResponse" web/api/models/schemas.py` returns exactly one match
    - All seven fields are present — verifiable via `python -c "from web.api.models.schemas import VersionResponse; print(set(VersionResponse.model_fields.keys()))"` returning the set `{'version', 'git_sha', 'build_id', 'deployed_at', 'llm_enrichment_ready', 'has_team_events_route', 'has_player_badges_route'}`
    - The existing HealthResponse class is unchanged (verify via `grep -A 10 "class HealthResponse" web/api/models/schemas.py` — fields match the pre-edit state)
  </acceptance_criteria>
  <done>
    VersionResponse pydantic model exists in schemas.py with seven typed fields matching the CONTEXT D-04 + D-05 contract. HealthResponse untouched.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Upgrade /api/version endpoint in web/api/main.py</name>
  <files>web/api/main.py</files>
  <read_first>
    - web/api/main.py (FULL FILE — lines 95-127 contain /api/health and /api/version; the new endpoint mirrors /api/health's llm_enrichment_ready logic)
    - web/api/models/schemas.py (after Task 1 — confirm VersionResponse import path)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-04 full SHA, D-05 llm_enrichment_ready)
  </read_first>
  <behavior>
    - GET /api/version returns 200 with a JSON body matching VersionResponse exactly
    - git_sha is the full 40-char value of RAILWAY_GIT_COMMIT_SHA (or "unknown")
    - build_id is the FULL value of RAILWAY_DEPLOYMENT_ID (drop [:8] for consistency, per D-04 — full SHA principle generalises)
    - llm_enrichment_ready uses bool(os.environ.get("ANTHROPIC_API_KEY")) — same as /api/health line 104
    - The two diagnostic route flags continue to be derived from news.router.routes
    - The endpoint's response_model is set to VersionResponse so OpenAPI schema is generated correctly
  </behavior>
  <action>
    Make two edits to `web/api/main.py`:

    **Edit 1 — Update the import.** In the existing schemas import (line 16), add VersionResponse:
    ```python
    from .models.schemas import HealthResponse, VersionResponse
    ```

    **Edit 2 — Replace the version_info() function** (currently lines 113-127). Replace the entire function with:

    ```python
    @app.get("/api/version", response_model=VersionResponse, tags=["health"])
    def version_info() -> VersionResponse:
        """Build and git metadata -- proves which code is actually deployed.

        ``git_sha`` is the FULL 40-character RAILWAY_GIT_COMMIT_SHA (no
        truncation) so Phase 84's asymmetry probe can do a clean equality
        check against the 40-char GITHUB_SHA from GitHub Actions
        (Phase 79 D-04).

        ``llm_enrichment_ready`` mirrors /api/health -- True when
        ANTHROPIC_API_KEY is set in the runtime environment. The value is
        a bool; the key itself is never returned or logged
        (Phase 66 / HOTFIX-01, applied here per Phase 79 D-05).

        The two diagnostic route flags
        (``has_team_events_route``, ``has_player_badges_route``) are
        retained from Phase 66 -- they proved their worth catching the
        v7.1 silent-freeze.
        """
        llm_ready = bool(os.environ.get("ANTHROPIC_API_KEY"))
        return VersionResponse(
            version=API_VERSION,
            git_sha=os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown"),
            build_id=os.environ.get("RAILWAY_DEPLOYMENT_ID", "unknown"),
            deployed_at=os.environ.get("RAILWAY_GIT_COMMIT_TIMESTAMP", "unknown"),
            llm_enrichment_ready=llm_ready,
            has_team_events_route=any(
                getattr(r, "path", "") == "/team-events" for r in news.router.routes
            ),
            has_player_badges_route=any(
                "player-badges" in getattr(r, "path", "") for r in news.router.routes
            ),
        )
    ```

    Notes:
    - The `[:8]` truncation is REMOVED from both `git_sha` AND `build_id` (D-04 principle generalises — keep the full IDs so debug context is unambiguous; the payload bump is trivial)
    - Do NOT modify the existing `/api/health` endpoint (lines 95-110) — its shape is exercised by other consumers
    - Do NOT change route paths, tags, or middleware behaviour
    - The endpoint stays in `_AUTH_EXEMPT_PATHS`-equivalent territory by virtue of being part of the `health` tag — actually verify: `/api/version` is NOT currently in `_AUTH_EXEMPT_PATHS` (line 55) which lists only `/api/health`, `/api/docs`, `/api/openapi.json`. THE VERSION ENDPOINT IS NOT EXEMPT. Phase 84's CI smoke step (Plan 79-04) will need to send X-API-Key when API_KEY is set. Document this in the docstring? No — keep the endpoint function clean; the CI plan handles auth separately.
  </action>
  <verify>
    <automated>python -c "import os; os.environ.pop('ANTHROPIC_API_KEY', None); os.environ['RAILWAY_GIT_COMMIT_SHA'] = 'c'*40; from fastapi.testclient import TestClient; from web.api.main import app; r = TestClient(app).get('/api/version'); assert r.status_code == 200, r.text; b = r.json(); assert set(b.keys()) == {'version', 'git_sha', 'build_id', 'deployed_at', 'llm_enrichment_ready', 'has_team_events_route', 'has_player_badges_route'}, list(b.keys()); assert b['git_sha'] == 'c'*40, b['git_sha']; assert len(b['git_sha']) == 40; assert b['llm_enrichment_ready'] is False; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "VersionResponse" web/api/main.py` returns at least 2 matches (import + response_model + return statement)
    - `grep -n "RAILWAY_GIT_COMMIT_SHA" web/api/main.py` shows NO `[:8]` slice on the env-var read in version_info
    - `grep -n "ANTHROPIC_API_KEY" web/api/main.py` returns at least 2 matches (one in /api/health, one in /api/version) — never returned, only `bool(...)`-checked
    - `len(response_json["git_sha"]) == 40` when RAILWAY_GIT_COMMIT_SHA is a real 40-char value
    - Response keys are EXACTLY: `{version, git_sha, build_id, deployed_at, llm_enrichment_ready, has_team_events_route, has_player_badges_route}` — no more, no less
    - /api/health response shape is unchanged (verify via existing test_health_returns_ok in tests/test_web_api.py)
  </acceptance_criteria>
  <done>
    /api/version returns 200 with the 7-key VersionResponse shape. git_sha is full 40-char (or 'unknown'). llm_enrichment_ready mirrors /api/health logic and never leaks the key.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Add TestVersion class to tests/test_web_api.py</name>
  <files>tests/test_web_api.py</files>
  <read_first>
    - tests/test_web_api.py (FULL FILE — observe TestClient pattern in TestHealth class at line 85; new tests follow same shape)
    - web/api/main.py (after Task 2 — confirm endpoint behaviour)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-04, D-05)
  </read_first>
  <behavior>
    - Test 1 (shape): GET /api/version returns 200 and exactly the 7 expected keys
    - Test 2 (full SHA): when RAILWAY_GIT_COMMIT_SHA is set to a 40-char value, response.git_sha equals it (no truncation)
    - Test 3 (llm_enrichment_ready true/false): response.llm_enrichment_ready reflects bool(ANTHROPIC_API_KEY); the key itself NEVER appears in response body or stringified body
    - Test 4 (env unset): when RAILWAY_GIT_COMMIT_SHA is unset, response.git_sha is 'unknown'
  </behavior>
  <action>
    Add a new `TestVersion` class to `tests/test_web_api.py`. Place it AFTER the existing `TestHealth` class (after line 91). Use `monkeypatch` for env-var manipulation so tests do not leak state.

    Append:

    ```python
    # ---------------------------------------------------------------------------
    # Version
    # ---------------------------------------------------------------------------


    class TestVersion:
        """Phase 79 DQ-02 — /api/version contract tests.

        - Full 40-char git_sha (no [:8] truncation) — D-04
        - llm_enrichment_ready mirrors /api/health, never leaks the key — D-05
        - Seven-key shape locked for Phase 84 DEPLOY-02 consumer
        """

        EXPECTED_KEYS = {
            "version",
            "git_sha",
            "build_id",
            "deployed_at",
            "llm_enrichment_ready",
            "has_team_events_route",
            "has_player_badges_route",
        }

        def test_version_shape_has_seven_keys(self, monkeypatch):
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
            resp = client.get("/api/version")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert set(body.keys()) == self.EXPECTED_KEYS, list(body.keys())

        def test_git_sha_is_full_40_chars_when_env_set(self, monkeypatch):
            full_sha = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
            assert len(full_sha) == 40
            monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", full_sha)
            resp = client.get("/api/version")
            assert resp.status_code == 200
            body = resp.json()
            assert body["git_sha"] == full_sha
            assert len(body["git_sha"]) == 40

        def test_git_sha_is_unknown_when_env_unset(self, monkeypatch):
            monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
            resp = client.get("/api/version")
            assert resp.status_code == 200
            assert resp.json()["git_sha"] == "unknown"

        def test_llm_enrichment_ready_reflects_anthropic_key_bool_only(
            self, monkeypatch
        ):
            secret = "sk-ant-VERY-SECRET-VALUE-NEVER-LEAK"
            monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
            resp = client.get("/api/version")
            assert resp.status_code == 200
            body = resp.json()
            assert body["llm_enrichment_ready"] is True
            # CRITICAL: the secret value MUST NOT appear in the response body.
            assert secret not in resp.text, "ANTHROPIC_API_KEY value leaked into /api/version response"

            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
            resp2 = client.get("/api/version")
            assert resp2.status_code == 200
            assert resp2.json()["llm_enrichment_ready"] is False
    ```
  </action>
  <verify>
    <automated>python -m pytest tests/test_web_api.py::TestVersion -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_web_api.py` contains a `class TestVersion:` block (verify with `grep -n "class TestVersion" tests/test_web_api.py`)
    - `pytest tests/test_web_api.py::TestVersion -x -q` exits 0 with 4 tests passing
    - The full-SHA test asserts `len(body["git_sha"]) == 40` — guards against silent re-introduction of `[:8]` truncation
    - The llm_enrichment_ready test asserts `secret not in resp.text` — guards against any future code path that accidentally serialises the key
    - Existing `TestHealth.test_health_returns_ok` still passes: `pytest tests/test_web_api.py::TestHealth -x -q`
  </acceptance_criteria>
  <done>
    Four tests in TestVersion all pass. Full-SHA, key-shape, env-unset, and key-leak guards are exercised. Existing TestHealth is unaffected.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Public internet → /api/version | Endpoint is publicly reachable on Railway. May be hit by anyone with the X-API-Key (or anyone, in dev mode where API_KEY is empty). |
| Runtime env vars → response body | `RAILWAY_GIT_COMMIT_SHA`, `RAILWAY_DEPLOYMENT_ID`, `RAILWAY_GIT_COMMIT_TIMESTAMP`, `ANTHROPIC_API_KEY` are all read; the first three are returned as-is, the fourth is converted to a bool ONLY. |
| Phase 84 DEPLOY-02 consumer → endpoint response | Future contract; `git_sha` shape is the asymmetry-detection primitive. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-79-08 | I (Information Disclosure) — secret leak | `ANTHROPIC_API_KEY` in /api/version response | mitigate | Endpoint reads the env var ONLY through `bool(os.environ.get("ANTHROPIC_API_KEY"))`. The value is never inserted into the response or logged. Test 4 (`test_llm_enrichment_ready_reflects_anthropic_key_bool_only`) asserts the secret string does NOT appear in `resp.text` — regression guard. Mirrors the existing /api/health pattern (Phase 66 HOTFIX-01). |
| T-79-09 | I (Information Disclosure) — git provenance disclosure | `git_sha`, `build_id`, `deployed_at` in response | accept | git_sha is public-by-design (the commit graph is public for any open-source repo). build_id and deployed_at are Railway-internal identifiers with no security value beyond being a deploy fingerprint. The existing endpoint already returned all three (truncated); Phase 79 just removes the truncation. |
| T-79-10 | T (Tampering) — response shape drift | Phase 84 DEPLOY-02 consumer contract | mitigate | `VersionResponse` pydantic model + Test 1 (`test_version_shape_has_seven_keys`) lock the response shape. Any future change to `version_info()` that drops/adds keys without updating the model fails the test. |
| T-79-11 | S (Spoofing) — endpoint accessibility for CI smoke | /api/version while API_KEY is set on Railway | accept | The CI smoke step (Plan 79-04) sends `X-API-Key` with the same secret used to deploy. /api/version is NOT in `_AUTH_EXEMPT_PATHS`. This is correct posture — public-internet probes without the key get 401, the GHA smoke step has the key. |
</threat_model>

<verification>
- `from web.api.models.schemas import VersionResponse` works
- `client.get("/api/version")` returns 200 with exactly the 7 expected keys
- `git_sha` is full 40-char (or 'unknown') — no `[:8]` slice anywhere in the codepath
- `llm_enrichment_ready` is a Python bool reflecting `bool(os.environ.get("ANTHROPIC_API_KEY"))`
- ANTHROPIC_API_KEY value never appears in response body
- All 4 TestVersion tests pass: `pytest tests/test_web_api.py::TestVersion -x -q`
- TestHealth is unaffected: `pytest tests/test_web_api.py::TestHealth -x -q`
- Full API test suite still green: `pytest tests/test_web_api.py -x -q`
</verification>

<success_criteria>
- GET /api/version returns 200 with exactly seven keys: `{version, git_sha, build_id, deployed_at, llm_enrichment_ready, has_team_events_route, has_player_badges_route}`
- `git_sha` length is 40 chars when RAILWAY_GIT_COMMIT_SHA is set to a 40-char value
- `llm_enrichment_ready == bool(os.environ.get("ANTHROPIC_API_KEY"))` and the key value never leaks
- The two diagnostic route flags continue to function as before
- VersionResponse model is registered in OpenAPI schema (verify via `client.get("/api/openapi.json")` containing `"VersionResponse"`)
</success_criteria>

<output>
After completion, create `.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-03-SUMMARY.md` capturing:
- New 7-key response shape
- Confirmation that `[:8]` truncation is removed from BOTH git_sha and build_id
- Test count + pass status
- ANTHROPIC_API_KEY leak-guard test outcome
- Any deviations from action text
</output>
