---
phase: 89-espn-draft-adapter
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: true
requirements: [ESPN-01, ESPN-02, ESPN-03]
files_created:
  - .planning/phases/89-espn-draft-adapter/89-SPIKE-FINDINGS.md
  - .planning/phases/89-espn-draft-adapter/89-01-espn-PLAN.md
  - src/espn_adapter.py
  - tests/test_espn_fallback.py
  - tests/test_espn_adapter_stub.py
files_modified: []

must_haves:
  truths:
    - "ESPN-01 spike produces a documented GO/NO-GO verdict with per-mechanism evidence and citations; verdict is NO-GO"
    - "Spike evaluates all three mechanisms: REST mDraftDetail polling, Playwright/DOM watcher, espn_s2/SWID cookie auth"
    - "REST mDraftDetail confirmed post-draft-only via cwendt94/espn-api maintainer (issue #558); not a live source"
    - "DOM watcher feasible but self-described VERY brittle by the only working OSS tool; not shippable for draft night"
    - "Cookie auth only gates post-draft REST reads; does not unlock live picks"
    - "NO-GO path: ESPN supported via manual-entry fallback (D-09) in scripts/draft_live.py"
    - "EspnAdapter stub conforms to DraftAdapter Protocol; load_state raises NotImplementedError with --manual guidance; resolve_draft returns {found: False}"
    - "tests/test_espn_fallback.py drives an ESPN-style draft through build_manual_state + LiveDraftEngine and asserts correct board/roster/turn state with >=90% skill-position mapping"
    - "tests/test_espn_adapter_stub.py asserts the stub conforms to DraftAdapter and exhibits its documented gated behavior"
    - "No fragile half-built scraper is merged; all new tests are @pytest.mark.unit and 100% offline"
    - "All new src/test files are black + flake8 (--max-line-length=100) clean"
  artifacts:
    - path: ".planning/phases/89-espn-draft-adapter/89-SPIKE-FINDINGS.md"
      provides: "ESPN-01 spike report with GO/NO-GO verdict, per-mechanism evidence, sources"
      contains: "NO-GO"
    - path: "src/espn_adapter.py"
      provides: "EspnAdapter stub conforming to DraftAdapter; honestly gated NO-GO registration seam"
      contains: "NotImplementedError"
    - path: "tests/test_espn_fallback.py"
      provides: "Offline proof that ESPN is assistable via the D-09 manual-entry fallback"
      contains: "build_manual_state"
    - path: "tests/test_espn_adapter_stub.py"
      provides: "Offline tests of the EspnAdapter stub's documented gated behavior"
      contains: "EspnAdapter"
  key_links:
    - from: "src/espn_adapter.py"
      to: "src/draft_adapter.py"
      via: "conforms to DraftAdapter Protocol"
      pattern: "DraftAdapter"
    - from: "src/espn_adapter.py"
      to: "src/draft_models.py"
      via: "load_state return type DraftState"
      pattern: "DraftState"
    - from: "tests/test_espn_fallback.py"
      to: "scripts/draft_live.py"
      via: "importlib load + build_manual_state"
      pattern: "build_manual_state"
    - from: "tests/test_espn_adapter_stub.py"
      to: "src/espn_adapter.py"
      via: "import EspnAdapter"
      pattern: "from src.espn_adapter import EspnAdapter"
---

<objective>
Decide whether live ESPN draft capture is feasible behind the DraftAdapter interface, and
deliver only what the evidence supports. ESPN has no official live API, so this phase is
SPIKE-FIRST: the primary deliverable is an honest GO/NO-GO verdict, not a fragile scraper.

Purpose: Close out the ESPN platform for v8.0 with an evidence-backed decision and a
guaranteed assistance floor, without merging un-shippable code.
Output: Spike report (89-SPIKE-FINDINGS.md), a gated EspnAdapter stub, and offline tests
proving the manual-entry fallback is the ESPN path.
</objective>

<spike_gate requirement="ESPN-01">
Investigate three live-capture mechanisms with web evidence:
(a) REST mDraftDetail polling during a live draft — latency / does it surface picks live?
(b) Playwright/DOM watcher of the live ESPN draft room.
(c) espn_s2 + SWID cookie auth for private leagues.
Also assess cwendt94/espn-api draft support and ToS/reliability risk.
RESULT (see 89-SPIKE-FINDINGS.md): **NO-GO.** All three fail the shippability bar; the
manual-entry fallback (D-09) is the supported ESPN path.
</spike_gate>

<tasks>
1. [ESPN-01] Run the feasibility spike; write 89-SPIKE-FINDINGS.md with per-mechanism
   evidence, citations, and a GO/NO-GO verdict. (DONE — verdict NO-GO.)
2. [ESPN-01] Record this GSD plan reflecting the spike gate and the NO-GO branch.
3. [ESPN-03 / NO-GO] Create tests/test_espn_fallback.py proving the D-09 manual fallback
   handles an ESPN-style draft (build_manual_state + LiveDraftEngine produce correct
   state; >=90% skill-position mapping). Offline, @pytest.mark.unit, importlib-loaded.
4. [ESPN-02 / honest gating] Create src/espn_adapter.py: EspnAdapter stub conforming to
   DraftAdapter, load_state -> NotImplementedError (--manual guidance), resolve_draft ->
   {found: False}, map_picks -> reuse map_picks_to_projections(player_index={}).
5. [ESPN-03] Create tests/test_espn_adapter_stub.py for the stub's documented behavior.
6. Run new tests (must pass); black + flake8 clean. Return integration instructions for
   optionally registering "espn" in _ADAPTERS (scripts/draft_live.py) — NOT applied here.
</tasks>

<constraints>
- CREATE ONLY NEW FILES. Do not edit existing files; return integration instructions.
- No git commit. Tests 100% offline (no network, no real ESPN cookies).
- Do NOT build a DOM scraper or any fragile live-capture path (NO-GO).
</constraints>
