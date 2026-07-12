# Mecha Assistant (GX-01)

## Design Decisions

The persistent floating AI assistant is **GX-01** — a full-body CSS mecha, bottom-right
on every page, "inspired-by, never literal Gundam" (no trademarked silhouettes or names).
Validated as at-home against all three sketch backgrounds; it's background-independent.

- **Anatomy:** built entirely from absolutely-positioned `div`s with `clip-path`
  polygons and gradients inside a 120×200px container — no images, no SVG assets.
- **Armor:** white/near-black plating (light gradients `#f4f6fb → #8f97ab`, joints and
  fists `#1c2333`), **yellow V-fin** on the head, **red chin vent**, **mint hexagonal
  chest core** (pulsing glow), **glowing cyan eyes** (`--cyan: #22d3ee`, skewed,
  pulsing), yellow chest vents + belt crest, periwinkle knee accents.
- **Idle animation:** `eye-pulse` opacity keyframes on eyes (3.2s) and chest core
  (2.6s) — the unit reads as "online" without being distracting.
- **Floating placement:** fixed bottom-right, scaled to ~0.62 with
  `transform-origin:bottom right`; hover scales up slightly and lifts 4px. Label
  "GX-01" in yellow condensed caps beneath.
- **Chat panel:** opens above the mecha (fixed, 310px wide), near-black `--bar`
  background, yellow-tinted 1px border, header "ADVISOR // GX-01" in yellow condensed
  caps with a ✕ close, reply body in soft gray `#cfd6e4`, input on `#131722` with
  mint focus border. Opens with a 0.18s fade/slide-up.
- **Interaction loop:** click mecha → panel toggles; Enter in input → brief
  "Analyzing…" state → reply with the answer's key numbers highlighted in mint. Replies
  cite real signals (correlations, implied totals, target-share trends).
- The same `.gx` markup scales up (`transform:scale(1.15)`) for the "Meet GX-01"
  feature section — one component, two contexts.

## CSS Patterns

Key structural pieces (full 30-part anatomy in sources/):

```css
.gx { position:relative; width:120px; height:200px;
  filter:drop-shadow(0 12px 22px rgba(0,0,0,.4)); }
.gx div { position:absolute; }
.gx .fin-l, .gx .fin-r { top:0; width:30px; height:26px;
  background:linear-gradient(180deg,#ffe98a,var(--yellow));
  filter:drop-shadow(0 0 6px rgba(255,216,77,.7)); z-index:6; }
.gx .fin-l { left:26px; clip-path:polygon(100% 100%, 0% 0%, 60% 100%); }
.gx .fin-r { right:26px; clip-path:polygon(0% 100%, 100% 0%, 40% 100%); }
.gx .head { top:8px; left:50%; transform:translateX(-50%); width:44px; height:38px;
  background:linear-gradient(160deg,#f4f6fb 0%,#c9cfdd 55%,#8f97ab 100%);
  clip-path:polygon(50% 0%, 88% 20%, 100% 58%, 80% 100%, 20% 100%, 0% 58%, 12% 20%); }
.gx .visor { top:22px; left:50%; transform:translateX(-50%); width:32px; height:10px;
  background:#05070d; clip-path:polygon(0 20%, 100% 20%, 90% 100%, 10% 100%); }
.gx .eye { top:24px; width:9px; height:4px; background:var(--cyan);
  box-shadow:var(--shadow-glow-cyan); animation:eye-pulse 3.2s ease-in-out infinite; }
.gx .eye.l { left:42px; transform:skewX(-12deg); }
.gx .eye.r { right:42px; transform:skewX(12deg); }
.gx .core { top:66px; left:50%; transform:translateX(-50%); width:14px; height:14px;
  background:radial-gradient(circle at 35% 30%, #d8fff1, var(--mint) 60%, var(--mint-deep));
  clip-path:polygon(50% 0, 100% 30%, 100% 70%, 50% 100%, 0 70%, 0 30%);
  box-shadow:0 0 10px rgba(145,237,208,.8); animation:eye-pulse 2.6s ease-in-out infinite; }
@keyframes eye-pulse { 0%,100% {opacity:1;} 50% {opacity:.55;} }
```

Floating placement + chat panel:

```css
#mecha { position:fixed; bottom:16px; right:20px; z-index:9000; cursor:pointer;
  transition:transform .2s ease; transform:scale(.62); transform-origin:bottom right; }
#mecha:hover { transform:scale(.68) translateY(-4px); }
#mecha-label { position:absolute; bottom:-20px; left:50%; transform:translateX(-50%);
  font-family:var(--font-bug); font-size:15px; letter-spacing:.16em;
  color:var(--yellow); text-transform:uppercase;
  text-shadow:0 1px 6px rgba(0,0,0,.6); }

#mecha-chat { position:fixed; bottom:170px; right:24px; z-index:9001; width:310px;
  background:var(--bar); color:#fff; border-radius:14px; box-shadow:var(--shadow-bug);
  padding:16px; display:none; border:1px solid rgba(255,216,77,.4); font-size:14px; }
#mecha-chat.open { display:block; animation:chat-in .18s ease; }
@keyframes chat-in { from {opacity:0; transform:translateY(8px);} to {opacity:1; transform:none;} }
#mecha-chat .hdr { font-family:var(--font-bug); letter-spacing:.12em;
  color:var(--yellow); font-size:12px; text-transform:uppercase; }
#mecha-chat input { width:100%; background:#131722; border:1px solid #2a3350;
  color:#fff; border-radius:8px; padding:8px 10px; outline:none; }
#mecha-chat input:focus { border-color:var(--mint); }
```

## HTML Structures

```html
<div id="mecha" onclick="toggleMecha()" title="GX-01 — your AI advisor">
  <div class="gx">
    <div class="fin-l"></div><div class="fin-r"></div>
    <div class="head"></div><div class="visor"></div>
    <div class="eye l"></div><div class="eye r"></div><div class="chin"></div>
    <div class="neck"></div>
    <div class="pauldron-l"></div><div class="pauldron-r"></div>
    <div class="torso"></div><div class="vent-l"></div><div class="vent-r"></div><div class="core"></div>
    <div class="arm-l"></div><div class="arm-r"></div>
    <div class="fist-l"></div><div class="fist-r"></div>
    <div class="waist"></div><div class="belt"></div><div class="skirt"></div>
    <div class="leg-l"></div><div class="leg-r"></div>
    <div class="knee-l"></div><div class="knee-r"></div>
    <div class="foot-l"></div><div class="foot-r"></div>
    <div id="mecha-label">GX-01</div>
  </div>
</div>
<div id="mecha-chat">
  <div class="hdr"><span>ADVISOR // GX-01</span><span onclick="toggleMecha()">✕</span></div>
  <div id="mecha-reply">GX-01 online. Ask me anything — start/sit, trade value, or why
  we're fading a player this week.</div>
  <input placeholder="Ask about your matchup…" onkeydown="if(event.key==='Enter'){mechaReply(this)}">
</div>
```

## What to Avoid

- **Literal Gundam** — no trademarked silhouettes, names, or exact RX-78 color blocking.
  "Inspired-by" means: angular armor, V-fin, glowing eyes, chest core — generic mecha
  vocabulary.
- Head-only button — the full-body figure won; it doubles as a brand character in the
  "Meet GX-01" feature section.
- Static (non-animated) eyes/core — the pulse is what makes it read as a live assistant.
- Generic chat-bubble FAB styling — the panel must carry the broadcast identity
  (near-black, yellow condensed header, mint focus states).

## Origin

Synthesized from sketch: 001 (mecha identical across variants by design; judged against
all three backgrounds)
Source files available in: sources/001-home-hero-direction/
