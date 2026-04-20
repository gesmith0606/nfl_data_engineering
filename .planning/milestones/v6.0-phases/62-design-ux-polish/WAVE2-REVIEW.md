# Wave 2 Code Review — Phase 62-03 + 62-04

Commits reviewed: `426fa08..origin/main` (17 commits).

---

## Regressions

None identified. All previously rendered components still have their functional logic intact. Token-only class replacements (e.g. `text-sm` → `text-[length:var(--fs-sm)]`) are semantically equivalent and do not change layout.

---

## Hydration / SSR Issues

**Low risk, one watchpoint.** `motion-primitives.tsx` carries `'use client'` and calls `useReducedMotion()` at the top of each primitive. This is correct — Framer Motion hooks must run client-side only. However, `Stagger` does `React.Children.toArray(children)` and re-wraps each child in an anonymous `motion.div`. If any Stagger child is itself a Server Component passed as a prop, that pattern would fail at the React boundary. In the current codebase all Stagger children are rendered inside `'use client'` files, so this is not a current regression — but it is a footgun to document.

`DataLoadReveal` uses `AnimatePresence mode='wait' initial={false}` which is the correct SSR-safe configuration (skips initial animation on hydration).

---

## Accessibility Losses

**One confirmed loss.** In `matchup-view.tsx`, `PlayerRow` was previously a bare `<div>` with CSS `transition-colors`. It is now wrapped in `<HoverLift>`, which renders an intermediate `motion.div`. The outer `motion.div` receives the `whileHover` transform; the inner `div` retains `hover:bg-white/10` via Tailwind. Because `HoverLift` does not accept or forward `role`, `tabIndex`, or `aria-*` props in its current signature (`DivMotionProps` omits `children`, no explicit a11y passthrough), any caller that needs to add `role="listitem"` or `aria-label` to the interactive row must now reach through two wrapper divs. No aria attributes were removed from existing call sites in this diff, so there is no current regression — but the `HoverLift` API creates a trap for future callers.

No semantic tags were replaced with divs. `<table>` / `<tr>` / `<th>` / `<td>` structure in `rankings-table` and `projections-table` is unchanged. `Stagger` is not used inside any table body, avoiding the invalid `motion.div` inside `<tbody>` problem.

`prefers-reduced-motion` is honored in all five primitives via `useReducedMotion()` → `PassThrough`. The `chat-widget.tsx` raw `motion` usage also gates on `reduceMotion` consistently.

---

## TypeScript Issues

**One gap.** `Stagger` reads `(child as React.ReactElement)?.key` but `React.Children.toArray` already re-keys children with a `.$` prefix — the original key is lost. The fallback to `idx` means Stagger always uses index keys. This is not a TS error (it compiles cleanly) but it is incorrect runtime behavior: animated items will not track identity on list reorder. Downstream effect is cosmetic (wrong exit animations) but worth fixing before motion is used on sortable lists (e.g. rankings-table if Stagger is ever added there).

No missing imports, no `any` escapes, and `getPositionColor` is correctly exported from `design-tokens.ts` and imported in `matchup-view.tsx`.

---

## Performance

**No large-list animation concern.** The two highest-volume Stagger sites are:

- `news-feed.tsx` → `visibleItems` capped at `PAGE_SIZE = 25` via `filtered.slice(0, offset + PAGE_SIZE)`. Max 25 animated nodes per render. Safe.
- `matchup-view.tsx` → `Stagger step={0.03}` wraps `rowSlots.map` inside each row group. Each group has 3–5 rows (backfield, receivers, line, secondary). Max ~5 nodes per Stagger instance. Safe.

`teamSentiments` in news-feed is all 32 NFL teams at most; `step={0.02}` means total cascade is 640ms at 32 items — acceptable.

The projections-table (the only view that could render 200+ rows) has no motion wrappers added in this diff. No concern.

---

## Pattern Drift Between 62-03 and 62-04

**Minor drift in two areas:**

1. `chat-widget.tsx` (62-04) uses raw `motion.div` / `AnimatePresence` with inline `MOTION` / `EASE` constants rather than the `FadeIn` / `Stagger` primitives introduced in 62-04. This is a deliberate choice (chat bubble enter/exit needs directional `x` offsets not exposed by `FadeIn`'s `rise` prop), but it means the widget is the only production site using raw motion post-62-04. The comment in `motion-primitives.tsx` says "Do NOT write raw `<motion.div>`" — so either the rule needs a documented exception for directional animations or `FadeIn` should grow an `x` prop.

2. 62-03 pages wrap content in `<FadeIn>` at the page level; 62-04 draft pages wrap content in `<FadeIn className='space-y-[var(--gap-stack)]'>` at the same level — consistent. No drift there.

Spacing token usage is consistent throughout: `var(--space-N)`, `var(--gap-stack)`, `var(--pad-card)` used uniformly in both families.

---

## Summary

| Category | Status |
|---|---|
| Regressions | None |
| Hydration/SSR | Low risk — Stagger + Server Component footgun documented |
| Accessibility | No losses; HoverLift API needs a11y prop forwarding note |
| TypeScript | Stagger key loss (cosmetic, index fallback always used) |
| Perf / large lists | Not a concern — all Stagger sites are bounded |
| 62-03 / 62-04 drift | chat-widget raw motion usage violates the no-raw-motion rule |

No blocking issues. Two items to address before wave 3: (1) add an explicit exception or `x`-offset prop to `FadeIn` so `chat-widget` can follow the same primitive pattern; (2) document that `HoverLift` / `Stagger` must forward `aria-*` / `role` for interactive children.
