---
phase: sentiment-v2
plan: 01
subsystem: sentiment
tags: [reddit, regex, nlp, rule-extraction, scraper]

requires:
  - phase: S1-sentiment-foundation
    provides: ClaudeExtractor, PlayerSignal dataclass, SentimentPipeline, PlayerNameResolver

provides:
  - Reddit scraper for r/fantasyfootball and r/nfl
  - Rule-based text extractor producing PlayerSignal objects without API key
  - Pipeline auto-selection between Claude and rule-based extractors

affects: [SV2-02, SV2-03, SV2-04, sentiment-pipeline]

tech-stack:
  added: []
  patterns: [rule-based-extractor, dual-extractor-auto-select]

key-files:
  created:
    - scripts/ingest_sentiment_reddit.py
    - src/sentiment/processing/rule_extractor.py
    - tests/test_rule_extractor.py
    - tests/test_reddit_ingestion.py
  modified:
    - src/sentiment/processing/pipeline.py
    - src/config.py

key-decisions:
  - "Rule-based confidence capped at 0.7 (vs Claude 0.8-0.9) to reflect reduced accuracy"
  - "Pipeline auto mode tries Claude first, falls back to RuleExtractor — no code change needed when API key becomes available"
  - "Name regex handles Mc/Mac prefixes, hyphens, St. prefix for NFL player names"

patterns-established:
  - "Dual extractor pattern: same interface (extract/is_available), pipeline auto-selects"
  - "Reddit scraper follows identical Bronze JSON envelope format as RSS ingestion"

requirements-completed: [SV2-01, SV2-02, SV2-03, SV2-04]

duration: 8min
completed: 2026-04-13
---

# Phase SV2 Plan 01: Reddit Scraper + Rule-Based Extraction Summary

**Reddit scraper for r/fantasyfootball and r/nfl plus regex-based signal extractor enabling the sentiment pipeline to run without an Anthropic API key**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-13T02:24:55Z
- **Completed:** 2026-04-13T02:33:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Rule-based extractor produces PlayerSignal objects from 5 pattern categories (injury, roster, role, positive, negative) with zero external dependencies
- Reddit scraper fetches public JSON from r/fantasyfootball and r/nfl with proper rate limiting and User-Agent
- Pipeline auto-selects Claude when API key available, falls back to rule-based otherwise
- 98 total sentiment tests pass (32 new + 66 existing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Reddit scraper + rule-based extractor** - `7cdd2d4` (feat) — TDD: tests written first, then implementation
2. **Task 2: Wire rule extractor into pipeline** - `4661aee` (feat)

## Files Created/Modified
- `scripts/ingest_sentiment_reddit.py` - Reddit public JSON API scraper with CLI flags
- `src/sentiment/processing/rule_extractor.py` - RuleExtractor class with regex patterns for 5 signal categories
- `src/sentiment/processing/pipeline.py` - Updated to auto-select between Claude and rule-based extractors
- `src/config.py` - Added reddit_subreddits, reddit_post_limit, reddit_user_agent to SENTIMENT_CONFIG
- `tests/test_rule_extractor.py` - 21 tests covering all pattern categories, confidence, format
- `tests/test_reddit_ingestion.py` - 11 tests covering JSON parsing, player resolution, CLI args

## Decisions Made
- Rule-based confidence capped at 0.7 to signal lower accuracy vs Claude (0.8-0.9)
- Pipeline auto mode: Claude first, rule fallback — zero config change needed when API key added
- Name regex extended with Mc/Mac prefix and St. prefix support for NFL player names (McCaffrey, St. Brown)
- Silver record model_version field now reflects actual extractor class name instead of hardcoded "claude-haiku-4-5"

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Name regex failed on McCaffrey and St. Brown**
- **Found during:** Task 1 (TDD GREEN phase)
- **Issue:** Default Title-Case regex missed Mc/Mac prefixes (McCaffrey) and St. prefix (St. Brown)
- **Fix:** Extended _NAME_PATTERN to handle `(?:Mc|Mac)?` prefix and `(?:St\.\s)?` prefix
- **Files modified:** src/sentiment/processing/rule_extractor.py
- **Verification:** test_returning_from_ir and test_positive_breakout now pass
- **Committed in:** 7cdd2d4 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential for correct player name extraction. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Rule extractor is wired and functional, unblocking all downstream sentiment v2 plans
- Reddit Bronze data will be available for SV2-02 (enhanced processing) and SV2-03 (aggregation)
- Pipeline can run end-to-end without API key via `python scripts/process_sentiment.py`

---
*Phase: sentiment-v2*
*Completed: 2026-04-13*
