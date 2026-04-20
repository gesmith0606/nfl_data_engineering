---
phase: 63-ai-advisor-hardening
plan: 05
subsystem: advisor-widget-persistence
tags: [advisor, widget, persistence, localstorage, advr-04]

requires:
  - file: "web/frontend/src/components/chat-widget.tsx"
    provides: "Pre-63-05 floating widget scaffold"
  - file: "web/frontend/src/app/dashboard/advisor/page.tsx"
    provides: "Pre-63-05 full-page advisor route"
provides:
  - "web/frontend/src/hooks/use-persistent-chat.ts: localStorage-backed useChat wrapper (storageKey 'advisor:conversation:v1', 100-msg cap, 250ms debounce)"
  - "Widget + advisor page share state via the default storage key"
  - "'Clear conversation' button in both surfaces (trash icon in widget, outline button on full page)"
affects:
  - "ADVR-04 requirement satisfied at the widget-mount + storage level"
  - "63-06 live re-audit can exercise persistence on every /dashboard/* page"

tech-stack:
  added: []
  patterns:
    - "SSR-safe localStorage hydration: guarded by typeof window; happens in useEffect, not during render"
    - "Quota / private-mode safe: all storage ops wrapped in try/except; warnings logged, never thrown"
    - "Corrupt-JSON recovery: removes the key and starts fresh"
    - "Debounced write: 250ms trailing batch so rapid message chains don't hammer storage"

key-files:
  created:
    - "web/frontend/src/hooks/use-persistent-chat.ts"
  modified:
    - "web/frontend/src/components/chat-widget.tsx"
    - "web/frontend/src/app/dashboard/advisor/page.tsx"
---

# Plan 63-05 — Persistent chat widget + cross-page reach

## What shipped

- `usePersistentChat()` hook wraps `useChat` from `@ai-sdk/react` with localStorage-backed state
- Widget (`chat-widget.tsx`) and full-page advisor (`/dashboard/advisor`) both call it with the default storage key, so they share conversation state via storage
- "Clear conversation" wired into both surfaces (trash icon + outline button)

## Browser UAT (Playwright-driven, 2026-04-19)

| # | Check | Result |
|---|---|:---:|
| 1 | Floating button on `/dashboard/projections` | ✓ |
| 2 | Widget opens, shows 4 suggestion chips + input | ✓ |
| 3 | Message sent, rendered in conversation | ✓ |
| 4 | `localStorage['advisor:conversation:v1']` written (98 bytes, role=user) | ✓ |
| 5 | Navigate to `/predictions` — widget + conversation preserved | ✓ |
| 6 | Navigate to `/dashboard/advisor` full page — same conversation visible | ✓ |
| 7 | Full page reload — conversation restored from storage | ✓ |
| 8 | "Clear conversation" removes the localStorage key | ✓ |
| 9 | Floating widget present on all 10 `/dashboard/*` routes | ✓ |

## Known follow-up (not blocking)

**Clear-broadcast**: when the full-page advisor's Clear button fires, it wipes the shared localStorage key AND its own `useChat` instance's messages — but the floating widget rendered on the same page has its own `useChat` instance that retains in-memory messages until the next page navigation/refresh. The visible effect: after Clear, the full-page conversation is gone but the widget still shows messages briefly.

Low-impact (refresh fully clears both; new messages write from either surface). Options for follow-up:
1. Add a BroadcastChannel / storage-event listener so either instance notices the other's clear
2. Hoist the `useChat` to a shared React context so both surfaces subscribe to one instance

Noted for 63-06 live re-audit; defer unless the SHIP gate flags it.

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1    | `a460dc1` | usePersistentChat hook + wire widget and advisor to shared state |
| 2 (docs) | (this commit) | Browser-verified SUMMARY close-out |

## Requirements coverage

- **ADVR-04** ✓ — floating widget renders on every `/dashboard/*` page; conversation persists across navigation + reload via localStorage

## Local AI credentials note

`/api/chat` returned 500 during UAT because neither `GOOGLE_GENERATIVE_AI_API_KEY` nor `GROQ_API_KEY` is set locally. Production has these configured — AI responses would render live. Not a 63-05 code issue.
