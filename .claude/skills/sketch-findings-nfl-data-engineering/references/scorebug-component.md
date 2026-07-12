# Scorebug Component

## Design Decisions

The broadcast scorebug is the product's signature component — validated as the HERO of
the marketing home (winner Variant B) and as a compact card for prediction grids. Colors
are sampled from the actual FIFA26 broadcast reference frame
(`.planning/design-refs/wc26-broadcast-scorebug.webp`):

- **Bar:** near-black `#05070d` (`--bar`) pill (`border-radius:999px`) with a
  **multicolor gradient outline** (periwinkle → mint → yellow → periwinkle) achieved via
  the two-layer `background-image` + `background-clip` border trick.
- **Score panels:** MINT `#91EDD0` (`--mint`) with near-black digits `#04140e` — this is
  the corrected signature (NOT gold, NOT white digits on navy).
- **Separator:** gold/yellow trophy emblem between the two scores — a `clip-path`
  polygon trophy silhouette with a yellow gradient and soft glow.
- **Clock tab (above, centered):** black rounded-top tab carrying OUR line
  (e.g. "OUR LINE  KC −2.5") — repurposes the broadcast match-clock slot for the model's
  prediction.
- **Ribbon (below, centered):** periwinkle `#5b67c7` (`--peri`) pill used as the CTA
  ("see every prediction →"), matching the scorer-ribbon slot in the reference.
- **Detail block (right):** vibrant yellow condensed caps, separated by a
  yellow-tinted 1px left border — week/slot + edge strength.
- **Team identity:** condensed caps team name (29px/700, `.04em` tracking) + a small
  team-color gradient chip (34×22px, 3px radius, inner 1px white-alpha inset).
- **Compact variant** (`.bug.compact`) for prediction grids: 12px radius instead of
  full pill, ~55% type scale, no clock tab/ribbon required.
- Typeface throughout: `--font-bug` = Barlow Condensed (weights 500–800).

## CSS Patterns

```css
.bug { font-family:var(--font-bug); box-shadow:var(--shadow-bug);
  border-radius:999px; background:var(--bar); color:#fff; display:inline-block;
  position:relative; padding:3px;
  /* multicolor gradient outline like the broadcast pill */
  background-image: linear-gradient(var(--bar), var(--bar)),
    linear-gradient(90deg, var(--peri) 0%, var(--mint) 35%,
      var(--yellow) 70%, var(--peri) 100%);
  background-origin:border-box; background-clip:padding-box, border-box;
  border:2px solid transparent; }

.bug-clock { position:absolute; top:-26px; left:50%; transform:translateX(-50%);
  background:#000; color:#fff; font-size:14px; letter-spacing:.08em;
  padding:3px 16px; border-radius:7px 7px 0 0; font-weight:600; white-space:nowrap; }

.bug-row { display:flex; align-items:center; padding:8px 26px; }
.bug-team { display:flex; align-items:center; gap:12px; min-width:180px; }
.bug-team.away { justify-content:flex-end; }
.bug-name { font-size:29px; font-weight:700; letter-spacing:.04em;
  text-transform:uppercase; }
.bug-chip { width:34px; height:22px; border-radius:3px; display:inline-block;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.25); }

/* mint score panels with near-black digits — the signature */
.bug-scorepanel { display:flex; align-items:stretch; margin:0 14px;
  border-radius:8px; overflow:hidden; }
.bug-score { font-size:36px; font-weight:800; width:56px; text-align:center;
  background:var(--mint); color:#04140e; display:flex; align-items:center;
  justify-content:center; line-height:1; padding:4px 0; }
.bug-sep { width:34px; background:var(--mint); display:flex;
  align-items:center; justify-content:center; }
.emblem { width:20px; height:32px;
  background:linear-gradient(180deg,#ffe98a,var(--yellow) 45%,var(--yellow-deep));
  clip-path:polygon(50% 0%, 88% 12%, 70% 44%, 62% 56%, 66% 82%, 82% 100%,
    18% 100%, 34% 82%, 38% 56%, 30% 44%, 12% 12%);
  filter:drop-shadow(0 0 5px rgba(255,216,77,.6)); }

.bug-detail { font-size:14px; letter-spacing:.06em; color:var(--yellow);
  text-transform:uppercase; padding-left:18px; margin-left:14px;
  border-left:1px solid rgba(255,216,77,.4); line-height:1.25; }

.bug-ribbon { position:absolute; bottom:-24px; left:50%; transform:translateX(-50%);
  background:var(--peri); color:#fff; font-size:12.5px; font-weight:700;
  letter-spacing:.08em; padding:4px 18px; border-radius:8px; cursor:pointer;
  transition:all .15s ease; white-space:nowrap;
  box-shadow:0 4px 12px rgba(91,103,199,.45); }
.bug-ribbon:hover { background:var(--peri-bright); }

/* compact variant for prediction grids */
.bug.compact { border-radius:12px; }
.bug.compact .bug-name { font-size:17px; }
.bug.compact .bug-score { font-size:20px; width:32px; padding:2px 0; }
.bug.compact .bug-row { padding:5px 14px; }
.bug.compact .bug-team { min-width:auto; }
.bug.compact .bug-chip { width:24px; height:16px; }
.bug.compact .emblem { width:12px; height:20px; }
```

Team chips are diagonal two-color gradients from real team palettes:

```css
.chip-kc  { background:linear-gradient(135deg,#E31837 60%,#FFB81C); }
.chip-buf { background:linear-gradient(135deg,#00338D 60%,#C60C30); }
.chip-det { background:linear-gradient(135deg,#0076B6 60%,#B0B7BC); }
```

## HTML Structures

```html
<div class="bug">
  <div class="bug-clock">OUR LINE&nbsp;&nbsp;KC −2.5</div>
  <div class="bug-row">
    <div class="bug-team away">
      <span class="bug-name">Chiefs</span><span class="bug-chip chip-kc"></span>
    </div>
    <div class="bug-scorepanel">
      <div class="bug-score">27</div>
      <div class="bug-sep"><div class="emblem"></div></div>
      <div class="bug-score">24</div>
    </div>
    <div class="bug-team">
      <span class="bug-chip chip-buf"></span><span class="bug-name">Bills</span>
    </div>
    <div class="bug-detail">Wk 1 · SNF<br>Edge: High</div>
  </div>
  <div class="bug-ribbon">see every prediction →</div>
</div>
```

Compact grid version drops `.bug-clock` and `.bug-ribbon`, adds `.compact` to `.bug`.

## What to Avoid

- **Gold score panels or gold digits** — the reference is mint panels + near-black
  digits; "gold" was a round-1 misread that George corrected.
- **Navy bar** — the bar is near-black `#05070d`.
- Full-pill radius on compact grid bugs — use 12px so rows pack cleanly.
- Fake/placeholder matchups in production — the sketch's KC/BUF etc. are stand-ins for
  real prediction data from `data/gold/predictions/`.

## Origin

Synthesized from sketch: 001 (winner Variant B — same scorebug validated across all
three variant backgrounds)
Source files available in: sources/001-home-hero-direction/
