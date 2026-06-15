---
phase: 87
plan: 87-01
title: /draft-live skill + CLI entrypoint + manual fallback
wave: 1
depends_on: [86-01]
requirements: [SKILL-01, SKILL-02, SKILL-03, SKILL-04]
files_modified:
  - scripts/draft_live.py
  - .claude/skills/draft-live/SKILL.md
  - tests/test_draft_live.py
  - CLAUDE.md
  - .claude/skills/draft-prep/SKILL.md
autonomous: true
---

# Plan 87-01: Claude Code Draft Skill

## Objective
Wrap the Phase 86 engine into a one-command, conversational, proactive draft-night
co-pilot that runs inside Claude Code, plus a manual pick-entry fallback.

## Tasks
- **87-01-1 (SKILL-01):** `scripts/draft_live.py` — load projections+ADP, build the
  adapter+engine, resolve a draft from `--username` or `--draft-id`, print a snapshot
  (status, on-the-clock, your next pick, recs, roster, key moments); `--json` output.
- **87-01-2 (SKILL-01/03):** `--watch` loop (poll on interval, re-render on new picks,
  stop on complete / Ctrl-C); auto-applies league scoring/roster from the snapshot.
- **87-01-3 (SKILL-04):** `--manual` + `--add-pick` builds a DraftState from typed
  picks and drives the engine (D-09 fallback for unsupported platforms / API breaks).
- **87-01-4 (SKILL-02/03):** `.claude/skills/draft-live/SKILL.md` proactivity policy
  (on-turn + key-moments + on-demand Q&A); docs in CLAUDE.md; cross-link from draft-prep.
- **87-01-5 (tdd):** offline tests for manual-state building + main(--manual --json).

## must_haves
1. `/draft-live` skill starts from username/draft_id with no code edits. (SKILL-01)
2. SKILL.md encodes the D-05 proactivity policy + ad-hoc Q&A. (SKILL-02)
3. Docs + draft-prep cross-link; watch/resume tolerant. (SKILL-03)
4. Manual pick entry drives the engine end-to-end. (SKILL-04)
