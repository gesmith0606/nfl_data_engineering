---
plan: 72-04-api-frontend
phase: 72-event-flag-expansion
status: complete
completed: 2026-04-25
requirements: [EVT-01, EVT-02]
commits: 2
---

# Plan 72-04: API + Frontend — SUMMARY

## What Was Built

Pydantic NewsItem + TeamEvents extended additively per CONTEXT Phase 72 Schema Note. EVENT_LABELS extended to 19 entries. Frontend EventBadges + NewsItem TS type extended.

### Backend Changes

| File | Change |
|------|--------|
| `web/api/models/schemas.py` | NewsItem adds EXACTLY 2 new top-level fields: `subject_type: Optional[Literal["player","coach","team","reporter"]] = "player"` and `team_abbr: Optional[str] = None`. NO new top-level boolean fields (per CONTEXT Phase 72 Schema Note). TeamEvents adds 3 new int fields: `coach_news_count`, `team_news_count`, `staff_news_count` (all default 0). |
| `web/api/services/news_service.py` | EVENT_LABELS extended from 12 → 19 entries (7 new draft-season flags appended after existing 12, preserves category grouping). NEGATIVE_FLAGS adds is_cap_cut + is_holdout. POSITIVE_FLAGS adds is_drafted + is_rookie_buzz. NEUTRAL_FLAGS adds is_rumored_destination + is_trade_buzz + is_coaching_change. `_build_news_item_from_bronze` and `_build_news_item_from_silver` populate `subject_type` (default "player") + `team_abbr` from Silver record. `_extract_event_flags` automatically emits the 7 new label strings via the same iteration loop (no code change needed). |

### Frontend Changes

| File | Change |
|------|--------|
| `web/frontend/src/lib/nfl/types.ts` | NewsItem TS type adds optional `subject_type` + `team_abbr` fields (mirrors Pydantic). TeamEvents TS type adds optional `coach_news_count`, `team_news_count`, `staff_news_count`. NO new boolean fields. |
| `web/frontend/src/features/nfl/components/EventBadges.tsx` | BEARISH_LABELS adds Cap Cut + Holdout. BULLISH_LABELS adds Drafted + Rookie Buzz. NEUTRAL_LABELS adds Rumored Destination + Trade Buzz + Coaching Change. Existing 12 labels untouched (back-compat). Component code unchanged — bucket assignment is data-driven. |

### Tests

| File | Change |
|------|--------|
| `tests/web/test_news_schema_phase_72.py` | NEW — 14 tests covering: subject_type defaults to "player", team_abbr defaults to None, valid Literal values accepted, invalid Literal rejected, NewsItem does NOT have new boolean top-level fields (locks Phase 72 Schema Note), event_flags carries new label strings, TeamEvents new counters default 0, EVENT_LABELS has 19 entries with correct ordering, _extract_event_flags emits new labels. |
| `web/frontend/src/features/nfl/components/EventBadges.test.tsx` | NEW — 7 tests covering: empty badges → null render, existing labels render, all 7 new labels render, Drafted gets bullish (green) class, Cap Cut gets bearish (red), Coaching Change gets neutral (yellow), mixed badges render distinctly. |

## Test Results

- `tests/web/test_news_schema_phase_72.py`: 14/14 passing
- `web/frontend EventBadges.test.tsx`: 7/7 passing
- `npx tsc --noEmit` (frontend): clean (no new TypeScript errors introduced)
- Full sentiment suite (Wave 3): 211/211 passing

## Commits

- `0ac1deb` — `feat(72-04): NewsItem +subject_type/team_abbr; TeamEvents +rollup counts; EVENT_LABELS extended`
- `bb059ff` — `feat(72-04): frontend EventBadges +7 draft-season labels; NewsItem TS type +subject_type/team_abbr`

## Self-Check: PASSED

- [x] NewsItem adds EXACTLY 2 new top-level fields (subject_type, team_abbr)
- [x] NewsItem does NOT have 7 new top-level boolean fields (per CONTEXT Phase 72 Schema Note)
- [x] TeamEvents adds 3 new int counters (coach_news_count, team_news_count, staff_news_count)
- [x] EVENT_LABELS = 19 entries (12 existing + 7 new appended)
- [x] news_service emits 7 new labels via _extract_event_flags
- [x] Frontend EventBadges renders all 19 labels with correct bucket colors
- [x] NewsItem TS type mirrors Pydantic schema additively
- [x] All tests pass; tsc clean

## Handoff to Plan 72-05

Plan 72-05 must:
1. Run W17/W18 backfill against Railway live (push code, confirm Railway deploys, trigger workflow).
2. Run `scripts/audit_event_coverage.py` against Railway → assert ≥15/32 teams non-zero events (EVT-04).
3. Run `scripts/audit_advisor_tools.py --out-72` against Railway → assert ≥20 teams via getPlayerNews + getTeamSentiment (EVT-05).
4. Commit audit JSON files showing both gates passed AND `base_url` contains `railway.app`.
5. Phase 72 SUMMARY + STATE/ROADMAP/REQUIREMENTS sync.
