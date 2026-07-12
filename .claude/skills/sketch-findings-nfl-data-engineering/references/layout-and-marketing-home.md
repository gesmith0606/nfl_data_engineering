# Layout & Marketing Home

## Design Decisions

**Winner: Variant B "Broadcast Overlay"** — the scorebug IS the hero, not a jewel accent.
Chosen over A (Apple Minimal, white, scorebug-once) and C (Dark Stadium Hybrid, glassy
receipt panel on navy-black). The dial sits closer to the FIFA26 broadcast pole than the
apple.com pole, while keeping apple's one-idea-per-screen scroll grammar for the feature
sections below the fold.

- **Canvas:** dark stadium (`--stadium: #070a12`); hero uses a vertical gradient from
  near-black navy into pitch green (`#0b0e18 → #14301a → var(--pitch-a) → var(--pitch-b)`)
  with faint white yard lines (`rgba(255,255,255,.13)`, 2px) layered absolutely.
- **Nav:** broadcast bar, not apple-quiet. 52px tall, `#05070d` background, condensed caps
  (`--font-bug`), `letter-spacing:.1em`, **2px solid mint bottom border** — this mint rule
  is the nav's signature. Brand wordmark "GRIDIRON**IQ**" with the "IQ" in mint. Sticky
  below the sketch chrome. Links `#cfd6e4`, hover → mint.
- **Nav items (site IA):** Draft Room / Rankings / Scores / News / Matchups / My League.
  First tab is NOT a dashboard — George explicitly rejected dashboard-first.
- **Hero headline:** condensed caps (`--font-bug`), weight 800, `clamp(38px,5.5vw,72px)`,
  white with the key phrase highlighted in vibrant yellow (`--yellow`), heavy text-shadow
  (`0 4px 24px rgba(0,0,0,.5)`). Copy leads with the provable claim:
  "We beat the consensus. Here's the receipt."
- **Honest receipts:** accuracy stats rendered as broadcast stat pills —
  `rgba(5,7,13,.85)` background, 1px mint-tinted border (`rgba(145,237,208,.45)`),
  condensed numerals 26px/800. Wins in mint-green (`--pos`), the RB deficit shown
  honestly in muted gray labeled "WIP". REAL numbers only: QB −0.39 / WR −0.075 /
  TE −0.43 / RB +0.26.
- **Feature story sections (`.fsec`):** apple-style one-idea-per-screen scroll, 96px
  vertical padding, centered, `kicker` (condensed caps, .2em tracking, accent color)
  → `h2` (in Variant B: condensed caps 800) → `sub` (max-width 640px, muted). Alternate
  section backgrounds `#0b0e18` / `#070a12`. Sections are themed via per-variant
  `--sec-*` custom properties so the same markup reskins per context.
- **Section content is real product data, never lorem:** correlation chips
  (Mahomes↔Kelce +0.50), VORP draft recs, vacated-opportunity sleeper board rows,
  Madden-style mini field with player pins, compact prediction scorebugs, sentiment
  news cards, league-sync CTA.

## CSS Patterns

Section theming contract (lets shared markup adapt to any variant/page):

```css
/* dark broadcast context */
.page-dark {
  --sec-bg:#0b0e18; --sec-bg-alt:#070a12; --sec-fg:#fff; --sec-muted:#9aa3b8;
  --sec-line:rgba(255,255,255,.09); --sec-card:#131722; --sec-accent:var(--yellow);
  --sec-card-shadow:none;
}
.fsec { padding:96px 24px; text-align:center; background:var(--sec-bg);
  color:var(--sec-fg); border-top:1px solid var(--sec-line); }
.fsec.alt { background:var(--sec-bg-alt); }
.fsec .kicker { font-family:var(--font-bug); text-transform:uppercase;
  letter-spacing:.2em; font-size:14px; color:var(--sec-accent); margin-bottom:14px; }
.fsec h2 { font-family:var(--font-bug); text-transform:uppercase; letter-spacing:.04em;
  font-weight:800; font-size:clamp(28px,3.8vw,46px); line-height:1.1; }
.fsec .sub { color:var(--sec-muted); font-size:18px; margin:16px auto 0;
  max-width:640px; line-height:1.55; }
.fcard { background:var(--sec-card); border:1px solid var(--sec-line);
  border-radius:14px; box-shadow:var(--sec-card-shadow); }
```

Broadcast nav:

```css
.b-nav { position:sticky; top:0; z-index:100; display:flex; align-items:center;
  gap:26px; padding:0 28px; height:52px; background:#05070d; color:#fff;
  font-family:var(--font-bug); letter-spacing:.1em; font-size:15px;
  text-transform:uppercase; border-bottom:2px solid var(--mint); }
.b-nav a { color:#cfd6e4; text-decoration:none; transition:color .15s; }
.b-nav a:hover { color:var(--mint); }
.b-nav .brand { color:#fff; font-weight:800; font-size:18px; }
.b-nav .brand .g { color:var(--mint); }
```

Hero field gradient + stat pills:

```css
.b-hero { position:relative; min-height:74vh; display:flex; flex-direction:column;
  align-items:center; justify-content:center; overflow:hidden; padding:60px 20px;
  background:linear-gradient(180deg,#0b0e18 0%, #14301a 30%,
    var(--pitch-a) 55%, var(--pitch-b) 100%); }
.b-hero .yard { position:absolute; left:6%; right:6%; height:2px;
  background:rgba(255,255,255,.13); }
.b-stat { font-family:var(--font-bug); background:rgba(5,7,13,.85);
  border:1px solid rgba(145,237,208,.45); color:#fff; padding:10px 20px;
  border-radius:10px; text-align:center; min-width:118px; }
.b-stat .num { font-size:26px; font-weight:800; }
.b-stat .num.pos { color:var(--mint); }
```

Correlation chip:

```css
.corr-chip { display:inline-flex; align-items:center; gap:8px;
  font-family:var(--font-bug); font-size:16.5px; letter-spacing:.05em;
  padding:7px 16px; border-radius:9999px; background:var(--sec-card);
  border:1px solid var(--sec-line); transition:all .15s ease; }
.corr-chip:hover { transform:translateY(-2px); }
.corr-chip .rho-pos { color:var(--pos); font-weight:800; }
```

## HTML Structures

Page skeleton (Variant B):

```html
<nav class="b-nav">
  <span class="brand">GRIDIRON<span class="g">IQ</span></span>
  <a href="#">Draft Room</a><a href="#">Rankings</a><a href="#">Scores</a>
  <a href="#">News</a><a href="#">Matchups</a><a href="#">My League</a>
</nav>
<section class="b-hero">
  <div class="yard" style="top:18%"></div> <!-- ×6, evenly spaced -->
  <h1>We beat the consensus.<br><span class="hl">Here's the receipt.</span></h1>
  <p class="sub">Graded against Sleeper across 11,000+ player-weeks — misses published too.</p>
  <!-- scorebug here (see scorebug-component.md) -->
  <div class="b-stats"> <!-- 4 stat pills, RB honestly marked WIP --> </div>
</section>
<!-- then .fsec sections: Graph Intelligence / Draft Room / AI Advisor /
     Madden View / Game Predictions / News & Sentiment / My League -->
```

Feature section:

```html
<section class="fsec">
  <div class="kicker">Graph Intelligence</div>
  <h2>We model the connections<br>between players.</h2>
  <p class="sub">121 stability-gated correlations mined from a decade of games…</p>
  <div class="body">…real data content…</div>
  <p class="fine">7,559 candidate pairs in. 121 served.</p>
</section>
```

## What to Avoid

- **Apple Minimal on white (Variant A rejected):** the accuracy claim read as generic
  SaaS marketing; the scorebug lost its broadcast identity against a white canvas.
- **Dark hybrid with glassy receipt panel (Variant C rejected):** closer, but the
  scorebug-as-rare-jewel treatment undersold the product's identity; George wants the
  broadcast look to BE the brand.
- **Dashboard as the first tab** — explicitly rejected; home is a marketing/story page.
- **Muted "gold" accents** — the reference frame's accent is VIBRANT yellow `#ffd84d`,
  not antique gold. George corrected this in round 1.
- **Navy-blue scorebug bar** — the reference bar is near-black `#05070d`, not navy.
- Hype-y claims without receipts — always show the RB +0.26 miss alongside the wins.

## Origin

Synthesized from sketch: 001 (winner Variant B: Broadcast Overlay)
Source files available in: sources/001-home-hero-direction/
