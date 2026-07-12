# Sketch Wrap-Up Summary

**Date:** 2026-07-12 (two sessions same day)
**Sketches processed:** 3
**Design areas:** Layout & Marketing Home, Scorebug Component, Mecha Assistant, Mobile Shell, Data Tables & Interior Pages
**Skill output:** `./.claude/skills/sketch-findings-nfl-data-engineering/`

## Included Sketches
| # | Name | Winner | Design Area |
|---|------|--------|-------------|
| 001 | home-hero-direction | B: Broadcast Overlay | Layout & Marketing Home; Scorebug Component; Mecha Assistant |
| 002 | mobile-broadcast-hero | B: App Shell + Bottom Tabs | Mobile Shell |
| 003 | rankings-data-density | A: Broadcast Table | Data Tables & Interior Pages |

## Excluded Sketches
| # | Name | Reason |
|---|------|--------|
| — | none | — |

## Design Direction
Apple.com scroll grammar fused with FIFA26 broadcast scorebug identity; the dial sits
broadcast-forward (001-B). Dark stadium canvas, pitch-green field-gradient hero with the
scorebug as the hero object, broadcast nav with mint rule, condensed-caps identity type
(Barlow Condensed) over system-ui body, persistent full-body CSS mecha assistant (GX-01).
At mobile widths the site becomes an app shell (002-B): bottom tab bar with GX-01 as the
raised center tab, one-liner scorebug, bottom-sheet chat. Interior workhorse pages are
dense broadcast tables (003-A): yellow condensed headers over a mint rule, mint hero
numerals, shared position/scoring/search control bar, expandable conformal-band rows.
Marketing home leads with the provable accuracy claim — receipts shown, RB miss included.

## Key Decisions
- **Palette (sampled from reference frame):** near-black `#05070d` bars, mint `#91edd0`
  score panels with near-black digits, vibrant yellow `#ffd84d` accents (not gold),
  periwinkle `#5b67c7` ribbon CTAs, cyan `#22d3ee` mecha eyes, pitch greens
  `#2d5a27→#1a3a17`.
- **Typography:** system-ui/SF Pro body; Barlow Condensed 500–800 uppercase for all
  identity/display/component chrome; `tabular-nums` right-aligned in data columns.
- **Desktop layout:** 52px broadcast nav (2px mint rule) → 74vh field-gradient hero →
  apple-style 96px-padded `.fsec` sections themed via `--sec-*` contract; IA = Draft
  Room / Rankings / Scores / News / Matchups / My League (no dashboard-first).
- **Mobile shell:** bottom tab bar (64px) with GX-01 raised center puck; horizontal
  one-liner scorebug; bottom-sheet chat; horizontal stat scroller. Open: tab overflow
  (5 slots vs 6 IA items).
- **Interior data pages:** dense sortable table, yellow condensed headers, mint proj
  numerals, color-coded position tags, tier pills, click-to-expand conformal band +
  stack correlation chip. Tier headlines (003-B) reserved as a future grouping toggle.
- **Scorebug:** pill with multicolor gradient outline, trophy-emblem separator, clock
  tab = our predicted line, periwinkle ribbon CTA; `.compact` grid variant; mobile
  one-liner variant; stacked `.vbug` card preserved for deck/detail contexts.
- **Mecha assistant:** GX-01 full-body clip-path CSS figure on desktop, head-only puck
  on mobile; pulsing eyes/core; inspired-by, never literal Gundam.
- **Honesty as design principle:** wins in mint, RB +0.26 in muted gray "WIP" — never
  hidden.
