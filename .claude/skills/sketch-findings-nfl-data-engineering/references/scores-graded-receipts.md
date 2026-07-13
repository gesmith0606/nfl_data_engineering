# Scores & Graded Receipts

## Design Decisions

**Winner: Sketch 005 Variant C "Ledger"** — the Scores page is an audit table, not a
grid of scorebugs. Chosen over A (edge-first hero bugs + compact grid) and B
(TV-slate grid grouped by kickoff slot). This confirms the session's meta-pattern:
**dense broadcast tables are the working surface everywhere**; scorebugs are hero/
marketing components.

- **Ledger columns:** Game (chips + `AWAY @ HOME`) · Slot · Our Proj (score pair) ·
  **Our Line** (mint condensed 800 — the hero column) · Market (muted) · Edge ·
  Cover Prob / Result. Our line and the market line sit side-by-side — the disagreement
  IS the product.
- **Edge column glyphs:** `● HIGH` (yellow) / `◐ MED` (dim yellow) / `○ LOW` (gray),
  condensed caps. Reads faster down a column than corner tags.
- **Two page states, one control:** week chips top-right. An upcoming week shows
  cover probabilities; a graded week (`2025 · WK 18 ✓ graded`) swaps the last column
  to `✓ COVER (31–20)` in mint / `✗ MISS (24–27)` in gray — **misses stay on the
  board.**
- **Graded record banner** appears only for graded weeks: big condensed numbers in a
  mint-bordered bar — ATS record (10–5–1), flat-stake units (+4.2u), high-edge hit
  rate (3/4) — plus the honesty line: "Every pick graded against the closing line.
  Misses stay on the board — that's the point."
- Table chrome inherits the 003 pattern exactly: yellow condensed headers over a 2px
  mint rule, zebra rows, mint-wash hover, `tabular-nums`.
- **Preserved patterns from rejected variants** (in sources/): A's enlarged hero-bug
  treatment with EDGE/LEAN corner tags suits marketing surfaces ("this week's best
  bets" module on the home page); B's slot-grouped slate could serve a TV-style
  ambient view. Graded scorebug treatment from A/B: ✓ COVER bugs keep the mint
  outline, ✗ MISS bugs switch to a flat gray outline at 82% opacity with a
  gray verdict pill.

## CSS Patterns

Week chips + record banner:

```css
.wk-chip { font-family:var(--font-bug); font-size:14px; letter-spacing:.08em;
  text-transform:uppercase; color:#cfd6e4; background:#131722;
  border:1px solid rgba(255,255,255,.12); padding:6px 15px; border-radius:999px; }
.wk-chip.on { background:var(--mint); color:#04140e; font-weight:700; }

.recbar .inner { display:flex; gap:26px; align-items:center;
  background:rgba(19,23,34,.8); border:1px solid rgba(145,237,208,.35);
  border-radius:12px; padding:12px 20px; font-family:var(--font-bug); }
.recbar .big { font-size:24px; font-weight:800; color:var(--mint); }
.recbar .lbl { font-size:12px; letter-spacing:.12em; color:#9aa3b8;
  text-transform:uppercase; }
```

Ledger value treatments:

```css
.led .ourline { font-family:var(--font-bug); font-size:17px; font-weight:800;
  color:var(--mint); }           /* our line = hero column */
.led .mkt { color:#9aa3b8; }     /* market line = muted comparison */
.led .edge-cell { font-family:var(--font-bug); letter-spacing:.08em; font-weight:700; }
.led .edge-cell.high { color:var(--yellow); }
.led .edge-cell.med  { color:rgba(255,216,77,.6); }
.led .edge-cell.low  { color:#5c6478; }
.led .res.hit  { color:var(--pos); font-weight:700; }
.led .res.miss { color:#8892ad; } /* visible, not hidden */
```

Graded scorebug treatment (for hero/marketing contexts):

```css
.bug.hit  { background-image:linear-gradient(var(--bar),var(--bar)),
  linear-gradient(90deg,var(--mint),var(--mint)); }   /* mint outline holds */
.bug.miss { background-image:linear-gradient(var(--bar),var(--bar)),
  linear-gradient(90deg,#3a4157,#3a4157); opacity:.82; }
.verdict { position:absolute; top:-11px; right:10px; font-size:11px; font-weight:800;
  letter-spacing:.1em; padding:2px 10px; border-radius:999px; }
.verdict.hit  { background:var(--mint); color:#04140e; }
.verdict.miss { background:#3a4157; color:#c3c9d8; }
.edge-tag { position:absolute; top:-11px; left:10px; font-size:11px; font-weight:800;
  letter-spacing:.1em; padding:2px 10px; border-radius:999px;
  background:var(--yellow); color:#221b00; }
```

## HTML Structures

```html
<div class="weekbar">
  <button class="wk-chip on">2026 · WK 1</button>
  <button class="wk-chip">2025 · WK 18 ✓ graded</button>
</div>
<table class="led">
  <thead><tr><th>Game</th><th>Slot</th><th class="num">Our Proj</th>
    <th class="num">Our Line</th><th class="num">Market</th><th>Edge</th>
    <th>Cover Prob</th></tr></thead> <!-- header becomes "Result" when graded -->
  <tbody>
    <tr><td><span class="game">[chip]KC <span class="at">@</span> [chip]BUF</span></td>
      <td>SNF</td><td class="num">27–24</td><td class="num ourline">KC −2.5</td>
      <td class="num mkt">KC −1</td><td><span class="edge-cell high">● HIGH</span></td>
      <td><span class="res hit">✓ COVER (31–20)</span></td></tr>
  </tbody>
</table>
```

## What to Avoid

- **Scorebug grids as the working Scores surface (A/B rejected as the base)** — bugs
  don't show the market comparison, and 10–16 of them compete visually. Bugs are for
  heroes; tables are for work.
- Hiding or dimming-to-invisible the misses — gray them, keep them. Credibility comes
  from the visible ✗ rows.
- Showing only our line without the market line — the side-by-side disagreement is
  the value proposition.
- Grading against anything but the closing line (product/copy rule, matches the
  true-CLV plumbing in the model).

## Origin

Synthesized from sketch: 005 (winner Variant C: Ledger)
Source files available in: sources/005-scores-grid/ (includes rejected A/B patterns
worth reusing in marketing contexts)
