# Data Tables & Interior Pages

## Design Decisions

**Winner: Sketch 003 Variant A "Broadcast Table"** — interior workhorse pages (Rankings,
and by extension Scores/Matchups/My League data surfaces) use a dense classic table
carried by broadcast identity details, not by turning every row into a branded capsule.
Chosen over B (tier board — airier grouped rows) and C (pill rows — scorebug-capsule
per player).

- **Page header:** condensed caps 800 title with the context segment in yellow
  ("RANKINGS **· 2026 PRESEASON**"), one-line muted subtitle stating the honesty
  promise ("anchored, graded, receipts published").
- **Control bar (shared across all interior data pages):**
  - Position filter pills — dark `#131722` capsules, active = solid mint with
    near-black text.
  - Scoring segmented toggle (PPR/Half/Std) — one capsule, active segment periwinkle.
    The toggle actually re-computes values, not just a label swap.
  - Search — dark capsule input, mint focus border.
- **Table chrome:** yellow condensed uppercase column headers (13px, .14em tracking)
  over a **2px mint rule** (the nav signature repeated as the table's identity anchor);
  faint zebra striping (`rgba(255,255,255,.025)`); row hover = mint-tinted wash;
  numerals right-aligned, `font-variant-numeric:tabular-nums`.
- **Value hierarchy:** projection is the hero number — condensed 19px/800 in mint.
  Floor·ceiling in muted gray. vs-ECR delta green/red. Tier as a small yellow-outline
  pill (T1/T2). Player cell = team chip + name + muted team code + position tag
  (position tags are color-coded: QB periwinkle, RB mint, WR yellow, TE red).
- **Depth reveal = expandable row:** clicking a player opens an inset panel
  (`#0d1120`, mint-tinted bottom border) with the conformal floor/ceiling band
  (a range bar with yellow proj tick, labeled "~80% coverage") and the player's
  stability-gated stack chip (e.g. BROWN ↔ GOFF +0.51). One row open at a time.
- **Sortable columns** flip ▾/▴ on the header.
- Real product data everywhere: half-PPR bases with rec-count adjusted PPR/Std,
  conformal bands, UC3 correlation edges.

## CSS Patterns

Control bar:

```css
.pos-tab { font-family:var(--font-bug); font-size:15px; letter-spacing:.08em;
  text-transform:uppercase; color:#cfd6e4; background:#131722;
  border:1px solid rgba(255,255,255,.12); padding:6px 16px; border-radius:999px;
  cursor:pointer; transition:all .15s ease; }
.pos-tab.on { background:var(--mint); color:#04140e; border-color:var(--mint);
  font-weight:700; }
.scoring { display:flex; background:#131722; border:1px solid rgba(255,255,255,.12);
  border-radius:999px; overflow:hidden; }
.scoring button.on { background:var(--peri); color:#fff; }
.search { background:#131722; border:1px solid rgba(255,255,255,.12);
  border-radius:999px; color:#fff; padding:8px 16px; outline:none; }
.search:focus { border-color:var(--mint); }
```

Table chrome:

```css
.rk thead th { font-family:var(--font-bug); font-size:13px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--yellow); padding:10px 12px;
  border-bottom:2px solid var(--mint); }
.rk tbody tr.player:nth-child(4n+3) { background:rgba(255,255,255,.025); }
.rk tbody tr.player:hover { background:rgba(145,237,208,.07); }
.rk td { padding:9px 12px; border-bottom:1px solid rgba(255,255,255,.05);
  font-size:14.5px; }
.rk .proj { font-family:var(--font-bug); font-size:19px; font-weight:800;
  color:var(--mint); }
.postag.QB { background:rgba(91,103,199,.25); color:#aab4f5; }
.postag.RB { background:rgba(145,237,208,.16); color:var(--mint); }
.postag.WR { background:rgba(255,216,77,.16); color:var(--yellow); }
.postag.TE { background:rgba(230,69,69,.18); color:#ff9d9d; }
.tier-pill { font-family:var(--font-bug); font-size:12px; letter-spacing:.08em;
  padding:2px 10px; border-radius:999px; border:1px solid rgba(255,216,77,.4);
  color:var(--yellow); }
```

Expandable detail row with conformal band:

```css
tr.detail td { background:#0d1120; padding:16px 20px 18px;
  border-bottom:1px solid rgba(145,237,208,.25); }
.rangebar { position:relative; height:10px; background:#1c2333; border-radius:5px; }
.rangebar .fill { position:absolute; top:0; bottom:0; border-radius:5px; opacity:.55;
  background:linear-gradient(90deg,var(--mint-deep),var(--mint)); }
.rangebar .tick { position:absolute; top:-4px; width:3px; height:18px;
  background:var(--yellow); border-radius:2px; } /* proj marker */
```

## HTML Structures

```html
<div class="ctrls">
  <div class="posbar">
    <button class="pos-tab on" data-pos="ALL">All</button>
    <button class="pos-tab" data-pos="QB">QB</button> <!-- RB/WR/TE -->
  </div>
  <div class="scoring">
    <button data-s="ppr">PPR</button><button data-s="half" class="on">Half</button>
    <button data-s="std">Std</button>
  </div>
  <input class="search" placeholder="Search player or team…">
</div>
<table class="rk">
  <thead><tr><th>RK</th><th>Player</th><th class="num sortable">Proj ▾</th>
    <th class="num">Floor · Ceil</th><th class="num">vs ECR</th><th>Tier</th></tr></thead>
  <tbody><!-- rows rendered from data; click row → tr.detail with rangebar + stack chip --></tbody>
</table>
```

## What to Avoid

- **Pill/capsule rows for long lists (C rejected)** — visually exhausting past ~15
  rows and wastes horizontal space; save the capsule treatment for hero contexts.
- **Trading density for air on workhorse pages (B rejected as the base)** — users
  live in Rankings; rows-per-screen matters more than whitespace. B's yellow tier
  headlines ("TIER 1 — THE ELITE" + fading gold rule) are worth adding later as an
  optional grouping toggle on top of the table.
- Non-tabular numerals in data columns — always `tabular-nums`, right-aligned.
- Modal/route navigation for quick player depth — the inline expandable row keeps
  the user in the list.

## Origin

Synthesized from sketch: 003 (winner Variant A: Broadcast Table)
Source files available in: sources/003-rankings-data-density/
