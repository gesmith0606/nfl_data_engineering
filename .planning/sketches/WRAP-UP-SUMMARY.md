# Sketch Wrap-Up Summary

**Date:** 2026-07-12
**Sketches processed:** 1
**Design areas:** Layout & Marketing Home, Scorebug Component, Mecha Assistant
**Skill output:** `./.claude/skills/sketch-findings-nfl-data-engineering/`

## Included Sketches
| # | Name | Winner | Design Area |
|---|------|--------|-------------|
| 001 | home-hero-direction | B: Broadcast Overlay | Layout & Marketing Home; Scorebug Component; Mecha Assistant |

## Excluded Sketches
| # | Name | Reason |
|---|------|--------|
| — | none | — |

## Design Direction
Apple.com scroll grammar fused with FIFA26 broadcast scorebug identity; the dial sits
broadcast-forward (Variant B won over Apple Minimal and Dark Stadium Hybrid). Dark
stadium canvas, pitch-green field-gradient hero with the scorebug as the hero object,
broadcast nav with mint rule, condensed-caps identity type (Barlow Condensed) over
system-ui body, and a persistent full-body CSS mecha assistant (GX-01). Marketing home
leads with the provable accuracy claim — receipts shown, RB miss included.

## Key Decisions
- **Palette (sampled from reference frame):** near-black `#05070d` bars, mint `#91edd0`
  score panels with near-black digits, vibrant yellow `#ffd84d` accents (not gold),
  periwinkle `#5b67c7` ribbon CTAs, cyan `#22d3ee` mecha eyes, pitch greens
  `#2d5a27→#1a3a17`.
- **Typography:** system-ui/SF Pro body; Barlow Condensed 500–800 uppercase for all
  identity/display/component chrome.
- **Layout:** 52px broadcast nav (2px mint bottom rule) → 74vh field-gradient hero with
  yard lines → apple-style 96px-padded `.fsec` feature sections themed via `--sec-*`
  custom-property contract; IA = Draft Room / Rankings / Scores / News / Matchups /
  My League (no dashboard-first).
- **Scorebug:** pill with multicolor gradient outline, trophy-emblem separator, clock
  tab repurposed for our predicted line, periwinkle ribbon as CTA; `.compact` variant
  for prediction grids.
- **Mecha assistant:** GX-01 full-body clip-path CSS figure, fixed bottom-right,
  pulsing eyes/core, near-black chat panel; inspired-by, never literal Gundam.
- **Interaction:** 0.15s ease baseline, hover lifts, CTA press feedback, honest stat
  pills (wins in mint, RB +0.26 in muted gray "WIP").
