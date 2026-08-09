# Frontend UX research & interior-page redesign plan (2026-08-08)

Market research (competitor page-level UX + sports-data design trends) and a full
design-system audit of the 21 non-homepage pages, synthesized into the phased plan below.
Design direction itself is settled — WC26 Broadcast Overlay (see
`.claude/skills/sketch-findings-nfl-data-engineering/`); this doc is about executing it
on interior pages, informed by what competitors do well/badly.

## Audit verdict (2026-08-08)

- Chrome is done everywhere: BroadcastNav + MobileTabbar + wc-display page titles ship on
  every dashboard page via the shared layout; primary nav already matches the target IA.
- Only 2/21 page bodies use the broadcast table pattern (rankings "Our Rankings",
  predictions "Ledger") — and the markup is copy-pasted; **no shared BroadcastTable exists**.
- Six files share a byte-identical plain `<table>` skeleton: dynasty-view, sos-grid-view,
  injury-depth-view, start-sit-view, ros-value-view (x2 tabs), multi-compare-table.
- projections (highest-traffic data page) uses the stock TanStack DataTable.
- Draft Room: deepest feature (~15 components), primary nav item, zero broadcast identity.
- Stat-pill motif (near-black + mint left rail + condensed label) hand-duplicated 3x
  (stat-cards, home-modules ProofStrip/PhaseModule).
- matchups + news are polished but run their own third design language (hardcoded emerald/
  red literals, semantic-colors helper) — reconcile later, don't bulldoze.

## Research: patterns adopted into the plan

From competitor teardown (FantasyPros/RotoWire/4for4/ESPN/Yahoo/Sleeper):
- **Tier bands** in rankings tables (shaded clusters + label) — most mature pattern in category.
- **Verdict + visible "why"** — every competitor ships black-box grades (trade, start-sit,
  accuracy). Pairing verdicts with the reasoning is the biggest unclaimed differentiator
  and matches our honesty-as-design-principle.
- **Confidence as %/bar**, never binary calls; floor/projection/ceiling wording (no σ/CI).
- ESPN "Bottom Line": one plain-English verdict sentence above the fold on player surfaces.
- RotoWire ticker: impact-color tag + relative timestamp + one-line takeaway + expandable
  analysis (news page already close; keep for reconciliation pass).
- Accuracy: linked methodology page next to every claim; show player-level error, per-season
  sparkline, letter grade — FantasyPros has the rigor but no visual encoding (our "beat").
- Mobile: nobody freezes the player column — we do (sketch 004 already specifies this).

From design-trend research (Opta/StatMuse/Underdog/Sofascore/FOX scorebug):
- Percentile displays: 6-9 decorrelated metrics, raw value + percentile together, never
  percentile alone ("five-second read" — the top premium-vs-generic lever).
- Table craft: sticky header + frozen ID column, 5-7 default columns, right-aligned
  numerals, skeleton loaders (no spinners), persistent "filtered view" indicator,
  axis-less inline sparklines, virtualize only past ~1000 rows.
- Motion: temporary hierarchy (expand for context, auto-contract); no ornamental motion.
- Anti-patterns: zebra striping on near-black, hover-only row actions, padded radars,
  percentile-only stats, permanent max density.

## Phased plan

- **P1 — shared primitives** (in progress): `<BroadcastTable>` (sticky header, frozen ID
  column, alignment rules, skeleton/empty/filtered states, tier bands, expandable rows)
  extracted from rankings-table + prediction-ledger; shared `<StatPill>`/panel replacing
  the 3 hand-rolled copies; dynasty-view converted as proof.
- **P2 — adoption + research wins**: sos/injuries/start-sit/value/multi-compare/projections
  onto BroadcastTable; trade + start-sit get verdict-with-why panels + confidence bars +
  floor/proj/ceiling bands; accuracy gets letter grades + per-season sparkline +
  methodology link + player-level biggest-misses.
- **P3 — Draft Room reskin**: wc tokens across the ~15-component tree (tabs, board table,
  panels); no functional rework.
- **Backlog — completed 2026-08-08 (second wave)**: matchups/news/games palette
  reconciliation onto system tokens (team colors kept as data); leagues raw-HTML →
  primitives; advisor/lineups/report broadcast treatment; BroadcastTable persisted
  density toggle + column show/hide (additive, opt-in); player profile page at
  /dashboard/players/[playerId] with Bottom Line verdict + Opta-style percentile BARS
  (bars chosen over radar per research) + game-log BroadcastTable.
- **Remaining follow-ups**: per-week projected-history endpoint so the profile's
  projected-vs-actual overlay can land (game-log API returns actuals only — the page
  says so honestly rather than fabricating); merge orphaned player-detail.tsx
  correlations/news sections into the new profile; delete player-detail.tsx after.

Full research reports: session transcript 2026-08-08 (competitor teardown + design trends
+ audit). Feature-gap market research (2026-08-06) lives in the knowledge vault:
`concepts/fantasy-competitor-landscape-2026.md`.
