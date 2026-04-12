---
phase: SV2-reddit-rule-extraction
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/ingest_sentiment_reddit.py
  - src/sentiment/processing/rule_extractor.py
  - src/sentiment/processing/pipeline.py
  - src/config.py
  - tests/test_rule_extractor.py
  - tests/test_reddit_ingestion.py
autonomous: true
requirements: [SV2-01, SV2-02, SV2-03, SV2-04]

must_haves:
  truths:
    - "Reddit posts from r/fantasyfootball and r/nfl are fetched and saved as Bronze JSON"
    - "Rule-based extractor produces PlayerSignal objects from plain text without any API key"
    - "Pipeline can run end-to-end using rule_extractor when no ANTHROPIC_API_KEY is set"
    - "Existing Claude extractor still works when API key IS available (hybrid mode)"
  artifacts:
    - path: "scripts/ingest_sentiment_reddit.py"
      provides: "Reddit scraper CLI"
      contains: "argparse"
    - path: "src/sentiment/processing/rule_extractor.py"
      provides: "Rule-based signal extraction"
      exports: ["RuleExtractor", "PlayerSignal"]
    - path: "tests/test_rule_extractor.py"
      provides: "Rule extractor unit tests"
      min_lines: 80
    - path: "tests/test_reddit_ingestion.py"
      provides: "Reddit ingestion tests"
      min_lines: 40
  key_links:
    - from: "src/sentiment/processing/rule_extractor.py"
      to: "src/sentiment/processing/extractor.py"
      via: "Same PlayerSignal dataclass output format"
      pattern: "PlayerSignal"
    - from: "src/sentiment/processing/pipeline.py"
      to: "src/sentiment/processing/rule_extractor.py"
      via: "Pipeline uses RuleExtractor as default, Claude as optional upgrade"
      pattern: "RuleExtractor"
    - from: "scripts/ingest_sentiment_reddit.py"
      to: "src/player_name_resolver.py"
      via: "Resolves player names from Reddit post text"
      pattern: "PlayerNameResolver"
---

<objective>
Build the Reddit scraper and rule-based extraction engine so the sentiment pipeline works
without an Anthropic API key. This is the foundation that unblocks the entire sentiment v2
system.

Purpose: The existing pipeline is blocked on ANTHROPIC_API_KEY (see ACTIVATION_BLOCKED.md).
Rule-based extraction makes the core pipeline functional immediately. Reddit adds a high-value
source (crowd sentiment, injury chatter) that RSS feeds miss.

Output: Two new scripts/modules, updated pipeline to auto-select extractor, tests.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md

@src/sentiment/processing/extractor.py
@src/sentiment/processing/pipeline.py
@src/config.py
@src/player_name_resolver.py
@scripts/ingest_sentiment_rss.py

<interfaces>
<!-- Key types and contracts the executor needs -->

From src/sentiment/processing/extractor.py:
```python
@dataclass
class PlayerSignal:
    player_name: str
    sentiment: float        # -1.0 to +1.0
    confidence: float       # 0.0 to 1.0
    category: str           # injury, usage, trade, weather, motivation, legal, general
    events: Dict[str, bool] # is_ruled_out, is_inactive, is_questionable, is_suspended, is_returning
    excerpt: str            # source text snippet

class ClaudeExtractor:
    def extract(self, doc: Dict[str, Any]) -> List[PlayerSignal]: ...
    def is_available(self) -> bool: ...
```

From src/config.py:
```python
SENTIMENT_CONFIG: Dict[str, Any] = {
    "rss_feeds": { ... },
    "staleness_hours": 72,
    "sentiment_multiplier_range": (0.70, 1.15),
    ...
}
SENTIMENT_LOCAL_DIRS: Dict[str, str] = {
    "rss": "data/bronze/sentiment/rss",
    "sleeper": "data/bronze/sentiment/sleeper",
    "reddit": "data/bronze/sentiment/reddit",
    ...
}
```

From src/player_name_resolver.py:
```python
class PlayerNameResolver:
    def resolve(self, name: str, team: str = None, position: str = None) -> Optional[str]: ...
```

From scripts/ingest_sentiment_rss.py (pattern to follow):
- JSON envelope: {"fetch_run_id", "source", "fetched_at", "season", "week", "items": [...]}
- Each item has resolved_player_ids from PlayerNameResolver
- Saves to data/bronze/sentiment/{source}/season=YYYY/
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Reddit scraper + rule-based extractor</name>
  <files>
    scripts/ingest_sentiment_reddit.py,
    src/sentiment/processing/rule_extractor.py,
    tests/test_rule_extractor.py,
    tests/test_reddit_ingestion.py
  </files>
  <behavior>
    - RuleExtractor.extract(doc) returns List[PlayerSignal] matching Claude extractor format
    - Injury patterns: "ruled out" -> sentiment=-0.9, is_ruled_out=True; "questionable" -> sentiment=-0.3, is_questionable=True; "full participant" -> sentiment=+0.3
    - Trade patterns: "traded" -> category="trade", sentiment=-0.2; "signed" -> sentiment=+0.2
    - Role patterns: "named starter" -> sentiment=+0.5, category="usage"; "benched" -> sentiment=-0.6
    - Positive signals: "breakout" -> sentiment=+0.4; "dominant" -> sentiment=+0.5
    - Negative signals: "struggling" -> sentiment=-0.3; "fumble issues" -> sentiment=-0.4
    - Multiple patterns in one text produce multiple signals (one per player mentioned)
    - RuleExtractor.is_available() always returns True (no external dependency)
    - Reddit scraper fetches from reddit.com/r/{subreddit}/new.json with User-Agent header
    - Reddit items saved in same JSON envelope format as RSS ingestion
    - Reddit scraper supports --subreddit, --limit, --verbose, --dry-run, --season flags
  </behavior>
  <action>
    **Rule-based extractor** (`src/sentiment/processing/rule_extractor.py`):
    Create a `RuleExtractor` class with the same interface as `ClaudeExtractor` (`.extract(doc) -> List[PlayerSignal]`, `.is_available() -> bool`).

    Pattern categories (regex-based, case-insensitive):
    1. **Injury status**: "ruled out|out for|sidelined" (-0.9, is_ruled_out), "doubtful" (-0.6, events), "questionable|game-time decision" (-0.3, is_questionable), "limited practice|limited participant" (-0.1), "full practice|full participant" (+0.3, is_returning), "DNP|did not practice" (-0.4), "activated from IR|returned to practice" (+0.4, is_returning)
    2. **Roster moves**: "traded to|dealt to" (-0.2, trade), "released|waived|cut" (-0.5, trade), "signed|claimed off waivers" (+0.2, trade), "activated from IR" (+0.4, trade)
    3. **Role changes**: "named starter|earned starting|promoted" (+0.5, usage), "benched|demoted|losing snaps" (-0.6, usage), "increased role|expanded role|more touches" (+0.3, usage), "decreased role|reduced workload" (-0.3, usage)
    4. **Positive performance**: "breakout|career game|dominant performance" (+0.4, general), "game-changing|monster game" (+0.5, general)
    5. **Negative performance**: "struggling|ineffective" (-0.3, general), "benched|fumble issues|drop problems" (-0.4, general)

    For each matched pattern:
    - Extract player names from surrounding text using PlayerNameResolver
    - Create PlayerSignal with appropriate sentiment, confidence (0.7 for rule-based), category, events
    - If no patterns match, return empty list
    - Confidence is always 0.7 (lower than Claude's typical 0.8-0.9) to reflect reduced accuracy

    **Reddit scraper** (`scripts/ingest_sentiment_reddit.py`):
    Follow the exact pattern of `scripts/ingest_sentiment_rss.py`:
    - Fetch `https://www.reddit.com/r/{subreddit}/new.json?limit={N}` with proper User-Agent
    - Default subreddits: r/fantasyfootball, r/nfl
    - Parse each post: title, selftext, author, created_utc, permalink, score, num_comments
    - Run PlayerNameResolver on title + selftext to resolve player mentions
    - Save as JSON envelope to `data/bronze/sentiment/reddit/season=YYYY/reddit_{subreddit}_{timestamp}.json`
    - Handle rate limiting (Reddit public API: 10 req/min) with simple sleep
    - Support --subreddit (default: fantasyfootball,nfl), --limit (default: 25), --verbose, --dry-run, --season

    **Tests**: Test each regex pattern category, test multi-pattern text, test empty text, test Reddit JSON parsing.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -m pytest tests/test_rule_extractor.py tests/test_reddit_ingestion.py -v</automated>
  </verify>
  <done>
    - RuleExtractor produces PlayerSignal objects for all 5 pattern categories
    - Reddit scraper can fetch and save posts (tested with mock/dry-run)
    - All tests pass
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire rule extractor into pipeline as default</name>
  <files>
    src/sentiment/processing/pipeline.py,
    src/config.py
  </files>
  <action>
    Modify `SentimentPipeline` in `pipeline.py` to support both extractors:

    1. Add `extractor_mode` parameter to `__init__`: "auto" (default), "rule", "claude"
       - "auto": Try Claude first (check `ClaudeExtractor.is_available()`), fall back to RuleExtractor
       - "rule": Always use RuleExtractor
       - "claude": Always use ClaudeExtractor (fails if no API key)

    2. In `__init__`, instantiate the appropriate extractor based on mode:
       ```python
       if extractor_mode == "auto":
           claude = ClaudeExtractor()
           if claude.is_available():
               self._extractor = claude
               logger.info("Using Claude extractor (API key available)")
           else:
               self._extractor = RuleExtractor()
               logger.info("Using rule-based extractor (no API key)")
       ```

    3. Update the `run()` method to use `self._extractor.extract(doc)` instead of hardcoded Claude call.

    4. Add "reddit" to the list of Bronze source directories the pipeline scans.

    5. In `src/config.py`, add Reddit config to SENTIMENT_CONFIG:
       ```python
       "reddit_subreddits": ["fantasyfootball", "nfl"],
       "reddit_post_limit": 25,
       "reddit_user_agent": "NFLDataEngineering/1.0",
       ```

    6. Verify the `SENTIMENT_LOCAL_DIRS` already has "reddit" key (it does per existing config).
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -m pytest tests/test_sentiment_processing.py tests/test_sentiment_integration.py -v</automated>
  </verify>
  <done>
    - Pipeline defaults to rule-based extraction when no ANTHROPIC_API_KEY is set
    - Pipeline uses Claude when API key is available
    - Pipeline scans Reddit Bronze directory alongside RSS and Sleeper
    - Existing tests still pass
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Reddit API -> Bronze | Untrusted user-generated content from Reddit |
| Rule extractor input | Arbitrary text from any source |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-SV2-01 | Spoofing | Reddit API | accept | Public JSON endpoint, no auth, read-only |
| T-SV2-02 | Tampering | Reddit posts | mitigate | Sentiment clamped to [-1,+1], multiplier clamped to [0.70,1.15] in weekly.py |
| T-SV2-03 | Info Disclosure | User-Agent | accept | Generic agent string, no PII |
| T-SV2-04 | DoS | Reddit rate limit | mitigate | 1-second sleep between requests, --limit cap |
</threat_model>

<verification>
1. `python scripts/ingest_sentiment_reddit.py --dry-run --verbose` shows parsed posts
2. `python -c "from src.sentiment.processing.rule_extractor import RuleExtractor; print(RuleExtractor().is_available())"` prints True
3. `python -c "from src.sentiment.processing.pipeline import SentimentPipeline; p = SentimentPipeline(); print(type(p._extractor).__name__)"` prints "RuleExtractor" when no API key set
4. All tests pass: `python -m pytest tests/test_rule_extractor.py tests/test_reddit_ingestion.py tests/test_sentiment_processing.py -v`
</verification>

<success_criteria>
- Rule-based extractor works without any external API key
- Reddit scraper fetches and saves posts in Bronze format
- Pipeline auto-selects extractor based on API key availability
- All existing sentiment tests continue to pass
</success_criteria>

<output>
After completion, create `.planning/phases/sentiment-v2/SV2-01-SUMMARY.md`
</output>
