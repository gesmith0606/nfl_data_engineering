---
name: sketch-findings-nfl-data-engineering
description: Validated design decisions, CSS patterns, and visual direction from sketch experiments. Auto-loaded during UI implementation on nfl_data_engineering (website redesign — broadcast overlay direction).
---

<context>
## Project: nfl_data_engineering

Apple.com layout grammar (one idea per full-bleed screen, huge restrained typography,
generous whitespace, scroll storytelling) fused with the FIFA World Cup 26 broadcast
scorebug identity (reference: `.planning/design-refs/wc26-broadcast-scorebug.webp` —
near-black bars, mint score panels, vibrant yellow accents, periwinkle ribbon, gold
trophy emblem separator, bold condensed white caps, team chips). Persistent floating AI
assistant styled as a full-body mecha (angular armor, yellow V-fin, glowing cyan eyes —
inspired-by, never literal Gundam). The marketing home leads with the provable claim:
we beat the industry consensus, receipts shown, misses included.

Reference points: apple.com (layout grammar, typography restraint, translucent nav),
FIFA26 broadcast scorebug (CCTV5 frame in design-refs), existing WC26 OKLCH tokens in
web/frontend (`--wc-*`).

Sketch sessions wrapped: 2026-07-12 (001–003), 2026-07-13 (004–005)
</context>

<design_direction>
## Overall Direction

**Winner: "Broadcast Overlay" (Sketch 001, Variant B)** — the dial sits closer to the
broadcast pole than the apple pole. The scorebug IS the hero; apple grammar governs the
scroll structure below the fold.

- **Palette (sampled from reference frame):** bar/near-black `#05070d`, dark canvas
  `#070a12`, mint `#91edd0` (score panels, nav rule, focus states), vibrant yellow
  `#ffd84d` (accents, headline highlights — NOT antique gold), periwinkle `#5b67c7`
  (ribbons/CTAs), cyan `#22d3ee` (mecha eyes), pitch greens `#2d5a27→#1a3a17`
  (hero field gradient), positive-stat green `#0eaf7d`.
- **Typography:** body = system-ui/SF Pro (the apple feel); display/identity =
  Barlow Condensed 500–800, uppercase, tracked (`--font-bug`). Condensed caps are the
  brand voice for nav, headlines, stats, and component chrome.
- **Layout:** broadcast nav bar (52px, near-black, 2px mint rule) → full-viewport hero
  (field gradient, yard lines, scorebug hero, honest stat pills) → apple-style `.fsec`
  feature story sections (96px padding, kicker/h2/sub, alternating dark backgrounds),
  themed via `--sec-*` custom-property contract.
- **Honesty as design principle:** real accuracy numbers everywhere, misses (RB +0.26)
  shown in muted gray labeled WIP — never hidden.
- **Interaction:** 0.15s ease transitions baseline; hover lifts on chips/ribbons;
  pulsing glow animations on the mecha; CTA press feedback.
- Site IA: Draft Room / Rankings / Scores / News / Matchups / My League. First tab is
  NOT a dashboard.
- **Mobile (≤~430px):** app shell, not shrunken website — bottom tab bar with GX-01 as
  the raised center tab, one-liner scorebug, bottom-sheet chat. Data tables keep FULL
  column parity and pan horizontally (sticky player column); tab overflow resolves via
  seasonal swap (Draft Jul–Sep ↔ Scores in-season), no "More" tab.
- **Interior data pages:** dense broadcast tables — yellow condensed headers over a
  2px mint rule, mint hero numerals, shared control bar (position pills / scoring
  segment / search), expandable rows for depth.
- **Meta-pattern (confirmed across 003/004/005):** dense broadcast tables are the
  working surface everywhere — desktop rankings, mobile rankings, scores ledger.
  Scorebugs are hero/marketing components, not working surfaces.
</design_direction>

<findings_index>
## Design Areas

| Area | Reference | Key Decision |
|------|-----------|--------------|
| Layout & Marketing Home | references/layout-and-marketing-home.md | Broadcast-forward dark home: field-gradient hero, broadcast nav w/ mint rule, honest stat pills, `--sec-*` themed apple-scroll feature sections |
| Scorebug Component | references/scorebug-component.md | Near-black pill w/ multicolor gradient outline, mint score panels + near-black digits, trophy emblem separator, clock tab = our line, periwinkle ribbon CTA, compact grid variant |
| Mecha Assistant | references/mecha-assistant.md | GX-01 full-body CSS mecha (clip-path divs, no images), fixed bottom-right, pulsing cyan eyes + mint chest core, near-black chat panel w/ yellow condensed header |
| Mobile Shell | references/mobile-shell.md | App shell at 375px: bottom tab bar w/ GX-01 raised center tab, one-liner scorebug, bottom-sheet chat; tables pan w/ sticky player column (full column parity); tab overflow = seasonal Draft↔Scores swap |
| Data Tables & Interior Pages | references/data-tables-interior-pages.md | Dense broadcast table: yellow condensed headers over mint rule, mint proj numerals, position/scoring/search control bar, expandable conformal-band rows |
| Scores & Graded Receipts | references/scores-graded-receipts.md | Scores = audit ledger: our line (mint) vs market side-by-side, ●/◐/○ edge glyphs, week chips toggle upcoming↔graded, ✓ COVER / ✗ MISS column + ATS record banner — misses stay visible |

## Theme

The winning theme file is at `sources/themes/default.css` (WC26 Broadcast v2,
color-corrected to the reference frame).

## Source Files

Original sketch HTML files are preserved in `sources/` for complete reference.
</findings_index>

<metadata>
## Processed Sketches

- 001-home-hero-direction
- 002-mobile-broadcast-hero
- 003-rankings-data-density
- 004-mobile-rankings-shell
- 005-scores-grid
</metadata>
