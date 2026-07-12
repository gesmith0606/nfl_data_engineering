---
sketch: 004
name: mobile-rankings-shell
question: "Do the dense table (003) and app shell (002) compose at 375px, and how does the 6-IA-in-5-tabs overflow resolve?"
winner: "C"
tags: [mobile, rankings, consistency, nav, tab-overflow]
---

# Sketch 004: Mobile Rankings Shell

## Design Question
Consistency check: the 003 Broadcast Table won at desktop and the 002 App Shell won
with placeholder content — they've never been seen together. A 6-column table can't
fit 375px, and the tab bar still has 6 IA items fighting for 5 slots. This sketch
tests both open decisions at once: the column strategy and the overflow strategy.

## How to View
open .planning/sketches/004-mobile-rankings-shell/index.html

Phone frames again — scroll inside. Position filters and the scoring sheet (⚙︎)
work in every variant.

## Variants
- **A: Essential Columns + "More" Tab** — table collapses to RK/Player/Δ/Proj;
  floor·ceil, tier, and stack move into the tap-to-expand row (same conformal band
  as desktop). Overflow: 5th tab is "⋯ More" opening a sheet with Draft Room /
  My League / News / Matchups.
- **B: Two-Line Rows + League Priority** — each row carries two lines (name+pos,
  then band·tier·Δ) with a mint proj panel; nothing hidden, no expansion needed.
  Overflow: My League takes the 4th slot (power users), Scores moves to More.
- **C: Pan Table + Seasonal Tabs** — the full 6-column desktop table survives by
  panning horizontally with a sticky player column. Overflow: the tab set is
  seasonal — Draft occupies a slot Jul–Sep, Scores replaces it in-season (no More).

## What to Look For
- Column strategy: hide-then-expand (A) vs always-visible two-liner (B) vs pan (C).
  B shows everything but rows get tall; C keeps desktop parity but sideways
  scrolling on data tables is divisive.
- Overflow strategy: universal More sheet (A) vs priority swap (B) vs seasonal
  swap (C). Which matches how you'd actually use it in August vs November?
- Tap a row in A — is the expandable conformal band still pleasant at this size?
