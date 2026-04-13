# Unstructured Data Storage and Sentiment Analysis Pipeline

Version: Draft v1.0
Date: 2026-04-07
Status: Pre-implementation design

---

## Executive Summary

This document describes a sentiment and news-signal pipeline that ingests unstructured text (beat reporter tweets, RSS articles, injury reports, Reddit posts), extracts structured signals using Claude, and feeds those signals as a multiplier into the existing projection engine. The pipeline follows the project's established medallion pattern (Bronze → Silver → Gold) and is built to slot into the existing FastAPI + Supabase + S3 infrastructure planned for Phase W5.

The key architectural insight is that raw text never enters the projection engine directly. Instead it is processed into a narrow set of numerical features — a per-player-week sentiment multiplier and a set of discrete event flags — that are applied as a final adjustment layer on top of the existing heuristic and ML projections. This mirrors how the injury multiplier (`apply_injury_adjustments`) and Vegas multiplier (`_vegas_multiplier`) already work.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SOURCES                                                                     │
│                                                                              │
│  Twitter/X API v2  RSS Feeds  Reddit API  NFL Official  Sleeper MCP         │
│  (beat reporters) (ESPN/NFL) (r/ff)      (injury rpts) (news feed)          │
└──────────┬──────────────┬──────────┬────────────┬────────────┬──────────────┘
           │              │          │            │            │
           └──────────────┴──────────┴────────────┴────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │  BRONZE INGESTION    │
                          │  (raw text + meta)   │
                          │  S3: nfl-raw/        │
                          │  Supabase: raw_docs  │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼──────────┐
                          │  SILVER PROCESSING   │
                          │  Claude API:         │
                          │  - entity extract    │
                          │  - sentiment score   │
                          │  - category tag      │
                          │  - embedding gen     │
                          │  Supabase:           │
                          │  - doc_signals       │
                          │  - doc_embeddings    │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼──────────┐
                          │  GOLD AGGREGATION    │
                          │  Per-player-week:    │
                          │  - sentiment_mult    │
                          │  - event flags       │
                          │  - alert_signals     │
                          │  Parquet + Supabase  │
                          └──────────┬───────────┘
                                     │
           ┌─────────────────────────┼──────────────────────────┐
           │                         │                          │
┌──────────▼─────┐       ┌───────────▼──────┐       ┌──────────▼──────┐
│ projection_    │       │ graph_injury_     │       │  Website API    │
│ engine.py      │       │ cascade.py        │       │  /api/news      │
│ sentiment mult │       │ event trigger     │       │  /api/players/  │
└────────────────┘       └──────────────────┘       │  {id}/news      │
                                                     └─────────────────┘
```

---

## 1. Data Model

### 1.1 Supabase PostgreSQL Schemas

All tables live in a `sentiment` schema to isolate this subsystem from the existing `public` schema used by projections and predictions.

#### Table: `sentiment.raw_docs`

Stores the canonical record of every ingested document before any processing. S3 holds the full raw payload; this table holds the index and key metadata needed for deduplication and processing queues.

```sql
CREATE SCHEMA IF NOT EXISTS sentiment;

CREATE TABLE sentiment.raw_docs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(30) NOT NULL,
    -- Enum values: twitter, rss_espn, rss_nfl, rss_rotoworld,
    --              reddit, nfl_injury_report, nfl_inactives, sleeper
    external_id     VARCHAR(255),
    -- Source-specific unique ID (tweet ID, Reddit post ID, etc.)
    -- Used for deduplication. NULL for sources without native IDs.
    url             TEXT,
    title           TEXT,
    body_text       TEXT NOT NULL,
    author          VARCHAR(200),
    published_at    TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    season          SMALLINT NOT NULL,
    week            SMALLINT,
    -- NULL for off-season content
    s3_key          TEXT,
    -- Full S3 key to the raw JSON/text payload (nfl-raw bucket)
    processing_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- Values: pending, processing, done, failed, skipped
    processing_attempts SMALLINT DEFAULT 0,
    error_message   TEXT,
    UNIQUE(source, external_id)
    -- Prevents duplicate ingestion of the same tweet/post
);

CREATE INDEX idx_raw_docs_status ON sentiment.raw_docs(processing_status);
CREATE INDEX idx_raw_docs_published ON sentiment.raw_docs(published_at DESC);
CREATE INDEX idx_raw_docs_season_week ON sentiment.raw_docs(season, week);
```

#### Table: `sentiment.doc_signals`

One row per document per mentioned player. A single tweet mentioning three players produces three rows here — one per player. This is the primary Silver output.

```sql
CREATE TABLE sentiment.doc_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_doc_id      UUID NOT NULL REFERENCES sentiment.raw_docs(id) ON DELETE CASCADE,
    player_id       VARCHAR(20) NOT NULL,
    -- Matches nfl-data-py player_id format (e.g. "00-0036442")
    player_name     VARCHAR(100) NOT NULL,
    team            VARCHAR(5),
    season          SMALLINT NOT NULL,
    week            SMALLINT,
    -- Week the signal applies to (may differ from publication week)

    -- Sentiment
    sentiment_score DECIMAL(4,3) NOT NULL,
    -- Range: -1.0 (very negative) to +1.0 (very positive)
    sentiment_confidence DECIMAL(4,3) NOT NULL,
    -- Claude's expressed confidence: 0.0 to 1.0

    -- Categorization
    category        VARCHAR(20) NOT NULL,
    -- Values: injury, usage, trade, weather, lineup, scheme,
    --         practice, contract, general
    subcategory     VARCHAR(40),
    -- E.g. "hamstring", "snap_count_increase", "ruled_out"

    -- Event flags (binary signals for the projection engine)
    is_ruled_out    BOOLEAN DEFAULT FALSE,
    is_limited_practice BOOLEAN DEFAULT FALSE,
    is_full_practice BOOLEAN DEFAULT FALSE,
    is_depth_chart_rise BOOLEAN DEFAULT FALSE,
    is_depth_chart_drop BOOLEAN DEFAULT FALSE,
    is_inactive     BOOLEAN DEFAULT FALSE,
    -- Set only from official NFL inactive list (90 min pre-game)
    is_questionable BOOLEAN DEFAULT FALSE,
    is_doubtful     BOOLEAN DEFAULT FALSE,

    -- Extraction metadata
    extracted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_version   VARCHAR(30) NOT NULL,
    -- Claude model used (e.g. "claude-haiku-4-5")
    raw_excerpt     TEXT,
    -- The specific sentence(s) from the source that triggered extraction

    UNIQUE(raw_doc_id, player_id)
);

CREATE INDEX idx_doc_signals_player ON sentiment.doc_signals(player_id, season, week);
CREATE INDEX idx_doc_signals_category ON sentiment.doc_signals(category, season, week);
CREATE INDEX idx_doc_signals_flags ON sentiment.doc_signals(is_ruled_out, season, week)
    WHERE is_ruled_out = TRUE;
```

#### Table: `sentiment.doc_embeddings`

Stores vector embeddings for semantic search. Requires `pgvector` extension enabled in Supabase (available on all Supabase tiers, enabled via Dashboard → Extensions).

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE sentiment.doc_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_doc_id      UUID NOT NULL REFERENCES sentiment.raw_docs(id) ON DELETE CASCADE,
    player_id       VARCHAR(20) NOT NULL,
    embedding       vector(1536),
    -- Dimension matches text-embedding-3-small (OpenAI) or
    -- voyage-finance-2 (Voyage AI). See Section 5.2 for model choice.
    model           VARCHAR(50) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(raw_doc_id, player_id)
);

-- HNSW index for approximate nearest-neighbor search
-- m=16, ef_construction=64 are standard starting values
CREATE INDEX idx_embeddings_vector ON sentiment.doc_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

#### Table: `sentiment.player_week_signals`

Gold-layer aggregation. One row per player per week, consumed directly by the projection engine. This is the only table the projection engine reads.

```sql
CREATE TABLE sentiment.player_week_signals (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id               VARCHAR(20) NOT NULL,
    player_name             VARCHAR(100) NOT NULL,
    team                    VARCHAR(5) NOT NULL,
    season                  SMALLINT NOT NULL,
    week                    SMALLINT NOT NULL,

    -- Aggregated sentiment
    sentiment_multiplier    DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
    -- Range: 0.70 to 1.15. Applied multiplicatively on top of
    -- existing injury/vegas multipliers in projection_engine.py.
    -- Neutral = 1.0 (no news or balanced news).
    sentiment_score_avg     DECIMAL(4,3),
    sentiment_score_max     DECIMAL(4,3),
    sentiment_score_min     DECIMAL(4,3),
    doc_count               SMALLINT DEFAULT 0,
    -- Number of documents that contributed to this signal

    -- Event flags (OR of all contributing doc_signals)
    is_ruled_out            BOOLEAN DEFAULT FALSE,
    is_inactive             BOOLEAN DEFAULT FALSE,
    is_questionable         BOOLEAN DEFAULT FALSE,
    is_doubtful             BOOLEAN DEFAULT FALSE,
    is_limited_practice     BOOLEAN DEFAULT FALSE,
    is_full_practice        BOOLEAN DEFAULT FALSE,
    is_depth_chart_rise     BOOLEAN DEFAULT FALSE,
    is_depth_chart_drop     BOOLEAN DEFAULT FALSE,

    -- Source breakdown
    twitter_doc_count       SMALLINT DEFAULT 0,
    rss_doc_count           SMALLINT DEFAULT 0,
    official_report_count   SMALLINT DEFAULT 0,
    reddit_doc_count        SMALLINT DEFAULT 0,

    -- Freshness
    latest_signal_at        TIMESTAMPTZ,
    -- Timestamp of most recent contributing document
    computed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    signal_staleness_hours  DECIMAL(5,1),
    -- Hours since latest_signal_at at computation time

    UNIQUE(player_id, season, week)
);

CREATE INDEX idx_player_week_signals_lookup
    ON sentiment.player_week_signals(player_id, season, week);
CREATE INDEX idx_player_week_signals_flags
    ON sentiment.player_week_signals(season, week, is_ruled_out, is_inactive);
```

#### Table: `sentiment.ingestion_runs`

Audit log for all ingestion runs. Used for monitoring, deduplication windows, and debugging.

```sql
CREATE TABLE sentiment.ingestion_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(30) NOT NULL,
    run_type        VARCHAR(20) NOT NULL,
    -- Values: batch, realtime, backfill
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    docs_fetched    INT DEFAULT 0,
    docs_new        INT DEFAULT 0,
    docs_duplicate  INT DEFAULT 0,
    docs_failed     INT DEFAULT 0,
    error_message   TEXT,
    metadata        JSONB
    -- Source-specific metadata (e.g. last tweet ID for cursor-based pagination)
);
```

---

### 1.2 S3 Key Patterns (Bronze Layer)

Raw payloads are stored in `nfl-raw` bucket alongside existing Bronze data. All keys follow the existing `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS` pattern.

```
# Twitter/X: one JSON file per fetch run containing up to 100 tweets
nfl-raw/sentiment/twitter/season=2026/week=01/twitter_20260407_083000.json

# RSS articles: one JSON array per source per fetch run
nfl-raw/sentiment/rss/season=2026/week=01/rss_espn_20260407_090000.json
nfl-raw/sentiment/rss/season=2026/week=01/rss_rotoworld_20260407_090000.json

# Reddit: one JSON file per subreddit per fetch run
nfl-raw/sentiment/reddit/season=2026/week=01/reddit_fantasyfootball_20260407_091500.json

# Official NFL injury reports (Wed/Thu/Fri practice reports)
nfl-raw/sentiment/official/season=2026/week=01/injury_report_wed_20260407.json

# NFL inactives (Sunday, 90 min before first game)
nfl-raw/sentiment/official/season=2026/week=01/inactives_20261004_113000.json

# Sleeper news feed
nfl-raw/sentiment/sleeper/season=2026/week=01/sleeper_news_20260407_100000.json
```

Each file is a JSON object (not JSON Lines) with the structure:
```json
{
  "fetch_run_id": "uuid",
  "source": "twitter",
  "fetched_at": "2026-04-07T08:30:00Z",
  "season": 2026,
  "week": 1,
  "items": [ ... ]
}
```

Individual items follow source-specific schemas documented in Section 2.

---

## 2. Ingestion Pipeline

### 2.1 Module Structure

New Python module at `src/sentiment/`:

```
src/sentiment/
    __init__.py
    config.py               # Source configs, rate limits, cost caps
    ingestion/
        __init__.py
        twitter_ingestor.py     # Twitter/X API v2
        rss_ingestor.py         # ESPN, NFL.com, Rotoworld RSS
        reddit_ingestor.py      # Reddit PRAW
        official_ingestor.py    # NFL.com injury reports + inactives
        sleeper_ingestor.py     # Sleeper API (wraps existing MCP)
        base.py                 # BaseIngestor ABC
    processing/
        __init__.py
        entity_extractor.py     # Claude-powered NER + player lookup
        sentiment_analyzer.py   # Claude-powered sentiment scoring
        embedder.py             # Embedding generation
        player_resolver.py      # Fuzzy name -> player_id mapping
    aggregation/
        __init__.py
        signal_aggregator.py    # Silver -> Gold aggregation
        multiplier_calculator.py # sentiment_score -> multiplier
    storage/
        __init__.py
        s3_store.py             # Raw payload S3 writes
        db_store.py             # Supabase writes (raw_docs, doc_signals)
    alerts/
        __init__.py
        alert_dispatcher.py     # Trigger injury cascade + notify
```

New scripts at `scripts/`:
```
scripts/ingest_sentiment.py         # Manual/scheduled batch ingest
scripts/process_sentiment.py        # Process pending raw_docs
scripts/aggregate_sentiment.py      # Build player_week_signals
scripts/realtime_sentiment.py       # Game-day polling loop
```

### 2.2 Source-by-Source Ingestion

#### Twitter/X API v2

Access tier: Basic ($100/month) provides 10,000 tweets/month read. Free tier (500 tweets/month) is too low for game day coverage. The elevated tier ($5,000/month) is unnecessary.

The key beat reporters and accounts to follow (stored in `src/sentiment/config.py`):

```python
TWITTER_ACCOUNTS = [
    # NFL insiders
    "AdamSchefter",    "RapSheet",        "TomPelissero",
    "MikeGarafolo",   "FieldYates",      "JordanRaanan",
    # Team beat reporters (sample — full list in config)
    "MattDeaderick",  "BuffaloBills",    "Chiefs",
    # Fantasy-specific
    "MarcusThurmond", "HarrisonBenjami", "IanHartitz",
]

TWITTER_KEYWORDS = [
    "ruled out", "inactive", "limited practice", "full practice",
    "IR", "placed on", "depth chart", "starting", "fantasy"
]
```

Ingestion approach: Use the Twitter v2 `filtered_stream` endpoint for real-time on game day (Sunday) and the `recent_search` endpoint for batch (Monday-Saturday). Both require OAuth 2.0 Bearer Token.

The ingestor stores raw tweet objects (id, text, author_id, created_at, entities) as JSON in S3, then writes a minimal record to `raw_docs` with `processing_status = 'pending'`.

Rate limit handling: 300 requests per 15-minute window for Basic tier. The ingestor implements token-bucket throttling and exponential backoff on 429 responses.

#### RSS Feeds

Free. No API key required for standard RSS. Use `feedparser` library (already available in Python ecosystem).

```python
RSS_FEEDS = {
    "espn_news":      "https://www.espn.com/espn/rss/nfl/news",
    "nfl_news":       "https://www.nfl.com/rss/rsslanding",
    "rotoworld":      "https://www.nbcsports.com/rotoworld/rss/nfl-player-news",
    "pro_football_talk": "https://profootballtalk.nbcsports.com/feed/",
    "fantasy_pros":   "https://www.fantasypros.com/nfl/rss/player-news.php",
}
```

Deduplication: Use the RSS item `guid` field as `external_id`. Items are checked against `raw_docs(source, external_id)` before processing.

Poll frequency: Every 15 minutes during in-season weeks. Every 6 hours during off-season.

#### Reddit

Free API via PRAW (Python Reddit API Wrapper). Rate limit: 60 requests/minute for OAuth apps.

Target subreddits: `r/fantasyfootball` (3M members), `r/nfl`.

Strategy: Monitor the "hot" and "new" feeds. Filter to posts with NFL player names in title. Extract comments on relevant posts (top 20 comments only). Use post/comment IDs as `external_id`.

Reddit is lower priority for individual player signals but useful for crowd sentiment on breakout candidates and bust calls.

#### Official NFL Injury Reports

No API — scrape the published PDF/HTML reports from `nfl.com`.

Schedule:
- Wednesday: practice participation report (published ~6 PM ET)
- Thursday: injury report (published ~5 PM ET)
- Friday: official injury report with game status designations (published ~4 PM ET)
- Sunday: inactives list (exactly 90 minutes before the first game of the day, typically 11:30 AM ET for 1 PM games)

The `official_ingestor.py` uses `httpx` to fetch the NFL injury report page and `BeautifulSoup` to parse the structured table. Each player row maps directly to a structured dict — no Claude processing needed for official reports since they follow a rigid schema.

Priority note: Official injury reports are the highest-authority source. When `is_ruled_out` or `is_inactive` comes from an official report, it overrides any Twitter-sourced flags and sets the projection multiplier to 0.0, consistent with the existing `apply_injury_adjustments` behavior.

#### Sleeper API

Sleeper's news feed is already accessible via the existing MCP integration. The `sleeper_ingestor.py` calls the Sleeper `get_trending_players` and player news endpoints. This is free, requires no additional API key, and provides pre-structured player news with player IDs already attached — avoiding the need for entity extraction in many cases.

```python
# Sleeper news item already has player_id
{
    "player_id": "4046",    # Sleeper player ID, needs mapping to nfl-data-py ID
    "news_body": "Patrick Mahomes limited in practice...",
    "news_date": "2026-04-07T14:00:00Z",
    "analyst": "Rotoworld"
}
```

The main task for Sleeper items is mapping Sleeper player IDs to the nfl-data-py `player_id` format. A mapping table is maintained in `src/sentiment/config.py`, generated once via `scripts/build_player_id_map.py`.

---

## 3. Processing Pipeline

### 3.1 Claude-Powered Extraction

All text processing goes through Claude. The choice of Claude model depends on the task:

| Task | Model | Reason |
|------|-------|--------|
| Entity extraction + sentiment from tweet (<280 chars) | `claude-haiku-4-5` | Cheap, fast, sufficient for structured extraction |
| Long RSS article analysis | `claude-haiku-4-5` | Same — the prompt template does the heavy lifting |
| Ambiguous or conflicting signals | `claude-sonnet-4-6` | Reserved for reconciliation on game day only |
| Embedding generation | OpenAI `text-embedding-3-small` | $0.02/1M tokens; pgvector compatible |

The processor reads rows from `raw_docs` where `processing_status = 'pending'` in batches of 50. For each document it runs the following prompt:

```python
EXTRACTION_PROMPT = """
You are an NFL news analyst. Extract structured information from this text.

Text: {body_text}
Source: {source}
Published: {published_at}

Return a JSON array. Each element represents one NFL player mentioned.
If no specific player is mentioned, return an empty array [].

For each player return:
{{
  "player_name": "full name as written in source",
  "team": "3-letter NFL abbreviation or null",
  "sentiment_score": float between -1.0 and 1.0,
    // -1.0 = very negative (ruled out, torn ACL)
    // 0.0 = neutral (mentioned, no clear direction)
    // +1.0 = very positive (full practice, cleared to play)
  "sentiment_confidence": float between 0.0 and 1.0,
  "category": one of [injury, usage, trade, weather, lineup, scheme, practice, contract, general],
  "subcategory": specific description or null,
  "is_ruled_out": bool,
  "is_limited_practice": bool,
  "is_full_practice": bool,
  "is_depth_chart_rise": bool,
  "is_depth_chart_drop": bool,
  "is_questionable": bool,
  "is_doubtful": bool,
  "is_inactive": bool,
  "raw_excerpt": "the specific sentence(s) that support this signal"
}}

Rules:
- Only include fantasy-relevant positions: QB, RB, WR, TE, K
- Only extract signals that are news (not historical references or speculation)
- is_ruled_out = true only if the text explicitly states the player will not play
- is_inactive = true only if this is from an official inactive list
"""
```

The response is parsed and validated before writing to `doc_signals`. Malformed responses (not valid JSON) cause a retry with the Sonnet model before marking the document as failed.

### 3.2 Player Resolution

Player name extraction from Claude ("Patrick Mahomes", "Mahomes", "Pat Mahomes") must resolve to a canonical `player_id`. The `player_resolver.py` module:

1. First checks an exact-match cache (in-memory dict loaded from a CSV mapping table)
2. Falls back to fuzzy matching using `rapidfuzz` against the current roster
3. For ambiguous cases (e.g. "Diggs" when both Stefon Diggs and Trevon Diggs are active), uses team context from the document to disambiguate
4. Unresolvable names are logged and stored with `player_id = NULL` in `doc_signals`; they do not contribute to `player_week_signals`

The mapping CSV is rebuilt weekly from the Bronze rosters parquet via `scripts/build_player_id_map.py`.

### 3.3 Embedding Generation

Embeddings are generated for the full document body text, truncated to 8,192 tokens. The embedding represents the document content for semantic search queries like "find all news about Josh Allen's shoulder injury this season."

Each embedding is stored in `doc_embeddings` alongside the `player_id` so searches can be scoped to a specific player.

Embedding model: OpenAI `text-embedding-3-small` (1536 dimensions, $0.02 per 1M tokens). At an estimated 500 documents/week × 52 weeks = 26,000 documents/year at ~200 tokens average = 5.2M tokens/year = $0.10/year. Cost is negligible.

Embeddings are generated asynchronously after signal extraction — they are not on the critical path for projection adjustment.

---

## 4. Signal Extraction: Unstructured Data to Numerical Features

### 4.1 Multiplier Calculation

The `multiplier_calculator.py` converts aggregated `doc_signals` for a player-week into a single `sentiment_multiplier` that the projection engine applies.

Design principles:
- The multiplier range is intentionally narrow: **0.70 to 1.15**. Sentiment signals are noisy and should not dominate the established statistical models.
- Official injury designations (ruled_out, inactive) set the multiplier to 0.0 and bypass the range — this is handled by the existing `apply_injury_adjustments` function, not by the sentiment multiplier. The sentiment system only flags these; the projection engine acts on them.
- The multiplier is only applied when `doc_count >= 2` to prevent single-tweet overreactions.

```python
def calculate_sentiment_multiplier(
    sentiment_score_avg: float,
    doc_count: int,
    category_weights: dict[str, float],
    staleness_hours: float,
) -> float:
    """
    Convert aggregated sentiment signals to a projection multiplier.

    Args:
        sentiment_score_avg: Weighted average sentiment (-1.0 to +1.0)
        doc_count: Number of contributing documents
        category_weights: Weight per category (injury > usage > general)
        staleness_hours: Hours since most recent signal

    Returns:
        Multiplier in range [0.70, 1.15]. Returns 1.0 if insufficient data.
    """
    if doc_count < 2:
        return 1.0

    # Staleness decay: signals older than 72 hours decay to neutral
    staleness_decay = max(0.0, 1.0 - (staleness_hours / 72.0))

    # Scale sentiment to multiplier range
    # sentiment +1.0 -> multiplier 1.15 (positive news boost)
    # sentiment  0.0 -> multiplier 1.00 (neutral)
    # sentiment -1.0 -> multiplier 0.70 (strong negative news)
    base_multiplier = 1.0 + (sentiment_score_avg * 0.15 * staleness_decay)

    # Additional confidence scaling: low-confidence signals shrink toward 1.0
    confidence_scale = min(1.0, doc_count / 5.0)
    multiplier = 1.0 + (base_multiplier - 1.0) * confidence_scale

    return max(0.70, min(1.15, multiplier))
```

### 4.2 Integration with projection_engine.py

The sentiment multiplier is applied as a final step after all existing multipliers. The integration point in `projection_engine.py` is the `apply_sentiment_adjustments` function (new), called after `apply_injury_adjustments` and the Vegas multiplier:

```python
def apply_sentiment_adjustments(
    projections_df: pd.DataFrame,
    player_week_signals: pd.DataFrame,
) -> pd.DataFrame:
    """
    Apply sentiment multipliers from the Silver sentiment layer.

    Called after apply_injury_adjustments() and _vegas_multiplier().
    Does not override players already zeroed out by injury status.

    Args:
        projections_df: Output of generate_weekly_projections()
        player_week_signals: DataFrame from sentiment.player_week_signals
            for the relevant season/week.

    Returns:
        projections_df with projected_points adjusted by sentiment_multiplier.
    """
    if player_week_signals.empty:
        return projections_df

    merged = projections_df.merge(
        player_week_signals[["player_id", "sentiment_multiplier",
                              "is_ruled_out", "is_inactive",
                              "is_questionable", "is_doubtful"]],
        on="player_id",
        how="left",
    )

    # Default to neutral multiplier where no signal exists
    merged["sentiment_multiplier"] = merged["sentiment_multiplier"].fillna(1.0)

    # Do not apply sentiment multiplier to players already zeroed by injury system
    active_mask = merged["projected_points"] > 0
    merged.loc[active_mask, "projected_points"] *= merged.loc[
        active_mask, "sentiment_multiplier"
    ]

    # Propagate event flags for downstream use (draft assistant, website)
    return merged
```

The sentiment event flags (`is_questionable`, `is_doubtful`, `is_ruled_out`) are passed through to the API response and displayed on the website as status badges — distinct from the multiplier itself.

### 4.3 Integration with graph_injury_cascade.py

When `is_ruled_out = TRUE` is detected in a new `doc_signals` row sourced from an official report, the alert dispatcher triggers the injury cascade computation:

```python
# In src/sentiment/alerts/alert_dispatcher.py

def handle_ruled_out_event(player_id: str, season: int, week: int) -> None:
    """
    Trigger injury cascade analysis when a player is confirmed out.
    Calls identify_significant_injuries() and compute_redistribution()
    from graph_injury_cascade.py.
    """
    from graph_injury_cascade import identify_significant_injuries, compute_redistribution

    injuries = identify_significant_injuries(season=season)
    cascade = compute_redistribution(injuries, season=season)
    # cascade DataFrame contains teammates who benefit from the vacancy
    # These are returned via the /api/news/alerts endpoint
```

This wiring means the cascade computation happens automatically when official injury data lands, not just during the weekly batch run.

### 4.4 Integration with draft_optimizer.py

During draft, the `DraftAdvisor` class in `draft_optimizer.py` will have a new `sentiment_context` parameter that accepts the current `player_week_signals` DataFrame. When `--live-news` flag is passed to `draft_assistant.py`, a background thread polls for new signals every 60 seconds and refreshes the advisor's context.

---

## 5. Real-Time vs Batch Architecture

### 5.1 Run Schedule

```
┌─────────────────────────────────────────────────────────┐
│  MONDAY (next-day analysis)                             │
│  08:00 UTC  RSS + Twitter batch (weekly summary)        │
│  10:00 UTC  Silver processing + Gold aggregation        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  TUESDAY (pipeline day — existing weekly cron)          │
│  09:00 UTC  Existing pipeline (Bronze → Silver → Gold)  │
│  11:00 UTC  Sentiment signals appended to Gold output   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  WEDNESDAY through FRIDAY (practice reports)            │
│  Every 15 min  RSS + Sleeper polling                    │
│  18:00-21:00 ET  Official injury report scrape          │
│  21:00 UTC  Silver processing + Gold aggregation        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  SATURDAY                                               │
│  Every 30 min  Twitter + RSS polling                    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  SUNDAY (game day — highest frequency)                  │
│  08:00-11:30 ET  Every 5 min: Twitter filtered stream   │
│  11:30 ET  Inactives scrape (90 min before 1 PM games)  │
│  11:31 ET  Emergency Gold aggregation + API cache bust  │
│  11:32 ET  alert_dispatcher triggers cascade analysis   │
│  12:00-20:00 ET  Every 10 min: Twitter polling          │
└─────────────────────────────────────────────────────────┘
```

### 5.2 Real-Time Implementation

The game-day polling loop runs as a separate process via `scripts/realtime_sentiment.py`. It is not an always-on service — it is triggered by the GHA workflow at 8 AM ET on Sundays and terminates after the last game of the day.

```python
# scripts/realtime_sentiment.py (simplified)
def run_game_day_loop(season: int, week: int) -> None:
    """
    Game-day near-real-time ingestion loop.
    Runs from 8 AM ET until final whistle (~11 PM ET).
    """
    ingestors = [TwitterIngestor(), RSSIngestor(), SleeperIngestor()]
    processor = SentimentProcessor()
    aggregator = SignalAggregator()

    while not is_past_final_whistle():
        for ingestor in ingestors:
            new_docs = ingestor.fetch_new()
            processor.process_batch(new_docs)

        # Aggregate and refresh Gold layer every 10 minutes
        if should_refresh_gold():
            aggregator.build_player_week_signals(season=season, week=week)
            bust_api_cache(season=season, week=week)

        time.sleep(POLL_INTERVAL_SECONDS)  # 300 on Sunday pre-game, 600 in-game
```

The API cache bust invalidates the FastAPI in-memory cache (or Supabase row cache) so the Next.js frontend immediately reflects updated projections on page refresh.

### 5.3 Batch vs Real-Time Feature Distinction

| Feature | Batch (Tue pipeline) | Real-Time (game day) |
|---------|---------------------|---------------------|
| `sentiment_multiplier` | Yes — full week's news | Yes — updated every 10 min |
| `is_ruled_out` | Yes | Yes — primary path |
| `is_inactive` | No | Yes — Sunday only |
| Injury cascade | Weekly | Triggered on ruled_out event |
| Embeddings | Yes — full corpus | No — deferred to batch |
| Reddit signals | Yes | No — too noisy for real-time |
| Official reports | Wed/Thu/Fri batch | Sunday inactives real-time |

---

## 6. API Design

### 6.1 New FastAPI Endpoints

Added to `web/api/routers/news.py`:

```
GET /api/news/players/{player_id}
    ?season=2026
    &week=1
    &limit=20

    Returns the N most recent documents mentioning this player,
    with their extracted sentiment signals.

    Response:
    {
      "player_id": "00-0036442",
      "player_name": "Josh Allen",
      "season": 2026,
      "week": 1,
      "sentiment_summary": {
        "sentiment_multiplier": 1.08,
        "sentiment_score_avg": 0.52,
        "doc_count": 7,
        "is_questionable": false,
        "is_ruled_out": false,
        "latest_signal_at": "2026-04-07T14:22:00Z"
      },
      "news_items": [
        {
          "id": "uuid",
          "source": "twitter",
          "author": "AdamSchefter",
          "body_text": "Josh Allen full practice Wednesday...",
          "published_at": "2026-04-07T14:22:00Z",
          "sentiment_score": 0.85,
          "category": "practice",
          "subcategory": "full_practice",
          "is_full_practice": true
        }
      ]
    }


GET /api/news/alerts
    ?season=2026
    &week=1
    &category=injury          (optional filter)
    &min_severity=high        (optional: high, medium, low)

    Returns active alerts for the current week (ruled out, inactive,
    major depth chart changes). Used for the website alert banner.

    Response:
    {
      "alerts": [
        {
          "player_id": "...",
          "player_name": "Saquon Barkley",
          "team": "PHI",
          "alert_type": "ruled_out",
          "alert_severity": "high",
          "source": "nfl_injury_report",
          "published_at": "2026-04-07T16:00:00Z",
          "headline": "Saquon Barkley ruled out Week 1...",
          "cascade_beneficiaries": [
            {"player_id": "...", "player_name": "Kenneth Gainwell", "share_delta": 0.18}
          ]
        }
      ]
    }


GET /api/news/search
    ?q=hamstring               (required, min 3 chars)
    &player_id=00-0036442      (optional, scope to player)
    &season=2026               (optional)
    &limit=10                  (optional, default 10)

    Semantic search using pgvector. Finds documents semantically
    similar to the query string.

    Response:
    {
      "query": "hamstring",
      "results": [
        {
          "id": "uuid",
          "player_name": "Josh Allen",
          "source": "twitter",
          "body_text": "...",
          "published_at": "...",
          "similarity_score": 0.87,
          "sentiment_score": -0.6
        }
      ]
    }


POST /api/news/ingest/manual
    (admin only, requires elevated API key)
    Body: { "text": "...", "source": "manual", "player_name": "...", "season": 2026, "week": 1 }

    Allows manual injection of a news item (for testing or when a
    critical piece of news is not being captured by automated ingestors).
```

### 6.2 Website Integration Points

The Next.js frontend consumes these endpoints in three places:

1. **Player detail page** (`/players/[slug]`): A `PlayerNewsPanel` component at the bottom of the page calls `/api/news/players/{player_id}` and renders a vertical list of news items with sentiment badges (positive/neutral/negative color coding). The `sentiment_multiplier` is shown as a small label: "News: +8%" or "News: -15%".

2. **Projections table** (`/projections`): Rows with active event flags show status badges: `OUT`, `DOUBT`, `Q`, `RISE`, `DROP`. These are populated from the `sentiment_summary` embedded in the projections response (the backend enriches the existing `/api/v1/projections` response with flags from `player_week_signals`).

3. **Alert banner**: A sticky banner at the top of all pages calls `/api/news/alerts` and shows the top 3 high-severity alerts for the current week. Updated every 5 minutes on game day via client-side polling.

---

## 7. Cost Estimate

### 7.1 API Costs (Annual, in-season = 18 weeks)

| Service | Usage | Unit Cost | Annual Cost |
|---------|-------|-----------|-------------|
| Twitter/X Basic | 10,000 tweets/month × 12 | $100/month | $1,200/year |
| Claude Haiku | ~500 docs/week × 18 weeks × ~500 tokens/call | $0.25/M input + $1.25/M output | ~$6/year |
| Claude Sonnet | ~50 reconciliation calls/week × 18 weeks | $3/M input + $15/M output | ~$1/year |
| OpenAI Embeddings | ~500 docs/week × 200 tokens | $0.02/M tokens | <$0.01/year |
| Reddit API | Free (OAuth app) | $0 | $0 |
| RSS feeds | Free | $0 | $0 |
| Sleeper API | Free | $0 | $0 |

Twitter is the only significant cost at $1,200/year. If budget is a constraint, start with the free tier (500 tweets/month) and RSS feeds only — this covers roughly 60% of meaningful news at $0 API cost. Twitter can be added when the system is proven useful.

### 7.2 Storage Costs (Annual)

| Component | Size Estimate | Cost |
|-----------|--------------|------|
| S3 raw docs (nfl-raw) | ~200 MB/year (text JSON is small) | ~$0.01/year |
| Supabase PostgreSQL | ~50 MB total (within free 500 MB tier) | $0 |
| pgvector embeddings | ~500 docs × 1536 floats × 4 bytes = ~3 MB/week × 18 = 54 MB | Within free tier |

Storage costs are negligible. The entire system fits within Supabase's free tier for at least 2-3 seasons.

### 7.3 Total Estimated Cost

- **Minimum viable (RSS + Sleeper only)**: $0/year
- **Full implementation (with Twitter Basic)**: ~$1,210/year
- **Claude processing**: <$10/year regardless of tier

---

## 8. Implementation Phases

### Phase S1: Foundation (1-2 weeks)

Build the storage layer and a single working ingestor before any ML processing.

Deliverables:
- Supabase schema migration (all 5 tables in `sentiment` schema)
- `src/sentiment/storage/` (S3 and DB writes)
- `src/sentiment/ingestion/rss_ingestor.py` (free, no API key needed)
- `src/sentiment/ingestion/sleeper_ingestor.py` (reuses existing MCP)
- `src/sentiment/ingestion/official_ingestor.py` (highest-value, free)
- `scripts/ingest_sentiment.py` with `--source rss,sleeper,official` flags
- Basic integration test: ingest one week of RSS, verify rows in `raw_docs`

Ship gate: 100+ documents ingested from RSS + official sources in one test run.

### Phase S2: Processing (1-2 weeks)

Add Claude-powered extraction and the player_week_signals Gold layer.

Deliverables:
- `src/sentiment/processing/entity_extractor.py`
- `src/sentiment/processing/sentiment_analyzer.py`
- `src/sentiment/processing/player_resolver.py`
- `scripts/build_player_id_map.py`
- `scripts/process_sentiment.py`
- `scripts/aggregate_sentiment.py`
- Backfill processing of Phase S1 documents

Ship gate: Process 100 documents, verify player resolution rate >80%, verify `player_week_signals` table populated with plausible multiplier values (0.90-1.10 range for typical news).

### Phase S3: Projection Integration (1 week)

Wire the sentiment multiplier into the projection engine.

Deliverables:
- `apply_sentiment_adjustments()` in `projection_engine.py`
- Updated `scripts/generate_projections.py` to load `player_week_signals`
- Backtest comparison: projections with and without sentiment multiplier on 2022-2024 data
- `src/sentiment/alerts/alert_dispatcher.py` → `graph_injury_cascade.py` trigger

Ship gate: Backtest shows sentiment multiplier does not degrade MAE (any improvement is a bonus; the gate is no degradation).

### Phase S4: Web API (1 week)

Surface news on the website.

Deliverables:
- `web/api/routers/news.py` with 4 endpoints
- `PlayerNewsPanel` component on player detail page
- Status badges on projections table rows
- Alert banner component

Ship gate: Player news loads within 300ms, status badges visible on 5+ players.

### Phase S5: Twitter + Real-Time (1-2 weeks)

Add Twitter integration and game-day loop.

Deliverables:
- `src/sentiment/ingestion/twitter_ingestor.py`
- `scripts/realtime_sentiment.py`
- Updated GHA workflow: Sunday game-day trigger
- API cache invalidation on Gold aggregation refresh

Ship gate: Sunday dry run before season start — inactives list scraped, processed, and reflected in projections within 5 minutes of official publication.

### Phase S6: Embeddings + Search (1 week, optional)

Add semantic search capability.

Deliverables:
- `src/sentiment/processing/embedder.py`
- Populate `doc_embeddings` table (batch backfill)
- `/api/news/search` endpoint

This phase can be deferred until the website needs a search feature.

---

## 9. Data Freshness and Staleness Handling

### 9.1 Signal Decay

Sentiment signals age out of relevance. A tweet from Wednesday predicting a hamstring concern is less actionable by Sunday. The `signal_staleness_hours` column in `player_week_signals` drives the decay function in `multiplier_calculator.py`:

- 0-24 hours: full weight (1.0)
- 24-48 hours: 75% weight
- 48-72 hours: 50% weight  
- 72+ hours: neutral (multiplier returns to 1.0)

This prevents stale week-old news from biasing projections in the next week's cycle.

### 9.2 Weekly Reset

On Monday of each new week, the `aggregate_sentiment.py` script starts a fresh `player_week_signals` row for the new week. The previous week's signals remain in `doc_signals` for historical analysis but do not carry forward into the new week's multiplier.

### 9.3 Archival Policy

`raw_docs` and `doc_signals`: Retained for 3 seasons (approximately 1,500 documents), then archived to S3 Glacier. `player_week_signals`: Retained indefinitely (small table, high analytical value). `doc_embeddings`: Retained for 1 season, then deleted (can be regenerated from `raw_docs` if needed).

### 9.4 Handling Missing Data

When no signals exist for a player-week (no news ingested), `sentiment_multiplier` defaults to exactly 1.0 — no adjustment. The projection engine treats absence of news as neutral, which is correct: most players have no meaningful news most weeks.

---

## 10. Privacy and Legal Considerations

### 10.1 Twitter/X Terms of Service

Twitter's Terms of Service (Section III) prohibit storing tweet content for longer than 30 days unless the data is used for research or analytics purposes. The architectural response:

- Store only the tweet text + metadata needed for processing (`body_text`, `author`, `external_id`, `published_at`)
- Do not store full tweet JSON objects (user profile images, follower counts, etc.)
- The S3 raw files (which contain full tweet JSON) are tagged for 30-day lifecycle expiration via S3 Object Lifecycle rules
- Processed signals in `doc_signals` contain only extracted data (player name, sentiment score, raw excerpt) — not the full tweet. This extracted data is more defensible as derivative/transformed data.
- Display tweet text on the website only by linking back to the original tweet, not by reproducing the text

### 10.2 RSS and Web Scraping

RSS feed terms of service vary by publisher. ESPN's RSS is published explicitly for syndication. Rotoworld/NBC Sports terms restrict automated access but permit reasonable rate-limited fetching for personal/research use.

Operational safeguards:
- Poll each RSS feed no more than once per 15 minutes
- Respect `Cache-Control` and `ETag` headers to avoid re-fetching unchanged feeds
- Include a `User-Agent` header identifying the application
- Store article summaries/excerpts, not full article text

For NFL.com injury reports: these are official public documents published by the NFL. No legal restriction on parsing them.

### 10.3 Reddit API

Reddit's Data API Terms require applications to identify themselves and not store user-generated content at scale for commercial purposes. Since this is a personal/research project:
- Only scrape public posts and comments (no private subreddits)
- Do not store Reddit usernames in `raw_docs` (set `author` to null for Reddit content)
- Respect rate limits: 60 requests/minute maximum

### 10.4 Claude API / Data Processing

Text processed through the Claude API is subject to Anthropic's usage policies. There is no restriction on sending publicly-available news text to the API for analysis. Do not send any personally identifiable information beyond public NFL player names.

### 10.5 GDPR / CCPA

All data stored is about public figures (NFL players) in their professional capacity. No end-user personal data is collected by this pipeline. No GDPR or CCPA obligations arise from this system.

---

## Appendix A: Key Design Decisions and Alternatives Considered

### Decision 1: Claude vs. Fine-tuned Open-Source Model

Chosen: Claude API (Haiku)
Alternative considered: Fine-tuned `distilbert-base-uncased` on an NFL news corpus

Rationale: Claude Haiku produces zero-shot structured JSON extraction that would require weeks of labeled training data to match with a fine-tuned model. At <$10/year, the cost advantage of a local model is not worth the development overhead for this project. The fine-tuned model becomes the better choice if volume exceeds ~10M documents/year.

### Decision 2: pgvector in Supabase vs. Dedicated Vector DB (Pinecone, Weaviate)

Chosen: pgvector extension in Supabase
Alternative considered: Pinecone (free tier: 100K vectors)

Rationale: Keeping vectors in the same Supabase database avoids a second service dependency. At 500 documents/week, the corpus stays well under 100K vectors for 2+ seasons. pgvector's HNSW index provides millisecond-range nearest-neighbor search at this scale. Pinecone becomes compelling if the corpus grows to millions of documents or if you need multi-tenant isolation.

### Decision 3: Sentiment Multiplier Range (0.70-1.15) vs. Wider Range

Chosen: 0.70-1.15
Alternative considered: 0.50-1.30 (matching the original usage multiplier range)

Rationale: Sentiment signals are inherently noisier than statistical usage signals. A tweet saying "Kelce looks great in practice" should not boost a projection by 30%. The narrow range means sentiment nudges projections rather than dominates them, which is appropriate until backtesting proves the signals have predictive value. The range can be widened in a future phase after empirical validation.

### Decision 4: Polling vs. Webhooks for Twitter

Chosen: Polling (filtered stream on Sundays, recent_search other days)
Alternative considered: Webhooks via Twitter Account Activity API (Enterprise tier only)

Rationale: Webhooks require Enterprise API access at prohibitive cost. The filtered stream endpoint at Basic tier covers game-day real-time needs adequately. 5-minute polling lag is acceptable — the critical inactives data comes from official NFL scraping, not Twitter.

---

## Appendix B: Python Module Dependencies

New dependencies to add to `requirements.txt`:

```
# Sentiment pipeline
feedparser>=6.0.10         # RSS parsing
praw>=7.7.1                # Reddit API
httpx>=0.27.0              # Async HTTP (replaces requests where needed)
beautifulsoup4>=4.12.3     # HTML parsing for NFL injury reports
rapidfuzz>=3.9.0           # Fuzzy player name matching
anthropic>=0.30.0          # Claude API (already in project)
openai>=1.40.0             # text-embedding-3-small
psycopg2-binary>=2.9.9     # PostgreSQL (already planned for Supabase)
pgvector>=0.3.2            # pgvector Python adapter
tweepy>=4.14.0             # Twitter API v2
apscheduler>=3.10.4        # Scheduled jobs for polling loops
```
