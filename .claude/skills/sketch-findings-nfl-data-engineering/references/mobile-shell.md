# Mobile Shell

## Design Decisions

**Winner: Sketch 002 Variant B "App Shell + Bottom Tabs"** — at 375px the site behaves
like an app, not a shrunken website. Chosen over A (hamburger menu + vertically stacked
matchup card) and C (scrolling chip nav + swipeable card deck).

- **Nav = persistent bottom tab bar** (64px, `#05070d`, 1px white-alpha top border).
  Tabs are condensed caps 10.5px with icon above; inactive `#8892ad`, active/hover mint.
  No hamburger — the IA stays visible and thumb-reachable.
- **GX-01 is the raised CENTER tab**: a 54px circular "puck" (near-black, yellow-tinted
  border, drop shadow) floating 22px above the bar, holding the head-only mecha. The
  label under it is yellow. This gives the assistant a permanent home and eliminates
  the floating-FAB-covers-content problem.
- **Head-only GX-01** works on mobile: fins + head + visor + pulsing cyan eyes + red
  chin read as GX-01 without the body (~44×40px component).
- **Scorebug stays a horizontal one-liner** (`KC [chip] 27 🏆 24 [chip] BUF | WK 1
  EDGE HIGH`) at reduced scale — truer to real broadcast geometry than a stacked card.
  Abbreviated team codes instead of full names; clock tab shrinks with it.
- **Top bar** is minimal: 44px, centered brand wordmark, 2px mint bottom rule (the
  nav signature carries over from desktop).
- **Chat = bottom sheet**, not a floating panel: slides up from above the tab bar
  (`transform:translateY(105%)` → open), grab handle, same near-black/yellow-header/
  mint-focus treatment as desktop.
- **Stat pills scroll horizontally** in a snap row rather than wrapping into a grid —
  keeps the hero short.
- Hero survives at 375px: same field gradient and yard lines, headline drops to 34px
  condensed caps.

**Mobile data tables (Sketch 004, winner C "Pan Table + Seasonal Tabs"):**

- **Full column parity, no simplification** — the desktop table keeps ALL columns on
  mobile and pans horizontally, with the player column sticky (`position:sticky;
  left:0` + right-edge shadow). Chosen over collapsing to essential columns with
  tap-to-expand depth (A) and two-line rows (B). George prefers the full data surface
  over a simplified mobile view.
- **Build-time fix required:** in the sketch, the mint Proj number pans out of view —
  make Proj part of the sticky region (second sticky column, or merged into the
  sticky player cell) in the real implementation.
- **Tab overflow: SEASONAL SWAP, not a "More" tab** — the 4th/5th tab slots change
  with the calendar: **Draft** holds a slot Jul–Sep, **Scores** replaces it once the
  season starts. Trigger rule TBD at build time (date-based or first-kickoff-based).
- Compact control bar: position pills scroll horizontally; the scoring toggle moves
  into a ⚙︎ bottom-sheet instead of sitting inline.
- Include a subtle pan affordance ("◂ drag the table sideways ▸") — sideways-scrolling
  tables aren't self-evident.

## CSS Patterns

Bottom tab bar with raised GX-01 center tab:

```css
.tabbar { position:fixed; bottom:0; left:0; right:0; z-index:65; height:64px;
  background:#05070d; border-top:1px solid rgba(255,255,255,.1); display:flex; }
.tab { flex:1; display:flex; flex-direction:column; align-items:center;
  justify-content:center; gap:3px; color:#8892ad; font-family:var(--font-bug);
  font-size:10.5px; letter-spacing:.1em; text-transform:uppercase; cursor:pointer; }
.tab.active, .tab:hover { color:var(--mint); }
.tab.gx-tab .puck { position:absolute; top:-22px; width:54px; height:54px;
  border-radius:50%; background:var(--bar); border:1.5px solid rgba(255,216,77,.55);
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 6px 18px rgba(0,0,0,.55); }
.tab.gx-tab .lbl { margin-top:30px; color:var(--yellow); }
```

Bottom-sheet chat (sits above the tab bar):

```css
.sheet { position:fixed; left:0; right:0; bottom:64px; z-index:64; background:var(--bar);
  border-radius:18px 18px 0 0; border-top:1px solid rgba(255,216,77,.4);
  padding:14px 16px 18px; transform:translateY(105%); transition:transform .22s ease; }
.sheet.open { transform:none; }
.sheet .grab { width:36px; height:4px; border-radius:2px;
  background:rgba(255,255,255,.25); margin:0 auto 10px; }
```

Mobile one-liner scorebug (fits 375px):

```css
.hbug { font-family:var(--font-bug); position:relative; display:inline-block;
  background:var(--bar); border-radius:14px; padding:2px;
  background-image:linear-gradient(var(--bar),var(--bar)),
    linear-gradient(90deg,var(--peri),var(--mint) 40%,var(--yellow) 75%,var(--peri));
  background-origin:border-box; background-clip:padding-box,border-box;
  border:2px solid transparent; }
.hbug-row { display:flex; align-items:center; padding:6px 12px; gap:8px; color:#fff; }
.hbug .nm { font-size:16px; font-weight:700; text-transform:uppercase; } /* KC, BUF */
.hbug .sc { font-size:18px; font-weight:800; background:var(--mint); color:#04140e;
  border-radius:5px; width:30px; text-align:center; }
```

Horizontal stat-pill scroller:

```css
.b-scroll { display:flex; gap:8px; overflow-x:auto; padding:0 16px;
  scrollbar-width:none; }
.b-scroll::-webkit-scrollbar { display:none; }
.b-scroll .m-stat { flex:0 0 96px; }
```

Pan table with sticky player column (Sketch 004-C):

```css
.c-scroller { overflow-x:auto; }
table.crk { border-collapse:collapse; min-width:560px; width:100%; }
.crk thead th { font-family:var(--font-bug); font-size:11px; letter-spacing:.12em;
  text-transform:uppercase; color:var(--yellow); padding:8px 10px;
  border-bottom:2px solid var(--mint); white-space:nowrap; background:#0b0e18; }
.crk td { padding:8px 10px; border-bottom:1px solid rgba(255,255,255,.05);
  font-size:13px; white-space:nowrap; }
.crk .sticky { position:sticky; left:0; background:#0b0e18; z-index:2; }
.crk td.sticky { box-shadow:2px 0 6px rgba(0,0,0,.4); }
/* NOTE: include Proj in the sticky region in production */
```

## HTML Structures

```html
<div class="tabbar">
  <div class="tab active"><span class="ic">🏠</span>Home</div>
  <div class="tab"><span class="ic">📊</span>Ranks</div>
  <div class="tab gx-tab" onclick="toggleSheet('gx-sheet')">
    <div class="puck"><!-- head-only .gxh mecha --></div>
    <span class="lbl">GX-01</span>
  </div>
  <div class="tab"><span class="ic">🏈</span>Scores</div>
  <div class="tab"><span class="ic">👥</span>League</div>
</div>
<div class="sheet" id="gx-sheet">
  <div class="grab"></div>
  <div class="hdr"><span>ADVISOR // GX-01</span><span onclick="...">✕</span></div>
  <div class="reply">…</div>
  <input placeholder="Ask about your matchup…">
</div>
```

## What to Avoid

- **Hamburger menu (A rejected)** — hides the IA; the product's surfaces should stay
  one thumb-tap away.
- **Stacked vertical matchup card as the primary mobile bug (A/C rejected)** — looks
  like a generic sports-app card; the horizontal one-liner is what keeps the broadcast
  identity. (The stacked `.vbug` card pattern is preserved in sources/ — still useful
  inside swipe decks or game-detail contexts.)
- **Floating FAB for GX-01 on mobile** — overlaps scorebugs/tables on a 375px screen;
  the center-tab puck solves placement permanently.
- Chat as a floating panel on mobile — use the bottom sheet.
- **Simplified/collapsed mobile tables (004-A/B rejected)** — don't hide columns
  behind expansion or reflow to two-line rows; keep the full table and pan.
- **"More" tab as the overflow answer (004-A rejected)** — the seasonal tab swap won;
  News and Matchups reach mobile through contextual entry points, not a junk-drawer
  tab.

## Open Questions

- Seasonal tab swap trigger: what date/event flips Draft→Scores? (Decide at build
  time — calendar date vs first regular-season kickoff.)
- News and Matchups have no permanent mobile tab — confirm their contextual entry
  points (home modules, player rows) are sufficient.

## Origin

Synthesized from sketches: 002 (winner Variant B: App Shell + Bottom Tabs),
004 (winner Variant C: Pan Table + Seasonal Tabs)
Source files available in: sources/002-mobile-broadcast-hero/,
sources/004-mobile-rankings-shell/
