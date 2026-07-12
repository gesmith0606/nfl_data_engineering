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

## Open Questions

- **Tab overflow:** 5 slots hold Home/Ranks/GX-01/Scores/League — News, Matchups, and
  Draft Room don't fit. Needs a "More" tab, contextual entry points, or IA priority
  call at build time.

## Origin

Synthesized from sketch: 002 (winner Variant B: App Shell + Bottom Tabs)
Source files available in: sources/002-mobile-broadcast-hero/
