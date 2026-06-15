# Phase 89 — ESPN Live Draft Capture Spike (ESPN-01)

**Date:** 2026-06-15
**Author:** Phase 89 spike (Claude Code)
**Requirement:** ESPN-01 [SPIKE] — gates ESPN-02 / ESPN-03
**Time-box:** feasibility investigation, web-evidence based (no live ESPN draft was in
progress to test against; conclusions rest on the maintainer of the canonical Python
library plus every working open-source/commercial implementation found).

---

## Verdict: **NO-GO** for an automated ESPN live-capture adapter

> ESPN serves its live draft room from a **separate, non-public realtime backend**, and
> the documented REST view (`mDraftDetail`) **does not reflect picks until after the
> draft completes** — confirmed directly by the maintainer of `cwendt94/espn-api`. The
> *only* mechanisms that capture picks live are **brittle browser/DOM scrapers** (Selenium
> + XPATHs, or a Chrome extension), which are self-described as "VERY brittle," break on
> any ESPN UI change, require a logged-in browser, and carry ToS risk. None of the three
> evaluated mechanisms clears the bar for a maintainable, shippable `EspnAdapter`.

**Chosen mechanism (NO-GO path):** ESPN is supported via the **existing manual-entry
fallback (D-09)** in `scripts/draft_live.py` (`--manual` / `--add-pick`). No automated
adapter is built. An honest, gated `EspnAdapter` *stub* is registered so the platform is
visible but fails loudly with guidance, rather than pretending to work.

---

## Mechanism (a): Poll REST `mDraftDetail` during a live draft

**Endpoint:**
`…/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{leagueId}?view=mDraftDetail`

**Finding: NO-GO — the REST view is post-draft only.**

The clearest evidence is from **cwendt94**, the maintainer of `cwendt94/espn-api` (the de
facto Python ESPN fantasy library, used by ffverse and most downstream tooling), replying
directly to "Can I use this for the live ESPN Draft?" (issue #558, opened 2024-08-22):

> "Unfortunately you cannot. Currently ESPN uses **different APIs for the live draft so the
> data won't reflect correctly until afterwards.** I tried looking into it last year and
> was not able to get it working live."
> — cwendt94, github.com/cwendt94/espn-api/issues/558

Implications:

- `mDraftDetail` (and `espn-api`'s `League.draft` / `Pick` objects built on it) is
  **post-draft only**. Polling it during a live draft returns stale / empty pick data.
- The live draft room is powered by a different, undocumented realtime backend (the
  community has never published a stable polling endpoint or websocket spec for it). The
  endpoint gist (nntrn) lists `mDraftDetail` among static views with **no live/realtime
  variant and no websocket** documented.
- "Latency" is therefore not measurable in the useful sense — picks are simply **absent
  from the REST surface until the draft finishes**, so there is no latency figure to GO on.

**Verdict (a): NO-GO.** The only officially-shaped REST path does not carry live picks.

## Mechanism (b): Playwright / DOM watcher of the live draft room

**Finding: NO-GO for a shippable adapter — works, but is irreducibly brittle.**

Every open-source tool that *does* capture ESPN picks live does it by scraping the draft
room DOM, and each one warns about fragility:

- **ianfinley89/espn-ffassistant** — Selenium + Firefox WebDriver scraping the live draft
  room. README, verbatim: *"The way I pull the data is VERY brittle, any change would break
  the methods for getting the XPATH."* Requires interactive ESPN login in the driven
  browser; relies on general XPATHs.
- **Zinkelburger/Fantasy-Football-Tool** — a **browser extension** that pushes scraped
  players to a local HTTP server. Same class of approach (client-side DOM capture).
- **PickPulse / DraftKick / Fantasy Draft Helper** (commercial Chrome extensions) — all
  ESPN "live sync" is delivered as a **browser extension running inside the draft room**,
  not via an API. FantasyPros' own Draft Wizard supports ESPN live only through a browser
  extension; without it ESPN is *Manual Draft Assistant only* — the same conclusion this
  spike reaches independently.

Why this is a NO-GO for *our* adapter (vs. for a hobby script):

- **Brittleness is structural, not incidental.** ESPN ships UI changes regularly; an
  XPATH/selector watcher breaks silently mid-draft — the single worst failure mode for a
  draft-night tool (you find out when you're on the clock). The maintenance burden is
  "re-reverse-engineer the DOM before every season, and possibly mid-season."
- **It needs a driven, logged-in browser** (Playwright/Selenium with the operator's ESPN
  session) running alongside the draft — heavy operational surface vs. Sleeper's no-auth
  poll and Yahoo's official OAuth API.
- **It contradicts D-08's spirit:** the adapter would be a screen-scraper, not a data
  client; its "normalized pick event" is reconstructed from rendered text, with no stable
  player_id (ESPN's internal ids are not exposed cleanly in the DOM), making the ≥90%
  skill-mapping bar (ESPN-02) fragile too.
- **A half-built DOM scraper is exactly what this phase is instructed not to merge.**

A DOM watcher is *technically possible* (the hobby tools prove it), which is why this is a
deliberate engineering NO-GO rather than an impossibility — the cost/reliability tradeoff
fails for a tool whose whole value is being reliable on the one night it's used.

**Verdict (b): NO-GO.** Feasible but unmaintainable and ToS-risky; not shippable.

## Mechanism (c): `espn_s2` + `SWID` cookie auth for private leagues

**Finding: NO-GO as a live-capture mechanism (it solves a different problem).**

- `espn_s2` + `SWID` are the standard cookies for reading **private** league data through
  the **REST v3 API** (ffverse/ffscrapr and `espn-api` both document this). They
  authenticate access to the *post-draft* REST surface — i.e. mechanism (a), which is
  already NO-GO for live picks.
- The cookies **cannot be obtained programmatically** — they must be harvested manually
  from a logged-in browser (DevTools → Application → Cookies, or a "ESPN Cookie Finder"
  extension). Expiry is not officially documented; community reports treat them as
  long-lived but **silently rotating/expiring**, requiring periodic manual re-harvest —
  another draft-night failure mode.
- Crucially, **cookies do not unlock live picks.** Auth only widens *which* leagues the
  REST view can read; it does not make the REST view carry in-progress picks, because the
  live draft runs on the separate realtime backend (per mechanism (a)).

**Verdict (c): NO-GO.** Necessary only for private post-draft reads; irrelevant to the
live-capture problem and adds manual-secret fragility.

---

## `cwendt94/espn-api` library assessment

- It is the standard Python ESPN fantasy client and **its draft support is post-draft
  only** — confirmed by the maintainer (issue #558). It's excellent for importing a
  completed draft, league settings (`settings.scoring_type` distinguishes PPR/STD/custom),
  rosters, and historical data; it is **not** a live-draft data source.
- Conclusion: even adopting the best-in-class library does not yield live capture. This
  reinforces the NO-GO — the gap is in ESPN's platform, not in our tooling choice.

## ToS & risk

- The v3 fantasy endpoints and `espn_s2`/`SWID` flows are **reverse-engineered / undocumented**;
  ESPN provides **no official public fantasy API or developer program**. Using them is at
  ESPN's discretion and can break without notice.
- DOM/Selenium scraping and browser extensions operating the draft room push further into
  ToS-gray territory (automated interaction with the authenticated site).
- For a **personal, read-only, manual-paced** co-pilot the practical risk is low, but it is
  non-zero and uncontrollable — another reason to prefer the manual-entry path that touches
  no ESPN endpoint at all.

---

## Decision & consequences (NO-GO path → ESPN-02 / ESPN-03)

1. **No automated `EspnAdapter` is built.** (ESPN-02 GO path is not triggered.)
2. **ESPN's supported path is the manual-entry fallback (D-09)** already in
   `scripts/draft_live.py` (`--manual --teams N --my-slot S --add-pick "Name" …`). This is
   verified by `tests/test_espn_fallback.py`, which drives an ESPN-style draft through
   `build_manual_state(...)` + the live engine and asserts correct board/roster/turn state
   and ≥90% skill-position mapping onto projections (ESPN-03).
3. **An honest, gated `EspnAdapter` stub** (`src/espn_adapter.py`) conforms to the
   `DraftAdapter` protocol so the platform is registerable, but `load_state()` raises
   `NotImplementedError("ESPN live capture unsupported — use --manual; see
   89-SPIKE-FINDINGS.md")` and `resolve_draft()` returns `{found: False}`. This makes the
   gating *visible and loud* rather than a silent omission, and gives a single seam to drop
   a real implementation into if ESPN ever ships a live API. Covered by
   `tests/test_espn_adapter_stub.py`.
4. **Re-evaluation trigger:** revisit only if ESPN publishes an official live draft API, or
   if a maintained library exposes a stable live endpoint. A DOM watcher remains explicitly
   out of scope as un-shippable for a draft-night tool.

---

## Sources

- cwendt94/espn-api issue #558 — "Can I use this for the live ESPN Draft?" (maintainer:
  live uses different APIs, REST won't reflect picks until afterwards):
  https://github.com/cwendt94/espn-api/issues/558
- cwendt94/espn-api (library, post-draft draft support): https://github.com/cwendt94/espn-api
- ianfinley89/espn-ffassistant ("VERY brittle" Selenium/XPATH live scraper):
  https://github.com/ianfinley89/espn-ffassistant
- Zinkelburger/Fantasy-Football-Tool (browser-extension DOM capture):
  https://github.com/Zinkelburger/Fantasy-Football-Tool
- ESPN v3 endpoint list (no live/websocket draft variant documented):
  https://gist.github.com/nntrn/ee26cb2a0716de0947a0a4e9a157bc1c
- ffverse/ffscrapr ESPN private-league authentication (espn_s2/SWID, manual harvest):
  https://ffscrapr.ffverse.com/articles/espn_authentication.html
- cwendt94/espn-api Discussion #150 — ESPN_S2 & SWID credentials:
  https://github.com/cwendt94/espn-api/discussions/150
- FantasyPros Draft Wizard (ESPN live = browser extension; else Manual Assistant):
  https://draftwizard.fantasypros.com/football/draft-assistant/
- PickPulse (ESPN live sync delivered as a Chrome extension): https://www.pick-pulse.com/
