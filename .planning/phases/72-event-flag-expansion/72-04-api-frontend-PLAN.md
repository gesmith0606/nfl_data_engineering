---
phase: 72
plan: 04
type: execute
wave: 4
depends_on: [72-01, 72-03]
files_modified:
  - web/api/models/schemas.py
  - web/api/services/news_service.py
  - web/frontend/src/features/nfl/components/EventBadges.tsx
  - web/frontend/src/lib/nfl/types.ts
  - tests/web/test_news_endpoints.py
  - web/frontend/src/features/nfl/components/__tests__/EventBadges.test.tsx
autonomous: true
requirements:
  - EVT-01
  - EVT-02
tags: [api, pydantic, frontend, event-badges, additive-fields, typescript]
must_haves:
  truths:
    - "Pydantic NewsItem adds EXACTLY two new top-level fields: subject_type (Optional[Literal] default 'player') + team_abbr (Optional[str]). The 7 new event flags are surfaced via the existing event_flags: List[str] inflection point — no new top-level boolean fields are added (per CONTEXT Phase 72 Schema Note)."
    - "Pydantic TeamEvents includes coach_news_count + team_news_count + staff_news_count int fields (default 0)"
    - "news_service._extract_event_flags + EVENT_LABELS dict cover all 19 flag → human-readable label mappings (existing 12 + 7 new); the 7 new labels are emitted into event_flags: List[str] when set"
    - "news_service.NEGATIVE_FLAGS / POSITIVE_FLAGS / NEUTRAL_FLAGS bucket assignments cover the 7 new flags per CONTEXT (e.g., is_drafted → bullish, is_cap_cut → bearish, is_trade_buzz → neutral)"
    - "news_service.get_team_event_density() projects coach_news_count + team_news_count + staff_news_count from non_player_news Silver channel into each team row"
    - "news_service.get_player_news() includes subject_type and team_abbr fields when present in Silver records"
    - "Frontend EventBadges.tsx EventBadgeMap covers all 19 labels (existing 12 + 7 new) with appropriate Tailwind color buckets — read out of the existing event_flags: string[] list, no new top-level bool consumption"
    - "Frontend NewsItem TS type matches the additive Pydantic surface exactly: subject_type + team_abbr added; NO new top-level booleans"
    - "Existing /api/news/team-events response shape stays back-compat (zero-fill rows still 32 entries, sentiment_label still bullish/bearish/neutral string)"
    - "Backend tests + frontend snapshot/unit tests for EventBadges all pass"
  artifacts:
    - path: "web/api/models/schemas.py"
      provides: "NewsItem additive top-level fields (subject_type + team_abbr ONLY); TeamEvents additive count fields"
      contains: "subject_type"
      contains_2: "team_abbr"
      contains_3: "coach_news_count"
    - path: "web/api/services/news_service.py"
      provides: "EVENT_LABELS extended with 7 new mappings; bucket frozensets updated; _build_news_item_from_bronze + _from_silver project subject_type + team_abbr; _extract_event_flags emits new labels into event_flags list; get_team_event_density merges non_player_news counts"
      contains: "is_drafted"
      contains_2: "non_player_news"
    - path: "web/frontend/src/features/nfl/components/EventBadges.tsx"
      provides: "BEARISH_LABELS + BULLISH_LABELS + NEUTRAL_LABELS extended with 7 new entries; consumes labels from event_flags: string[] (existing pattern)"
      contains: "Drafted"
      contains_2: "Coaching Change"
    - path: "web/frontend/src/lib/nfl/types.ts"
      provides: "NewsItem TS type extended with subject_type + team_abbr ONLY (no new bool fields); TeamEvents TS type extended with 3 new int counts"
      contains: "subject_type"
      contains_2: "coach_news_count"
  key_links:
    - from: "data/silver/sentiment/non_player_news/season=YYYY/week=WW/"
      to: "news_service.get_team_event_density() output"
      via: "scan envelope JSON, group by team_abbr, populate coach_news_count + team_news_count fields per row"
      pattern: "non_player_news.*coach_news_count"
    - from: "web/api/models/schemas.py::NewsItem"
      to: "web/frontend/src/lib/nfl/types.ts::NewsItem"
      via: "TypeScript interface mirrors Pydantic shape exactly — subject_type + team_abbr top-level; 7 new flag labels live in event_flags: string[]"
      pattern: "subject_type.*coach.*team.*reporter"
    - from: "news_service.EVENT_LABELS"
      to: "EventBadges.tsx BEARISH_LABELS / BULLISH_LABELS / NEUTRAL_LABELS"
      via: "labels must match string-for-string between backend and frontend bucket sets; backend emits via _extract_event_flags into event_flags list, frontend reads from same list"
      pattern: "'Drafted'|'Coaching Change'|'Trade Buzz'|'Holdout'|'Cap Cut'|'Rookie Buzz'|'Rumored Destination'"
---

<objective>
Plumb the 7 new event flags + subject_type + team rollup counts through the API + frontend so the Wave 5 audit scripts can prove EVT-04 (≥15/32 teams non-zero) and EVT-05 (≥20 teams via advisor) on a live Railway target. All schema changes are additive Pydantic field additions with safe defaults — zero breaking changes to the existing `/api/news/*` response shapes. Per the CONTEXT "Phase 72 Schema Note" amendment, the 7 new flags are NOT added as top-level NewsItem booleans; they ride the existing `event_flags: List[str]` inflection point that already carries the other 7 in-list flags. NewsItem only gains `subject_type` + `team_abbr` at the top level.

Purpose: Without this plan, Plans 72-01..03 are invisible to the user. The frontend needs to render the 7 new badges for the news feed, and the team-events grid needs to populate the new counts so a single visual confirms ≥15 teams with non-zero events. The advisor surface (`getPlayerNews`, `getTeamSentiment`) consumes the existing `/api/news/*` endpoints transparently — additive fields ride through without prompt-tool changes.

Output: Backend Pydantic + service edits, frontend EventBadges + types extension, full test coverage for both halves. No new endpoints, no new components — extension only.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/72-event-flag-expansion/72-CONTEXT.md
@.planning/phases/72-event-flag-expansion/72-01-SUMMARY.md
@.planning/phases/72-event-flag-expansion/72-02-SUMMARY.md
@.planning/phases/72-event-flag-expansion/72-03-SUMMARY.md
@CLAUDE.md
@web/frontend/CLAUDE.md
@.claude/rules/coding-style.md
@.claude/rules/testing.md

<interfaces>
<!-- LOCKED contracts. -->

From web/api/models/schemas.py (Phase 61 final — current actual shape, verified by reading the file):

```python
class NewsItem(BaseModel):
    doc_id: Optional[str] = None
    title: Optional[str] = None
    source: str = Field(..., description="rss_espn / sleeper / rss_nfl / etc.")
    url: Optional[str] = None
    published_at: Optional[str] = None
    sentiment: Optional[float] = None
    category: Optional[str] = None
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    team: Optional[str] = None

    # 5 pre-existing top-level event-status booleans (back-compat surface — DO NOT add new bools here):
    is_ruled_out: bool = False
    is_inactive: bool = False
    is_questionable: bool = False
    is_suspended: bool = False
    is_returning: bool = False

    body_snippet: Optional[str] = None

    # The 7 OTHER pre-existing flags (is_traded, is_released, is_signed, is_activated,
    # is_usage_boost, is_usage_drop, is_weather_risk) are NOT top-level — they surface
    # only as human-readable strings in event_flags: List[str] via _extract_event_flags.
    # The 7 NEW flags from Plan 72-01 follow that SAME pattern (per CONTEXT Phase 72
    # Schema Note): they appear ONLY in event_flags: List[str], never as top-level bools.
    event_flags: List[str] = Field(default_factory=list, ...)
    summary: Optional[str] = None

class TeamEvents(BaseModel):
    team: str
    negative_event_count: int = 0
    positive_event_count: int = 0
    neutral_event_count: int = 0
    total_articles: int = 0
    sentiment_label: str = "neutral"
    top_events: List[str] = Field(default_factory=list)
```

From web/api/services/news_service.py (Phase 61 final):

```python
EVENT_LABELS: Dict[str, str] = {
    "is_ruled_out": "Ruled Out", "is_inactive": "Inactive",
    "is_questionable": "Questionable", "is_suspended": "Suspended",
    "is_returning": "Returning", "is_traded": "Traded",
    "is_released": "Released", "is_signed": "Signed",
    "is_activated": "Activated", "is_usage_boost": "Usage Boost",
    "is_usage_drop": "Usage Drop", "is_weather_risk": "Weather Risk",
}  # 12 entries — extend to 19 (append the 7 new flag→label mappings; preserves category grouping)

NEGATIVE_FLAGS = frozenset({
    "is_ruled_out", "is_inactive", "is_suspended",
    "is_usage_drop", "is_weather_risk", "is_released",
})  # 6 entries — extend with new bearish flags

POSITIVE_FLAGS = frozenset({
    "is_returning", "is_activated", "is_usage_boost", "is_signed",
})  # 4 entries — extend with new bullish flags

NEUTRAL_FLAGS = frozenset({"is_traded", "is_questionable"})  # 2 entries — extend

def _bucket_for_flag(flag: str) -> Optional[str]:  # returns "negative"|"positive"|"neutral"
def _classify_sentiment(negative: int, positive: int, neutral: int) -> str:  # returns label
def _extract_event_flags(silver_rec: Dict) -> List[str]:
    """Walks events sub-dict and emits the human-readable EVENT_LABELS value for any
    True flag. AFTER 72-04: also emits the 7 new labels when their flags are set."""

def get_team_event_density(season: int, week: int) -> List[Dict[str, Any]]:
    """Returns 32 rows; reads Silver signals + Bronze team hints. Currently does NOT
    consume non_player_news. AFTER 72-04: also load non_player_news + populate
    coach_news_count + team_news_count + staff_news_count per row."""

def _build_news_item_from_bronze(bronze_rec, silver_rec=None) -> Dict[str, Any]:
    """Returns dict matching NewsItem shape. Reads events from silver_rec.
    AFTER 72-04: propagates subject_type + team_abbr to top level; 7 new flags
    flow into event_flags: List[str] via _extract_event_flags (no new top-level bools)."""
```

From web/frontend/src/lib/nfl/types.ts (Phase 61 final):

```typescript
export interface NewsItem {
  doc_id: string | null;
  title: string | null;
  source: string;
  url: string | null;
  published_at: string | null;
  sentiment: number | null;
  category: string | null;
  player_id: string | null;
  player_name: string | null;
  team: string | null;
  // Same 5 top-level bools as backend — no new bools added in 72-04.
  is_ruled_out: boolean;
  is_inactive: boolean;
  is_questionable: boolean;
  is_suspended: boolean;
  is_returning: boolean;
  body_snippet: string | null;
  // 7 new flag labels surface here as strings (existing pattern)
  event_flags: string[];
  summary: string | null;
}

export interface TeamEvents {
  team: string;
  negative_event_count: number;
  positive_event_count: number;
  neutral_event_count: number;
  total_articles: number;
  sentiment_label: OverallSentimentLabel;  // 'bullish' | 'bearish' | 'neutral'
  top_events: string[];
}
```

From web/frontend/src/features/nfl/components/EventBadges.tsx (NEWS-04 final):

```typescript
const BEARISH_LABELS: ReadonlySet<string> = new Set([
  'Ruled Out', 'Inactive', 'Suspended', 'Usage Drop', 'Weather Risk', 'Released'
]);
const BULLISH_LABELS: ReadonlySet<string> = new Set([
  'Returning', 'Activated', 'Usage Boost', 'Signed'
]);
const NEUTRAL_LABELS: ReadonlySet<string> = new Set(['Traded', 'Questionable']);
function bucketForBadge(label: string): BadgeBucket { ... }
```

From web/frontend/package.json (verified by reading):
- `"test": "vitest run"` — single canonical test command. Use `npm test -- EventBadges` or `npx vitest run EventBadges` (both invoke the same vitest runner). Do NOT use `npm test -- --run` (no such flag passes through). Do NOT use a separate `typecheck` script — it does not exist in package.json. For type checking use `npx tsc --noEmit` directly.

CONTEXT D-02 bucket assignments for the 7 new flags (LOCKED):
- is_drafted → bullish (positive draft pick = good for fantasy)
- is_signed → bullish (already in POSITIVE_FLAGS — no change)
- is_rookie_buzz → bullish (player stock rising)
- is_coaching_change → neutral (depends on whether new coach favors player; can't pre-judge)
- is_trade_buzz → neutral (rumor, not consummated)
- is_rumored_destination → neutral (same — speculation)
- is_holdout → bearish (player not practicing/playing)
- is_cap_cut → bearish (player released, no roster spot)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend Pydantic NewsItem (subject_type + team_abbr ONLY) + TeamEvents schemas + news_service projections (RED→GREEN)</name>
  <read_first>
    - web/api/models/schemas.py lines 388-460 (NewsItem + TeamEvents definitions — verify the 5 top-level bools + event_flags: List[str] surface)
    - web/api/services/news_service.py lines 47-160 (EVENT_LABELS + bucket frozensets + helpers — locate _extract_event_flags), lines 522-643 (_build_news_item_from_bronze + _from_silver), lines 1326-1417 (get_team_event_density)
    - tests/web/ directory (find existing test_news_endpoints.py or test_news_service.py — check naming pattern)
  </read_first>
  <files>web/api/models/schemas.py, web/api/services/news_service.py, tests/web/test_news_endpoints.py</files>
  <behavior>
    - Test 1: NewsItem(source='rss', subject_type='coach', team_abbr='KC', event_flags=['Drafted', 'Coaching Change']) validates; .dict() includes subject_type='coach', team_abbr='KC', event_flags carrying the two label strings. NewsItem does NOT have an `is_drafted` top-level attribute (per CONTEXT Phase 72 Schema Note — would AttributeError on access).
    - Test 2: NewsItem(source='rss', subject_type='bogus') raises ValidationError (Literal restriction enforces 4 values)
    - Test 3: NewsItem(source='rss') (no new fields supplied) defaults to subject_type='player', team_abbr=None, event_flags=[]
    - Test 4: TeamEvents(team='KC') defaults coach_news_count=0, team_news_count=0, staff_news_count=0; .dict() exposes all 3 new keys
    - Test 5: news_service.EVENT_LABELS has cardinality == 19 + each new key maps to expected human label ('Drafted', 'Rumored Destination', 'Coaching Change', 'Trade Buzz', 'Holdout', 'Cap Cut', 'Rookie Buzz')
    - Test 6: news_service._bucket_for_flag('is_drafted') == 'positive'; ('is_holdout') == 'negative'; ('is_coaching_change') == 'neutral' — verify all 7 new mappings
    - Test 7: news_service.get_team_event_density(2025, 17) on a tmp tree containing a non_player_news file with 2 KC coach items + 1 BUF team item: KC row has coach_news_count == 2, team_news_count == 0, staff_news_count == 0; BUF row has coach_news_count == 0, team_news_count == 1; remaining 30 teams zero-filled
    - Test 8: news_service._build_news_item_from_bronze with silver_rec containing events.is_drafted=True + subject_type='coach' + team_abbr='KC' → returned dict has subject_type='coach', team_abbr='KC', and 'Drafted' present in event_flags list. Returned dict does NOT have an `is_drafted` top-level key (locks the no-new-top-level-bool contract).
  </behavior>
  <action>
    Per CONTEXT "Phase 72 Schema Note" (LOCKED — amendment to "API + Frontend Integration"):

    1. Edit `web/api/models/schemas.py::NewsItem`:
       - **Add EXACTLY two new top-level fields after `summary`:**
         - `subject_type: Optional[Literal["player", "coach", "team", "reporter"]] = "player"` with Field description from CONTEXT
         - `team_abbr: Optional[str] = Field(None, description="3-letter NFL team abbreviation when subject is non-player or enrichment is available")`
       - **Do NOT add 7 new boolean top-level fields.** The 7 new flags surface ONLY through the existing `event_flags: List[str]` field per CONTEXT Phase 72 Schema Note. The 5 pre-existing top-level bools (is_ruled_out, is_inactive, is_questionable, is_suspended, is_returning) stay as-is for back-compat — no new ones added.
       - Use `Literal` from `typing` (already imported at top of file — verify line 7).

    2. Edit `web/api/models/schemas.py::TeamEvents`:
       - Add 3 int fields after `top_events`, all `int = Field(0, description=...)`:
         `coach_news_count, team_news_count, staff_news_count` (with descriptions from CONTEXT noting staff_news_count is a placeholder for future GM/exec items, currently always 0)

    3. Edit `web/api/services/news_service.py`:
       - **Extend `EVENT_LABELS` dict by appending 7 new entries AFTER the existing 12** (preserves category grouping per the existing structure — do NOT alphabetise across the prior set):
         ```
         "is_drafted": "Drafted",
         "is_rumored_destination": "Rumored Destination",
         "is_coaching_change": "Coaching Change",
         "is_trade_buzz": "Trade Buzz",
         "is_holdout": "Holdout",
         "is_cap_cut": "Cap Cut",
         "is_rookie_buzz": "Rookie Buzz",
         ```
       - Extend `NEGATIVE_FLAGS` frozenset with: `"is_holdout", "is_cap_cut"`
       - Extend `POSITIVE_FLAGS` frozenset with: `"is_drafted", "is_rookie_buzz"`
       - Extend `NEUTRAL_FLAGS` frozenset with: `"is_coaching_change", "is_trade_buzz", "is_rumored_destination"`
       - **Verify `_extract_event_flags` already iterates EVENT_LABELS dict** — if so, the 7 new labels emit automatically into `event_flags: List[str]` whenever the underlying flag is True. If not, refactor `_extract_event_flags` to walk `EVENT_LABELS.items()` so it stays the single inflection point. NEVER add 7 separate handler branches.
       - In `_build_news_item_from_bronze` (line ~523): in the returned dict, add `"subject_type": (silver_rec or {}).get("subject_type", "player")` and `"team_abbr": (silver_rec or {}).get("team_abbr") or bronze_rec.get("team")` (silver wins). DO NOT add 7 new `is_<flag>` keys to the returned dict — the new flags already surface via `event_flags` (which is built from `_extract_event_flags(silver_rec)`).
       - Apply the same edits to `_build_news_item_from_silver` (line ~606).
       - Add new module constant `_NON_PLAYER_NEWS_DIR = SILVER_SENTIMENT_DIR / "non_player_news"` next to `_SILVER_SIGNALS_DIR`.
       - Add new helper `_load_non_player_news(season: int, week: int) -> List[Dict[str, Any]]`:
         ```
         """Load non_player_news envelope JSON records (D-06 fail-open: returns [] on any error)."""
         ```
       - Modify `get_team_event_density(season, week)` (line ~1326): after computing `by_team` from Silver records, ALSO load non_player_news records and group by team_abbr. For each team in the final results loop, if the team has non_player_news records, count by `subject_type`:
         - subject_type=='coach' → coach_news_count
         - subject_type=='team' → team_news_count
         - (reporter records do NOT contribute to the team rollup table per CONTEXT)
         - staff_news_count := 0 always (placeholder)
         Set the 3 new fields on the result dict; keep zero-filled defaults for teams with no non_player_news.

    4. Create `tests/web/test_news_endpoints.py` (or extend existing if present — check `ls tests/web/` first):
       - Use FastAPI TestClient OR direct service-layer calls (mirror existing test patterns under `tests/web/`).
       - Implement Tests 1-8 from the behavior block. Tests 1 + 8 explicitly assert that NewsItem does NOT carry `is_drafted` etc. as top-level attributes — locks the schema contract.
       - For Test 7, monkeypatch `_NON_PLAYER_NEWS_DIR` to a tmp_path and write a small envelope JSON.
       - For backend ValidationError (Test 2), assert via `pytest.raises(ValidationError)` from `pydantic`.

    5. Run targeted tests:
       `python -m pytest tests/web/test_news_endpoints.py -v`

    6. Commit:
       - `test(72-04): add failing tests for NewsItem/TeamEvents extensions + service projections`
       - `feat(72-04): extend NewsItem (subject_type + team_abbr only) + TeamEvents Pydantic + project new flags via news_service`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/web/test_news_endpoints.py -v && python -c "
from web.api.services.news_service import EVENT_LABELS, NEGATIVE_FLAGS, POSITIVE_FLAGS, NEUTRAL_FLAGS
from web.api.models.schemas import NewsItem
assert len(EVENT_LABELS) == 19
assert 'is_holdout' in NEGATIVE_FLAGS
assert 'is_drafted' in POSITIVE_FLAGS
assert 'is_coaching_change' in NEUTRAL_FLAGS
n = NewsItem(source='rss')
assert not hasattr(n, 'is_drafted'), 'CONTEXT Phase 72 Schema Note: NewsItem must NOT have is_drafted top-level field'
assert n.subject_type == 'player' and n.team_abbr is None and n.event_flags == []
print('OK')
"</automated>
  </verify>
  <done>
    Pydantic NewsItem accepts ONLY subject_type + team_abbr as new top-level fields (per CONTEXT Phase 72 Schema Note). TeamEvents accepts 3 new int fields with safe defaults. EVENT_LABELS has 19 entries (7 new appended after existing 12 — preserves category grouping); bucket frozensets cover all 7 new flags per CONTEXT bucket assignments. _extract_event_flags emits the 7 new labels into event_flags list when set. get_team_event_density projects coach_news_count + team_news_count + staff_news_count from non_player_news. Test module passes. Two commits land.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Extend frontend NewsItem TS type (subject_type + team_abbr only) + EventBadges component (RED→GREEN)</name>
  <read_first>
    - web/frontend/src/lib/nfl/types.ts (full — current NewsItem + TeamEvents definitions, lines 100-160)
    - web/frontend/src/features/nfl/components/EventBadges.tsx (full — current bucket sets + bucketForBadge function)
    - web/frontend/src/features/nfl/components/__tests__/ (check if a __tests__ dir exists; if so, mirror its test format)
    - web/frontend/AGENTS.md (Next.js conventions per repo CLAUDE.md)
    - web/frontend/package.json (verify `"test": "vitest run"` is the canonical script — already verified in context block)
  </read_first>
  <files>web/frontend/src/lib/nfl/types.ts, web/frontend/src/features/nfl/components/EventBadges.tsx, web/frontend/src/features/nfl/components/__tests__/EventBadges.test.tsx</files>
  <behavior>
    - Test 1: bucketForBadge('Drafted') === 'bullish'; bucketForBadge('Rookie Buzz') === 'bullish'
    - Test 2: bucketForBadge('Holdout') === 'bearish'; bucketForBadge('Cap Cut') === 'bearish'
    - Test 3: bucketForBadge('Coaching Change') === 'neutral'; bucketForBadge('Trade Buzz') === 'neutral'; bucketForBadge('Rumored Destination') === 'neutral'
    - Test 4: <EventBadges badges={['Drafted', 'Holdout', 'Coaching Change']} /> renders 3 Badge elements with correct color classes (snapshot OR class assertion). Mirrors existing test pattern of consuming labels from a string list (event_flags), NOT from per-flag boolean props.
    - Test 5: TypeScript compile passes — NewsItem.subject_type is 'player'|'coach'|'team'|'reporter', team_abbr is string|null. NewsItem does NOT have an `is_drafted` member (would TS-error if accessed).
  </behavior>
  <action>
    Per CONTEXT "Phase 72 Schema Note" (LOCKED) and "Frontend: extend EventBadgeMap":

    1. Edit `web/frontend/src/lib/nfl/types.ts`:
       - Add `subject_type: 'player' | 'coach' | 'team' | 'reporter';` and `team_abbr: string | null;` to `NewsItem` interface (place after `summary` field). Mirror the backend Pydantic shape exactly.
       - **Do NOT add 7 new boolean fields** to `NewsItem`. The 7 new flag labels surface via the existing `event_flags: string[]` field — same pattern as the other 7 prior in-list flags.
       - Add 3 int fields to `TeamEvents` interface after `top_events`:
         ```
         coach_news_count: number;
         team_news_count: number;
         staff_news_count: number;
         ```

    2. Edit `web/frontend/src/features/nfl/components/EventBadges.tsx`:
       - Extend `BEARISH_LABELS` set: add `'Holdout', 'Cap Cut'`
       - Extend `BULLISH_LABELS` set: add `'Drafted', 'Rookie Buzz'`
       - Extend `NEUTRAL_LABELS` set: add `'Coaching Change', 'Trade Buzz', 'Rumored Destination'`
       - Update the file header docstring comment to note "Plan 72-04 added 7 draft-season labels matching news_service.py EVENT_LABELS extension. Per CONTEXT Phase 72 Schema Note, all 19 labels arrive via the existing event_flags: string[] inflection point — no new boolean props consumed."
       - The component continues to consume labels out of the `event_flags` list — the existing pattern handles all 19 labels with no signature change.

    3. Create `web/frontend/src/features/nfl/components/__tests__/EventBadges.test.tsx`:
       - Use vitest + @testing-library/react (per repo testing convention — confirm via existing test under `web/frontend/src/`)
       - Implement Tests 1-4 from the behavior block.
       - For Test 4 use snapshot testing OR explicit className assertions (mirror existing tests).
       - For Test 5, the TypeScript compile happens via `npx tsc --noEmit` — no explicit test needed beyond ensuring types compile.

    4. Run frontend tests using the LOCKED single command (`package.json` defines `"test": "vitest run"`):
       `cd web/frontend && npm test -- EventBadges`
       Equivalent fallback if npm dispatch quirks: `cd web/frontend && npx vitest run EventBadges`. Use one of these — do NOT invent flags like `--run` (vitest 4 already runs once by default; the package script already includes `run`).

    5. Run TypeScript compile to confirm no type errors (no `typecheck` script exists — invoke tsc directly):
       `cd web/frontend && npx tsc --noEmit`

    6. Commit:
       - `test(72-04): add failing tests for EventBadges 7 new labels`
       - `feat(72-04): extend NewsItem TS (subject_type + team_abbr only) + EventBadges with 7 draft-season labels`
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering/web/frontend && npx vitest run EventBadges && npx tsc --noEmit</automated>
  </verify>
  <done>
    NewsItem TS type carries ONLY subject_type + team_abbr as new top-level fields (no new bools — locks CONTEXT Schema Note). TeamEvents TS type carries 3 new counts. EventBadges bucket sets contain all 19 labels. EventBadges.test.tsx passes (Tests 1-4). TypeScript compile passes via `npx tsc --noEmit`. Two commits land.
  </done>
</task>

<task type="auto">
  <name>Task 3: End-to-end smoke test (local) + write SUMMARY for Plan 72-04</name>
  <read_first>
    - .planning/phases/71-llm-primary-extraction/71-04-SUMMARY.md (mirror SUMMARY structure)
    - web/api/main.py (FastAPI app entry — confirm dev server start command)
  </read_first>
  <files>.planning/phases/72-event-flag-expansion/72-04-SUMMARY.md</files>
  <action>
    1. Run the full backend sentiment + web suite:
       `source venv/bin/activate && python -m pytest tests/sentiment/ tests/web/ --tb=short -q`

       Expected: Plan 72-03's 201+ + ~12 new from this plan = >= 213 passed, 0 failed.

    2. Local end-to-end smoke (no Railway deploy yet — that's Plan 72-05):
       Start the dev server in background:
       `cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && (uvicorn web.api.main:app --port 8000 &) && sleep 3`

       Curl the team-events endpoint:
       `curl -s "http://localhost:8000/api/news/team-events?season=2025&week=17" | python -m json.tool | grep -E "coach_news_count|team_news_count|staff_news_count" | head -10`

       Expected: each row shows the 3 new keys (zero-filled if no Silver data on disk yet — that's expected; real values land in Plan 72-05 backfill).

       Curl the player news endpoint with a known player:
       `curl -s "http://localhost:8000/api/news/player/00-0033873?season=2025&week=17&limit=1" | python -m json.tool | grep -E "subject_type|team_abbr|event_flags" | head -5`

       Expected: each NewsItem row shows the 2 new top-level keys (subject_type + team_abbr) and the event_flags list (which may include any of the 19 labels when applicable). Note: the 7 new flag names should NOT appear as top-level keys in the JSON — only as strings inside event_flags.

       Kill the dev server:
       `pkill -f "uvicorn web.api.main"`

    3. Write `.planning/phases/72-event-flag-expansion/72-04-SUMMARY.md` mirroring `71-04-SUMMARY.md` structure. Include:
       - `requirements-completed: [EVT-01 (full surface), EVT-02 (full surface)]` — note that EVT-04 + EVT-05 are validated in Plan 72-05 backfill
       - Total backend test count + new tests
       - Frontend test status
       - **Schema decision recap:** "Per CONTEXT Phase 72 Schema Note (locked amendment), NewsItem gained ONLY subject_type + team_abbr at top level. The 7 new flags surface via event_flags: List[str] — single inflection point through _extract_event_flags."
       - List of new EVENT_LABELS entries + their bucket assignment
       - Local smoke output snippet showing zero-filled new fields (proves wiring without depending on real backfill)
       - Risks: Railway must be redeployed for the new fields to appear in production (handled in Plan 72-05)

    4. Commit:
       `docs(72-04): plan summary — API + frontend extensions wired and tested`
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/sentiment/ tests/web/ --tb=no -q | tail -3 && test -f .planning/phases/72-event-flag-expansion/72-04-SUMMARY.md</automated>
  </verify>
  <done>
    Full sentiment + web suite green (>= 213 passed). Local smoke output captured in SUMMARY (showing the 2 new top-level keys + event_flags list, with no new top-level booleans). SUMMARY file lands. Single docs commit lands. Frontend EventBadges + types extension complete; ready for Plan 72-05 audit against Railway.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Pydantic schema → FastAPI response | Untrusted Silver records must validate against the additive Pydantic shape; bad subject_type values blocked by Literal |
| API JSON → frontend NewsItem TS type | Frontend trusts the API response shape; missing fields would show up as TypeScript runtime undefined |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-72-04-01 | Tampering | NewsItem.subject_type Pydantic field | mitigate | Pydantic Literal["player","coach","team","reporter"] enforces validation at API boundary; invalid Silver data raises ValidationError BEFORE the response leaves FastAPI. |
| T-72-04-02 | Information Disclosure | non_player_news Silver path read by news_service | accept | Same data Claude already produced in Plan 72-03; no new sensitive fields surface. |
| T-72-04-03 | Denial of Service | _load_non_player_news in news_service | mitigate | Wrapped in try/except returning [] on any error (D-06 fail-open). get_team_event_density continues to return 32 zero-filled rows on any failure. |
| T-72-04-04 | Tampering | EventBadges bucket sets | mitigate | TypeScript ReadonlySet prevents runtime mutation; new labels go through code review. Unknown labels default to neutral (existing fallback in bucketForBadge). |
| T-72-04-05 | Repudiation | Frontend NewsItem rendering | accept | Frontend renders what the API sends; doc_id traces back to Bronze + Silver records for audit. |
| T-72-04-06 | Schema sprawl | NewsItem top-level field growth | mitigate | CONTEXT Phase 72 Schema Note + Test 1/Test 8 explicitly lock the no-new-top-level-bool contract. Future plans cannot accidentally add per-flag bools without updating CONTEXT and the test asserts. |
</threat_model>

<verification>
- `python -m pytest tests/sentiment/ tests/web/ --tb=no -q | tail -3` → 213+ passed, 0 failed
- `python -c "from web.api.models.schemas import NewsItem, TeamEvents; n = NewsItem(source='x'); assert n.subject_type == 'player' and n.team_abbr is None and n.event_flags == []; assert not hasattr(n, 'is_drafted'); t = TeamEvents(team='KC'); assert t.coach_news_count == 0 and t.team_news_count == 0 and t.staff_news_count == 0; print('OK')"` exits 0
- `python -c "from web.api.services.news_service import EVENT_LABELS; assert len(EVENT_LABELS) == 19 and 'Drafted' in EVENT_LABELS.values() and 'Coaching Change' in EVENT_LABELS.values(); print('OK')"` exits 0
- Frontend: `cd web/frontend && npx vitest run EventBadges | tail -5` shows passed tests
- Frontend TS: `cd web/frontend && npx tsc --noEmit | tail -3` shows no errors
- Local smoke: `curl -s "http://localhost:8000/api/news/team-events?season=2025&week=17" | python -c "import json,sys; rows=json.load(sys.stdin); assert len(rows) == 32 and all('coach_news_count' in r for r in rows); print('OK')"` exits 0 (run only after `uvicorn` is up)
- `python -c "from web.api.models.schemas import NewsItem; n = NewsItem(source='x', subject_type='coach', team_abbr='KC', event_flags=['Drafted']); assert n.subject_type == 'coach' and 'Drafted' in n.event_flags; print('OK')"` exits 0
</verification>

<success_criteria>
- Pydantic NewsItem gains ONLY subject_type + team_abbr at top level (per CONTEXT Phase 72 Schema Note); 7 new flags surface exclusively via event_flags: List[str]
- Pydantic TeamEvents gains 3 new int counts with safe defaults
- Backend EVENT_LABELS + bucket frozensets cover all 19 flags; 7 new entries appended after existing 12 (preserves category grouping)
- get_team_event_density consumes non_player_news Silver channel; populates 3 new int columns per team row
- Frontend NewsItem + TeamEvents TS types match Pydantic shape exactly (no new top-level bools on NewsItem)
- EventBadges component renders the 7 new labels with CONTEXT-dictated bucket colors via the existing event_flags string-list pattern
- Backend + frontend tests pass; TypeScript compiles cleanly via `npx tsc --noEmit`
- Local smoke proves wiring end-to-end (zero-filled when no real data — that's expected pre-backfill)
- SUMMARY captures EVT-01 + EVT-02 full-surface closure + the schema decision recap
</success_criteria>

<output>
After completion, create `.planning/phases/72-event-flag-expansion/72-04-SUMMARY.md` mirroring `71-04-SUMMARY.md`.
</output>
</content>
</invoke>