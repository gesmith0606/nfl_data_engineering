---
name: Phase 41 Ship Gate Results
description: ML player models ship QB only; RB/WR/TE stay heuristic — OOF gap persists despite efficiency features and ensemble
type: project
---

Phase 41 ship gate results (2026-03-31):
- QB: SHIP — 75.4% holdout improvement, 43.6% OOF improvement (massive win)
- RB: SKIP — holdout +20.4%, OOF -13.1% (dual agreement fails)
- WR: SKIP — holdout +12.8%, OOF -14.5% (dual agreement fails)
- TE: SKIP — holdout +12.6%, OOF -11.8% (dual agreement fails)

**Why:** The heuristic rolling average (roll3 45% + roll6 30% + STD 25%) is near-optimal for RB/WR/TE. These positions have stable, recency-driven output. ML adds noise. QB has more variance from matchup/game script that ML captures.

**How to apply:** Phase 42 ships QB ML + RB/WR/TE heuristic fallback. All infrastructure (features, ensemble, ship gate) is in place for future attempts.
