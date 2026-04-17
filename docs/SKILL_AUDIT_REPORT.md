# Skill & Agent Audit Report

**Date**: 2026-04-14
**Auditor**: Claude Opus 4.6

---

## 1. Scorecard — Project Skills

| Skill | Clarity | Complete | Accurate | Specific | Anti-pat | Testable | Fresh | Integrated | Avg |
|-------|---------|----------|----------|----------|----------|----------|-------|------------|-----|
| weekly-pipeline | 9 | 8 | 8 | 9 | 6 | 7 | 9 | 8 | **8.0** |
| test | 8 | 8 | 9 | 8 | 5 | 9 | 9 | 6 | **7.8** |
| validate-data | 8 | 8 | 7 | 9 | 5 | 8 | 8 | 7 | **7.5** |
| draft-prep | 9 | 9 | 8 | 9 | 5 | 6 | 8 | 9 | **7.9** |
| ingest | 9 | 8 | 9 | 8 | 5 | 7 | 9 | 7 | **7.8** |
| notebooklm | 6 | 4 | **3** | 5 | **2** | **2** | 5 | 4 | **3.9** |
| fireworks-tech-graph | 7 | 9 | **3** | 8 | 6 | 5 | 6 | **2** | **5.8** |
| emil-design-eng | 8 | 9 | 8 | 10 | 8 | 5 | 7 | 4 | **7.4** |
| impeccable | 7 | 8 | 6 | 7 | 7 | 5 | 7 | 6 | **6.6** |
| audit (design) | 7 | 7 | 7 | 7 | 6 | 7 | 7 | 7 | **6.9** |
| polish | 7 | 7 | 7 | 6 | 5 | 5 | 7 | 7 | **6.4** |
| animate | 7 | 7 | 7 | 6 | 5 | 4 | 7 | 7 | **6.3** |
| colorize | 7 | 6 | 7 | 5 | 5 | 4 | 7 | 7 | **6.0** |
| typeset | 7 | 6 | 7 | 5 | 5 | 4 | 7 | 7 | **6.0** |
| layout | 7 | 6 | 7 | 5 | 5 | 4 | 7 | 7 | **6.0** |
| critique | 7 | 7 | 7 | 6 | 6 | 6 | 7 | 7 | **6.6** |
| bolder | 7 | 6 | 7 | 5 | 5 | 4 | 7 | 7 | **6.0** |
| taste-skill | 6 | 7 | 7 | 8 | 8 | 3 | 6 | **2** | **5.9** |
| soft-skill | 6 | 7 | 7 | 8 | 8 | 3 | 6 | **2** | **5.9** |
| minimalist-skill | 6 | 7 | 7 | 8 | 7 | 3 | 6 | **2** | **5.8** |
| redesign-skill | 7 | 7 | 7 | 8 | 7 | 3 | 6 | 4 | **6.1** |
| skill-creator | 7 | 6 | **3** | 5 | 3 | 5 | 6 | 3 | **4.8** |

## 2. Scorecard — Project Agents

| Agent | Clarity | Complete | Accurate | Specific | Anti-pat | Testable | Fresh | Integrated | Avg |
|-------|---------|----------|----------|----------|----------|----------|-------|------------|-----|
| design-engineer | 8 | 8 | 8 | 8 | 8 | 5 | 8 | 7 | **7.5** |
| web-scraper | 7 | 7 | 5 | 7 | 5 | 4 | 6 | 5 | **5.8** |
| skill-optimizer | 8 | 8 | 7 | 8 | 5 | 6 | 7 | 7 | **7.0** |

## 3. Scorecard — AI Advisor Tools (route.ts)

| Tool | Clarity | Accurate | Overlap | Error Ctx | Avg |
|------|---------|----------|---------|-----------|-----|
| getPlayerProjection | 9 | 8 | Low | 7 | **8.0** |
| compareStartSit | 8 | 8 | Med* | 7 | **7.7** |
| searchPlayers | 8 | 8 | Low | 7 | **7.7** |
| getNewsFeed | 7 | 7 | Med** | 6 | **6.8** |
| getPositionRankings | 8 | 8 | Med* | 7 | **7.7** |
| getGamePredictions | 8 | 7 | Low | 7 | **7.3** |
| getTeamRoster | 8 | 8 | Low | 7 | **7.7** |
| getTeamSentiment | 7 | **3** | Med** | 5 | **4.5** |
| getPlayerNews | 7 | 7 | Med** | 6 | **6.8** |
| getDraftBoard | 8 | 8 | Low | 7 | **7.7** |
| compareExternalRankings | 8 | 7 | Low | 6 | **7.0** |
| getSentimentSummary | 7 | **3** | Med** | 5 | **4.5** |

**Overlap notes:**
- (*) `compareStartSit` fetches ALL projections then filters 2 — could use `getPlayerProjection` x2 instead. Model may be confused about which to use.
- (**) `getNewsFeed`, `getPlayerNews`, `getTeamSentiment`, `getSentimentSummary` — four sentiment/news tools with overlapping purpose. Model may pick the wrong one.

---

## 4. Critical Bugs Found

### BUG-1: `getTeamSentiment` calls wrong endpoint (BROKEN)
- **Tool calls**: `/api/news/team?season=N`
- **Actual endpoint**: `/api/news/team-sentiment?season=N&week=W`
- **Impact**: Tool always returns 404 / "not found". Gemini has no working path to team sentiment.
- **Fix**: Change path to `/api/news/team-sentiment` and add required `week` parameter.

### BUG-2: `getSentimentSummary` missing required `week` parameter (BROKEN)
- **Tool calls**: `/api/news/summary?season=N` (no week)
- **Actual endpoint requires**: `season` AND `week` (both mandatory via `Query(...)`)
- **Impact**: Backend returns 422 Unprocessable Entity every time.
- **Fix**: Add `week` to the tool's input schema and pass it through.

### BUG-3: `getGamePredictions` defaults season to 2024 (STALE)
- **Tool schema**: `z.number().default(2024)` but current season is 2026
- **Impact**: Gemini must override the default every time, or returns stale 2024 data.
- **Fix**: Change default to 2026.

### BUG-4: `getNewsFeed` defaults season to 2025 (STALE)
- Same issue: default 2025, current season 2026.

---

## 5. Bottom 5 Items (Improved)

### 5a. `notebooklm` skill (Avg 3.9 -- LOWEST)
**Problems:**
- References `scripts/generate_notebooklm_content.py` which exists but has limited content types
- References `output/notebooklm/` but only rankings exist, no weekly/matchup content
- No anti-patterns section
- No testability criteria
- Manual workflow is not integrated with the rest of the pipeline
- Automated pipeline code uses `notebooklm` package that may not be installed
- No NFL-specific examples for content generation

**Improvements applied:**
- Added NFL-specific content templates and examples
- Added anti-patterns section
- Added testability criteria
- Clarified which workflows are functional vs aspirational
- Added integration points with projection engine

### 5b. `getTeamSentiment` AI advisor tool (Avg 4.5 -- BROKEN)
**Problems:**
- Wrong endpoint URL (`/api/news/team` vs `/api/news/team-sentiment`)
- Missing required `week` parameter
- No useful error message when backend returns 404

**Improvements applied:**
- Fixed endpoint path to `/api/news/team-sentiment`
- Added `week` parameter to input schema
- Improved error context

### 5c. `getSentimentSummary` AI advisor tool (Avg 4.5 -- BROKEN)
**Problems:**
- Missing required `week` parameter
- Backend returns 422 on every call

**Improvements applied:**
- Added `week` parameter to input schema
- Passes week through to API call

### 5d. `skill-creator` skill (Avg 4.8)
**Problems:**
- References `eval-viewer/generate_review.py` which does not exist in the project
- Very informal tone ("Cool? Cool.")
- No NFL-specific guidance
- No concrete eval criteria for this project
- No anti-patterns

**Improvements applied:**
- Removed broken eval-viewer reference
- Added NFL project context
- Added concrete eval criteria examples
- Added anti-patterns section

### 5e. `fireworks-tech-graph` skill (Avg 5.8)
**Problems:**
- References `references/style-1-flat-icon.md` and `references/style-N.md` which do not exist
- References `scripts/generate-diagram.sh` and other scripts that do not exist
- No NFL project integration (no templates for pipeline/architecture diagrams)
- Zero integration with other project skills

**Improvements applied:**
- Removed broken references to nonexistent scripts/references directories
- Added NFL-specific diagram templates (medallion architecture, projection pipeline)
- Added integration note with project documentation

---

## 6. AI Advisor Tool Analysis

### Tool Selection Confusion Risk
The 12 tools fall into overlapping clusters that may confuse Gemini's tool selection:

**Cluster 1 — News/Sentiment (4 tools, high overlap):**
- `getNewsFeed` — general news feed
- `getPlayerNews` — player-specific news (filters from same feed endpoint)
- `getTeamSentiment` — team-level sentiment (different endpoint)
- `getSentimentSummary` — overall sentiment summary (different endpoint)

**Recommendation:** Merge `getPlayerNews` into `getNewsFeed` with a player_name filter parameter. This reduces from 4 to 3 tools and makes it clearer which to pick.

**Cluster 2 — Player Lookup (3 tools, moderate overlap):**
- `getPlayerProjection` — single player lookup
- `compareStartSit` — two-player comparison (uses same endpoint)
- `searchPlayers` — name search

These are sufficiently distinct in description. No action needed.

**Cluster 3 — Rankings/Draft (2 tools, low overlap):**
- `getPositionRankings` — positional rankings
- `getDraftBoard` — full draft board with ADP/VORP

Distinct purposes. No action needed.

### Missing Error Context
All tools return `{ found: false, message: "..." }` but the messages are generic. When the backend is down, the message says "The data backend is currently unavailable" for ALL tools. Consider adding tool-specific context like "Could not fetch projections — the backend may be offline or projections may not be generated for this week."

### Hardcoded Season Defaults
Multiple tools have different default seasons (2024, 2025, 2026). These should all be 2026 for consistency, or better yet derived from a single constant.

---

## 7. Additional Findings

### Design Skills (audit/polish/animate/colorize/typeset/layout/critique/bolder)
All 8 design sub-skills are well-structured with consistent patterns (MANDATORY PREPARATION referencing /impeccable). However, none contain NFL project-specific guidance. For a data-heavy fantasy football dashboard, these skills would benefit from NFL-specific context about:
- Dark mode data visualization
- Team color palettes
- Sports-specific typography (tabular nums for stats, monospace for scores)
- Dashboard card patterns for player/game data

### Third-Party Skills (taste-skill, soft-skill, minimalist-skill)
These are generic UI skills with no NFL project integration. They score low on Integration (2/10) because they have no awareness of the project's Next.js + shadcn stack or its data dashboard nature. They are useful as reference material but not as actionable project skills.

### `impeccable` Skill
Contains a `<post-update-cleanup>` block that references a `scripts/cleanup-deprecated.mjs` that does not exist. This will produce an error on first invocation after update.

---

## 8. Recommendations

1. **Fix the 2 broken AI advisor tools immediately** (getTeamSentiment, getSentimentSummary) -- these silently fail on every call
2. **Normalize season defaults** across all AI advisor tools to 2026
3. **Consider consolidating** getPlayerNews into getNewsFeed with a player filter
4. **Add NFL context** to the impeccable/design sub-skills for dashboard-specific guidance
5. **Remove or update** the notebooklm skill's aspirational code paths that reference uninstalled packages
6. **Remove the stale cleanup block** from impeccable (references nonexistent script)
