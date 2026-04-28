---
phase: 79
slug: audit-provenance-version-probe
status: secured
threats_total: 16
threats_closed: 16
threats_open: 0
audit_date: 2026-04-27
asvs_level: standard
---

# Phase 79 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| caller → get_script_sha argument | Audit script (or future caller) supplies a `script_path` string; treated as untrusted-by-default | Filesystem path (string), potentially user-influenced |
| get_script_sha → git binary | Helper constructs the subprocess argv; git binary is OS-managed | git log SHA output, diff content (suppressed — only bool captured) |
| audit script → JSON output file | Audit scripts write provenance-stamped JSON to `.planning/` directory | sha, dirty bool, ISO-8601 timestamp |
| public internet → /api/version | Railway endpoint reachable by anyone with X-API-Key (or in dev mode without) | version string, full 40-char git SHA, build metadata, bool fields |
| runtime env vars → /api/version response body | RAILWAY_GIT_COMMIT_SHA, RAILWAY_DEPLOYMENT_ID, RAILWAY_GIT_COMMIT_TIMESTAMP, ANTHROPIC_API_KEY read at request time | git/deploy metadata (returned); ANTHROPIC_API_KEY (bool-only, value suppressed) |
| GitHub Actions runner → Railway public endpoint | Outbound HTTPS polling to /api/version after every redeploy | version JSON (read-only probe) |
| GitHub-Actions secret RAILWAY_API_KEY → curl X-API-Key header | Standard GHA secret-injection; auto-masked in logs | API key credential |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-79-01 | T (Tampering) — argument injection | `get_script_sha` subprocess calls | mitigate | `shell=False`, list-form argv, literal `--` separator before path in BOTH `git log` and `git diff` calls | CLOSED |
| T-79-02 | I (Information Disclosure) — leaking git history | `get_script_sha` return value | accept | Returns only `{sha, dirty, resolved_at}` — no diff body, no env vars, no file contents | CLOSED-ACCEPTED |
| T-79-03 | D (Denial of Service) — hung git subprocess | `subprocess.run` calls | mitigate | `timeout=10` on both subprocess calls; `TimeoutExpired` caught and degrades to `sha='unknown'` | CLOSED |
| T-79-04 | D (Denial of Service) — missing git binary | `subprocess.run` calls | mitigate | `FileNotFoundError` and `OSError` caught; degrades to `sha='unknown'`, never raises | CLOSED |
| T-79-05 | I (Information Disclosure) — over-sharing in JSON | `script_provenance` field in audit JSON | accept | Field carries only `{sha, dirty, resolved_at}`; SHA is public-by-design (commit graph); dirty bool reveals only presence of uncommitted edits, not their content | CLOSED-ACCEPTED |
| T-79-06 | T (Tampering) — historical evidence rewrite | v7.1 audit JSONs on disk | mitigate | D-08 forward-only: no code path modifies existing files at import or run time; `test_historical_audit_json_not_backfilled` regression guard in `tests/test_audit_script_provenance.py` | CLOSED |
| T-79-07 | R (Repudiation) — fresh audit JSON without provenance | All three audit scripts on re-run | mitigate | All three payload builders always call `get_script_sha(__file__)`; no opt-out flag exists | CLOSED |
| T-79-08 | I (Information Disclosure) — ANTHROPIC_API_KEY leak | `/api/version` response | mitigate | Key read only via `bool(os.environ.get("ANTHROPIC_API_KEY"))`; `test_llm_enrichment_ready_reflects_anthropic_key_bool_only` asserts `secret not in resp.text` | CLOSED |
| T-79-09 | I (Information Disclosure) — git provenance disclosure | `git_sha`, `build_id`, `deployed_at` in /api/version response | accept | These fields are public-by-design (commit graph is public for this repo); prior endpoint already returned them (truncated); Phase 79 only removes truncation | CLOSED-ACCEPTED |
| T-79-10 | T (Tampering) — response shape drift | Phase 84 DEPLOY-02 consumer contract | mitigate | `VersionResponse` pydantic model + `TestVersion.test_version_shape_has_seven_keys` lock the 7-key contract; any schema change fails the test | CLOSED |
| T-79-11 | S (Spoofing) — endpoint accessibility for CI smoke | `/api/version` without X-API-Key | accept | `/api/version` is not in `_AUTH_EXEMPT_PATHS`; public probes without X-API-Key get 401; GHA smoke step sends the key via `secrets.RAILWAY_API_KEY` | CLOSED-ACCEPTED |
| T-79-12 | I (Information Disclosure) — RAILWAY_API_KEY in logs | curl invocation in smoke step | mitigate | Secret sourced via `${{ secrets.RAILWAY_API_KEY }}` (GHA auto-masks); passed via `-H` flag in conditional array `HEADER_ARGS`; never echoed directly; `curl -s` suppresses progress output | CLOSED |
| T-79-13 | D (Denial of Service) — runaway smoke loop | Polling while-loop in smoke step | mitigate | Hard 300s wall-clock budget via `date -u +%s` arithmetic; per-request `curl -m 10`; `sleep 15` between attempts | CLOSED |
| T-79-14 | T (Tampering) — wrong-job placement breaks pipeline | Smoke step job placement | mitigate | Step lives in `deploy-backend` AFTER the 120s wait (verified by Python YAML parse + `idx > 0` check in acceptance criteria); `continue-on-error: true` prevents the warn-only step from affecting downstream `live-gate-blocking` | CLOSED |
| T-79-15 | R (Repudiation) — silent failure | Smoke step timeout branch | mitigate | Timeout branch emits `::warning title=Railway /api/version SHA asymmetry::` with expected SHA, last-seen SHA, last HTTP code, and attempt count; visible on workflow summary page | CLOSED |
| T-79-16 | E (Elevation of Privilege) — token scope creep | Repo secrets for smoke step | accept | No new repo secret added; `RAILWAY_API_KEY` reused from existing set; `GITHUB_TOKEN` not used by this step | CLOSED-ACCEPTED |

---

## Evidence Index

| Threat ID | Evidence Location | Line(s) |
|-----------|-------------------|---------|
| T-79-01 | `src/utils.py` | 307–314 (`shell=False`, `"--"`, path as argv list element); 325–332 (same pattern in diff call) |
| T-79-01 | `tests/test_get_script_sha.py` | 109–126 (shell-safety mock test asserting both calls use list argv, `shell=False`, `--` separator) |
| T-79-02 | `src/utils.py` | 337 (return dict: `{"sha": sha, "dirty": dirty, "resolved_at": resolved_at}` — exactly 3 keys) |
| T-79-03 | `src/utils.py` | 313 (`timeout=10` on log call), 331 (`timeout=10` on diff call), 317 (`TimeoutExpired` caught) |
| T-79-04 | `src/utils.py` | 317 (`FileNotFoundError, subprocess.TimeoutExpired, OSError` caught), 334 (same in diff block) |
| T-79-05 | `scripts/audit_event_coverage.py` | 195 (`"script_provenance": get_script_sha(__file__)`) |
| T-79-05 | `scripts/audit_advisor_tools_evt05.py` | 164 (`"script_provenance": get_script_sha(__file__)`) |
| T-79-05 | `scripts/audit_advisor_tools.py` | 586 (`"script_provenance": get_script_sha(__file__)` in `write_audit_json`) |
| T-79-06 | `tests/test_audit_script_provenance.py` | `test_historical_audit_json_not_backfilled` (parametrised D-08 guard) |
| T-79-07 | `scripts/audit_event_coverage.py` | 46 (import), 195 (`get_script_sha(__file__)` — always called, no opt-out) |
| T-79-07 | `scripts/audit_advisor_tools_evt05.py` | 48 (import), 164 (`get_script_sha(__file__)` — always called) |
| T-79-07 | `scripts/audit_advisor_tools.py` | 42 (import), 586 (`get_script_sha(__file__)` in `write_audit_json` — always called from `main()`) |
| T-79-08 | `web/api/main.py` | 132 (`bool(os.environ.get("ANTHROPIC_API_KEY"))` — value never inserted into response) |
| T-79-08 | `tests/test_web_api.py` | 151 (`assert secret not in resp.text`) |
| T-79-09 | `web/api/main.py` | 135 (`git_sha=os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown")`) |
| T-79-10 | `web/api/models/schemas.py` | 345 (`class VersionResponse(BaseModel)` with 7 typed fields) |
| T-79-10 | `tests/test_web_api.py` | 99–119 (`TestVersion.test_version_shape_has_seven_keys` asserting `set(body.keys()) == EXPECTED_KEYS`) |
| T-79-11 | `web/api/main.py` | line 55 (`_AUTH_EXEMPT_PATHS` excludes `/api/version`); `.github/workflows/deploy-web.yml` line 184 (`RAILWAY_API_KEY` passed to smoke step) |
| T-79-12 | `.github/workflows/deploy-web.yml` | 184 (`${{ secrets.RAILWAY_API_KEY }}` — GHA auto-masked), 192–195 (conditional `HEADER_ARGS` array, secret in `-H` flag not echoed) |
| T-79-13 | `.github/workflows/deploy-web.yml` | 189 (`BUDGET_SECONDS=300`), 218 (`curl -m 10`), 190 (`POLL_INTERVAL=15`) |
| T-79-14 | `.github/workflows/deploy-web.yml` | 174 (step in `deploy-backend` job), 181 (`continue-on-error: true`) |
| T-79-15 | `.github/workflows/deploy-web.yml` | 212 (`::warning title=Railway /api/version SHA asymmetry::` with structured fields) |
| T-79-16 | `.github/workflows/deploy-web.yml` | 184 (`secrets.RAILWAY_API_KEY` — pre-existing secret, no new secret created) |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-79-01 | T-79-02 | `get_script_sha` return value contains only SHA (public-by-design: already in commit graph), a dirty bool (no diff content), and a UTC timestamp. No sensitive data crosses this boundary. | GSD security auditor | 2026-04-27 |
| AR-79-02 | T-79-05 | `script_provenance` JSON block carries the same three fields as AR-79-01. Audit JSONs live in `.planning/` which is committed to git — SHA is already part of the public commit history. | GSD security auditor | 2026-04-27 |
| AR-79-03 | T-79-09 | `git_sha`, `build_id`, and `deployed_at` were already returned by the prior `/api/version` endpoint (Phase 66). Phase 79 removes the `[:8]` truncation for clean Phase 84 equality checks. The commit graph is public for this repository; these fields carry no confidentiality requirement. | GSD security auditor | 2026-04-27 |
| AR-79-04 | T-79-11 | `/api/version` requires X-API-Key (not in `_AUTH_EXEMPT_PATHS`). Public internet probes without the key receive 401. The GHA smoke step holds `secrets.RAILWAY_API_KEY`. This is correct posture for a read-only metadata endpoint. | GSD security auditor | 2026-04-27 |
| AR-79-05 | T-79-16 | No new repository secret introduced. `RAILWAY_API_KEY` is a pre-existing secret reused from the existing live-gate scripts. GITHUB_TOKEN is not used by the smoke step. | GSD security auditor | 2026-04-27 |

---

## Unregistered Threat Flags

None. All threat flags from SUMMARY.md files map to registered threat IDs in the threat register above.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-27 | 16 | 16 | 0 | GSD security auditor (gsd-secure-phase) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (5 entries)
- [x] `threats_open: 0` confirmed
- [x] `status: secured` set in frontmatter

**Approval:** verified 2026-04-27
