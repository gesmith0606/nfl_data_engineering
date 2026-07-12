---
sketch: 002
name: mobile-broadcast-hero
question: "Does the Broadcast Overlay home survive at 375px — nav pattern, scorebug adaptation, GX-01 placement?"
winner: "B"
tags: [mobile, responsive, nav, scorebug, mecha-assistant]
---

# Sketch 002: Mobile Broadcast Hero

## Design Question
Sketch 001's winner (Broadcast Overlay) was validated at desktop width only, and
its scorebug physically cannot fit a phone (each team block is 180px min). Fantasy
users check on phones at night — this sketch decides the mobile shell every page
will inherit: how the nav collapses, how the scorebug re-lays, and where GX-01
lives when screen space is scarce.

## How to View
open .planning/sketches/002-mobile-broadcast-hero/index.html

Each variant renders inside a fixed 375×760 phone frame — scroll INSIDE the frame.

## Variants
- **A: Hamburger + Stacked Card** — website-first. Hamburger menu slides down,
  the scorebug re-lays as a vertical matchup card (team rows, mint score column,
  emblem mid-divider), GX-01 head floats bottom-right, chat is a bottom sheet.
- **B: App Shell + Bottom Tabs** — app-first. Persistent 5-slot bottom tab bar
  with GX-01 as the raised CENTER tab; the scorebug shrinks but stays horizontal
  (one-line KC 27 🏆 24 BUF); stats scroll horizontally.
- **C: Chip Nav + Swipe Deck** — content-first. Horizontally scrolling chip nav
  under the brand bar, hero becomes a swipeable snap-scroll deck of stacked
  matchup cards with pagination dots, receipts as a compact card.

## What to Look For
- **Scorebug adaptation:** stacked vertical card (A/C) vs shrunken horizontal
  one-liner (B) — which still feels like the broadcast identity?
- **Nav:** hamburger (A) vs bottom tabs (B) vs scrolling chips (C). Tabs are
  app-native but eat 64px forever; hamburger hides the IA; chips show it.
- **GX-01:** floating head (A/C) vs center-tab celebrity placement (B). Does the
  head-only version still read as GX-01 without the body?
- Try the interactions: hamburger, tab switches, swipe the deck (drag sideways),
  open GX-01 and ask something.
