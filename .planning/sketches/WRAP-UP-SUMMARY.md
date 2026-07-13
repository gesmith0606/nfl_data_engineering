# Sketch Wrap-Up Summary

**Date:** 2026-07-12 → 2026-07-13 (three wrap-up sessions)
**Sketches processed:** 5
**Design areas:** Layout & Marketing Home, Scorebug Component, Mecha Assistant, Mobile Shell, Data Tables & Interior Pages, Scores & Graded Receipts
**Skill output:** `./.claude/skills/sketch-findings-nfl-data-engineering/`

## Included Sketches
| # | Name | Winner | Design Area |
|---|------|--------|-------------|
| 001 | home-hero-direction | B: Broadcast Overlay | Layout & Marketing Home; Scorebug Component; Mecha Assistant |
| 002 | mobile-broadcast-hero | B: App Shell + Bottom Tabs | Mobile Shell |
| 003 | rankings-data-density | A: Broadcast Table | Data Tables & Interior Pages |
| 004 | mobile-rankings-shell | C: Pan Table + Seasonal Tabs | Mobile Shell (update) |
| 005 | scores-grid | C: Ledger | Scores & Graded Receipts |

## Excluded Sketches
| # | Name | Reason |
|---|------|--------|
| — | none | — |

## Design Direction
Apple.com scroll grammar fused with FIFA26 broadcast scorebug identity; the dial sits
broadcast-forward (001-B). Dark stadium canvas, pitch-green field-gradient hero with the
scorebug as the hero object, broadcast nav with mint rule, condensed-caps identity type
(Barlow Condensed) over system-ui body, persistent full-body CSS mecha assistant (GX-01).
At mobile widths the site becomes an app shell (002-B) with GX-01 as the raised center
tab. **Meta-pattern confirmed across 003/004/005: dense broadcast tables are the working
surface everywhere** — desktop rankings (003-A), mobile rankings via full-parity pan
table (004-C), and the scores audit ledger (005-C). Scorebugs are hero/marketing
components, not working surfaces. Marketing home leads with the provable accuracy claim
— receipts shown, misses included.

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
- **Mobile shell:** bottom tab bar (64px) with GX-01 raised center puck; one-liner
  scorebug; bottom-sheet chat. Tables keep FULL column parity and pan horizontally
  with a sticky player column (make Proj sticky too at build time). Tab overflow =
  seasonal swap (Draft Jul–Sep ↔ Scores in-season), no "More" tab.
- **Interior data pages:** dense sortable table, yellow condensed headers, mint proj
  numerals, color-coded position tags, tier pills, click-to-expand conformal band +
  stack correlation chip.
- **Scores page:** audit ledger — our line (mint, hero column) vs market side-by-side,
  ●/◐/○ edge glyphs, week chips toggle upcoming↔graded, ✓ COVER / ✗ MISS results with
  misses kept visible, ATS record banner (record / units / high-edge hit rate).
- **Scorebug:** pill with multicolor gradient outline, trophy-emblem separator, clock
  tab = our predicted line, periwinkle ribbon CTA; `.compact` grid variant; mobile
  one-liner; graded hit/miss outline treatments; hero-bug + EDGE/LEAN corner tags
  reserved for marketing modules.
- **Mecha assistant:** GX-01 full-body clip-path CSS figure on desktop, head-only puck
  on mobile; pulsing eyes/core; inspired-by, never literal Gundam.
- **Honesty as design principle:** wins in mint, misses in visible gray — never hidden;
  grade against the closing line.

## Open Questions (carried into build)
- Seasonal tab swap trigger (calendar date vs first kickoff).
- News/Matchups contextual entry points on mobile (no permanent tab).
- Proj column must join the sticky region in the mobile pan table.
