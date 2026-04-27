"""
Pydantic response models for the NFL Data Engineering API.

All models use ``Optional`` syntax compatible with Python 3.9.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PlayerProjection(BaseModel):
    """Fantasy projection for a single player-week."""

    player_id: str
    player_name: str
    team: str
    position: str = Field(..., description="QB / RB / WR / TE / K")
    projected_points: float
    projected_floor: float
    projected_ceiling: float

    # Stat projections (None when not applicable for position)
    proj_pass_yards: Optional[float] = None
    proj_pass_tds: Optional[float] = None
    proj_interceptions: Optional[float] = None
    proj_rush_yards: Optional[float] = None
    proj_rush_tds: Optional[float] = None
    proj_carries: Optional[float] = None
    proj_rec: Optional[float] = None
    proj_rec_yards: Optional[float] = None
    proj_rec_tds: Optional[float] = None
    proj_targets: Optional[float] = None

    # Kicker stats
    proj_fg_makes: Optional[float] = None
    proj_xp_makes: Optional[float] = None

    scoring_format: str
    season: int
    week: int

    # Metadata
    position_rank: Optional[int] = None
    injury_status: Optional[str] = None


class ProjectionComparisonRow(BaseModel):
    """A single row of the multi-source projection comparison (Phase 73-03)."""

    player_id: str
    player_name: str
    position: Optional[str] = None
    team: Optional[str] = None
    ours: Optional[float] = Field(None, description="Our Gold projection")
    espn: Optional[float] = Field(None, description="ESPN projection")
    sleeper: Optional[float] = Field(None, description="Sleeper projection")
    yahoo: Optional[float] = Field(
        None, description="Yahoo (via FantasyPros consensus proxy)"
    )
    delta_vs_ours: Optional[float] = Field(
        None,
        description="Average of external sources minus ours; positive = externals higher",
    )


class ProjectionComparison(BaseModel):
    """Response envelope for /api/projections/comparison."""

    season: int
    week: int
    scoring_format: str
    rows: List[ProjectionComparisonRow]
    source_labels: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Provenance map exposed to UI tooltips, e.g. "
            "{'yahoo': 'Yahoo via FantasyPros consensus'}"
        ),
    )
    data_as_of: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-source ISO 8601 freshness timestamps for the data_as_of chip",
    )


class SleeperUser(BaseModel):
    """Sleeper user identity (Phase 74 SLEEP-01)."""

    user_id: str
    username: str
    display_name: Optional[str] = None
    avatar: Optional[str] = None


class SleeperLeague(BaseModel):
    """A single Sleeper league the authenticated user is part of."""

    league_id: str
    name: str
    season: str
    total_rosters: Optional[int] = None
    sport: Optional[str] = "nfl"
    status: Optional[str] = None
    settings: Optional[dict] = None


class SleeperUserLoginResponse(BaseModel):
    """Response for /api/sleeper/user/login."""

    user: SleeperUser
    leagues: List[SleeperLeague] = Field(default_factory=list)


class SleeperRosterPlayer(BaseModel):
    """A single player slot on a Sleeper roster."""

    player_id: str
    player_name: Optional[str] = None
    position: Optional[str] = None
    team: Optional[str] = None
    slot: Optional[str] = Field(None, description="QB / RB / WR / TE / FLEX / BENCH")


class SleeperRoster(BaseModel):
    """A Sleeper roster — starters + bench grouped by slot."""

    roster_id: int
    league_id: str
    owner_user_id: Optional[str] = None
    is_user_roster: bool = Field(
        False,
        description="True if this roster belongs to the authenticated user",
    )
    starters: List[SleeperRosterPlayer] = Field(default_factory=list)
    bench: List[SleeperRosterPlayer] = Field(default_factory=list)


class GamePrediction(BaseModel):
    """Model prediction for a single game."""

    game_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    predicted_spread: float
    predicted_total: float
    vegas_spread: Optional[float] = None
    vegas_total: Optional[float] = None
    spread_edge: Optional[float] = None
    total_edge: Optional[float] = None
    confidence_tier: str = Field(..., description="high / medium / low")
    ats_pick: str = Field(..., description="home / away")
    ou_pick: str = Field(..., description="over / under")


class ProjectionMeta(BaseModel):
    """Upstream traceability metadata for a projection response.

    Populated by the Parquet backend so the AI advisor (and humans) can cite
    when the Gold layer was last refreshed. When the PostgreSQL backend is
    active we do not have a filesystem mtime, so ``data_as_of`` and
    ``source_path`` may be ``None``.
    """

    season: int
    week: int
    data_as_of: Optional[str] = Field(
        None, description="ISO 8601 UTC timestamp of the source parquet's mtime"
    )
    source_path: Optional[str] = Field(
        None, description="Relative path to the source parquet (or null for DB)"
    )


class ProjectionResponse(BaseModel):
    """Envelope for a list of player projections."""

    season: int
    week: int
    scoring_format: str
    projections: List[PlayerProjection]
    generated_at: str
    meta: Optional[ProjectionMeta] = Field(
        None,
        description=(
            "Upstream traceability — source parquet mtime. Populated for the "
            "Parquet backend; may be null for PostgreSQL."
        ),
    )


class LatestWeekResponse(BaseModel):
    """Latest-available (season, week) pair for the projections Gold layer.

    Returned by ``GET /api/projections/latest-week``. When no Gold data exists
    for the requested season, ``week`` and ``data_as_of`` are both ``None``
    but the response still carries HTTP 200.
    """

    season: int
    week: Optional[int] = None
    data_as_of: Optional[str] = None


class PredictionResponse(BaseModel):
    """Envelope for a list of game predictions."""

    season: int
    week: int
    predictions: List[GamePrediction]
    generated_at: str
    data_as_of: Optional[str] = Field(
        default=None,
        description=(
            "ISO timestamp of the underlying Gold parquet used for this response. "
            "Populated when the request defaulted to latest-played-week so the "
            "frontend can surface data freshness without a second roundtrip."
        ),
    )
    defaulted: bool = Field(
        default=False,
        description=(
            "True when season/week were not supplied and the service resolved them "
            "from Gold storage. Frontend uses this to avoid overwriting user-selected "
            "filters."
        ),
    )


class PlayerSearchResult(BaseModel):
    """Lightweight result for player search."""

    player_id: str
    player_name: str
    team: str
    position: str


class LineupPlayer(BaseModel):
    """A single player in a team lineup."""

    player_id: str
    player_name: str
    position: str
    position_group: str
    field_position: str = Field(
        ...,
        description=(
            "Layout label: qb, rb, wr_left, wr_right, wr_slot, te, k, "
            "edge_left, edge_right, dt_left, dt_right, lb_left, lb_mid, "
            "lb_right, cb_left, cb_right, s_left, s_right"
        ),
    )
    projected_points: Optional[float] = None
    projected_floor: Optional[float] = None
    projected_ceiling: Optional[float] = None
    snap_pct: Optional[float] = None
    depth_rank: int
    is_starter: bool
    starter_confidence: float


class TeamLineup(BaseModel):
    """Starting lineup for a single team-week."""

    team: str
    season: int
    week: int
    offense: List[LineupPlayer]
    defense: List[LineupPlayer]
    implied_total: Optional[float] = None
    team_projected_total: Optional[float] = None


class FlatLineupPlayer(BaseModel):
    """Flat lineup entry used by the AI advisor ``getTeamRoster`` tool.

    Mirrors the legacy ``LineupPlayer`` shape but carries the ``team`` code
    and an ``injury_status`` field at the top level so the advisor can render
    a single flat roster list without walking the per-team offense/defense
    nesting.
    """

    player_id: str
    player_name: str
    team: str
    position: str
    projected_points: Optional[float] = None
    projected_floor: Optional[float] = None
    projected_ceiling: Optional[float] = None
    injury_status: Optional[str] = None
    is_starter: bool = False


class LineupResponse(BaseModel):
    """Envelope for lineup endpoint responses.

    Carries two parallel representations so both the website's team-lineup
    widget and the AI advisor ``getTeamRoster`` tool see their expected
    schema:

    * ``lineups`` — legacy nested ``TeamLineup[]`` (offense/defense split).
    * ``lineup`` — advisor-friendly flat ``FlatLineupPlayer[]`` across all
      teams in the response (empty list when no data).
    """

    season: int
    week: int
    lineups: List[TeamLineup]
    lineup: List[FlatLineupPlayer] = Field(default_factory=list)
    generated_at: str
    data_as_of: Optional[str] = Field(
        default=None,
        description=(
            "ISO timestamp of the underlying Gold parquet used for this response. "
            "Populated when the request defaulted to latest-played-week."
        ),
    )
    defaulted: bool = Field(
        default=False,
        description=(
            "True when season/week were not supplied and the service resolved them "
            "from Gold storage."
        ),
    )


class HealthResponse(BaseModel):
    """Health-check payload."""

    status: str
    version: str
    db_status: Optional[str] = None
    llm_enrichment_ready: bool = Field(
        default=False,
        description=(
            "True when ANTHROPIC_API_KEY is set in the runtime environment, "
            "indicating the news extractor can run. Never leaks the key itself."
        ),
    )


# ---------------------------------------------------------------------------
# Game Archive models
# ---------------------------------------------------------------------------


class GameResult(BaseModel):
    """Score and result for a single NFL game."""

    game_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    winner: str
    point_spread_result: int
    total_points: int
    game_date: Optional[str] = None
    game_time: Optional[str] = None


class GamePlayerStat(BaseModel):
    """Fantasy stat line for a single player in a game."""

    player_id: str
    player_name: str
    team: str
    position: str
    fantasy_points: float
    passing_yards: Optional[float] = None
    passing_tds: Optional[float] = None
    rushing_yards: Optional[float] = None
    rushing_tds: Optional[float] = None
    receptions: Optional[float] = None
    receiving_yards: Optional[float] = None
    receiving_tds: Optional[float] = None
    targets: Optional[float] = None
    carries: Optional[float] = None


class GameDetail(BaseModel):
    """Full game detail with both teams' player stats."""

    game_info: GameResult
    home_players: List[GamePlayerStat]
    away_players: List[GamePlayerStat]
    top_performers: List[GamePlayerStat]


class GameListResponse(BaseModel):
    """Envelope for a list of game results."""

    season: int
    week: Optional[int] = None
    games: List[GameResult]
    count: int


class GameDetailResponse(BaseModel):
    """Envelope for a single game detail."""

    game: GameDetail
    scoring_format: str


class SeasonLeader(BaseModel):
    """Season-long fantasy point leader."""

    player_id: str
    player_name: str
    team: str
    position: str
    total_fantasy_points: float
    games_played: int
    ppg: float
    best_week: float
    worst_week: float


class SeasonLeadersResponse(BaseModel):
    """Envelope for season leaders."""

    season: int
    scoring_format: str
    position: Optional[str] = None
    leaders: List[SeasonLeader]


class PlayerGameLogEntry(BaseModel):
    """Single week entry in a player's game log."""

    week: int
    opponent: Optional[str] = None
    home_away: str
    fantasy_points: float
    game_result: str
    passing_yards: Optional[float] = None
    passing_tds: Optional[float] = None
    rushing_yards: Optional[float] = None
    rushing_tds: Optional[float] = None
    receptions: Optional[float] = None
    receiving_yards: Optional[float] = None
    receiving_tds: Optional[float] = None
    targets: Optional[float] = None
    carries: Optional[float] = None


class PlayerGameLogResponse(BaseModel):
    """Envelope for a player's game log."""

    player_id: str
    season: int
    scoring_format: str
    game_log: List[PlayerGameLogEntry]


class AvailableSeason(BaseModel):
    """Summary of an available season."""

    season: int
    game_count: int
    has_player_stats: bool


class SeasonsResponse(BaseModel):
    """Envelope for list of available seasons."""

    seasons: List[AvailableSeason]


# ---------------------------------------------------------------------------
# News / Sentiment models
# ---------------------------------------------------------------------------


class NewsItem(BaseModel):
    """A single news article or report associated with a player."""

    doc_id: Optional[str] = None
    title: Optional[str] = None
    source: str = Field(..., description="rss_espn / sleeper / rss_nfl / etc.")
    url: Optional[str] = None
    published_at: Optional[str] = None
    sentiment: Optional[float] = Field(None, description="Sentiment score in [-1, 1]")
    category: Optional[str] = Field(None, description="injury / usage / trade / etc.")
    player_id: Optional[str] = None
    player_name: Optional[str] = None
    team: Optional[str] = None

    # Event flags extracted from the document
    is_ruled_out: bool = False
    is_inactive: bool = False
    is_questionable: bool = False
    is_suspended: bool = False
    is_returning: bool = False

    body_snippet: Optional[str] = Field(
        None, description="First 200 chars of body text"
    )

    # Plan 61-05: human-readable event labels derived from the Silver events
    # dict. Empty list when the document has no rule-extracted events.
    event_flags: List[str] = Field(
        default_factory=list,
        description="Human-readable event labels (e.g. Questionable, Returning)",
    )

    # Plan 61-06 placeholder: LLM-enriched summary, populated only when the
    # optional Haiku enrichment step is enabled (D-04). Null otherwise.
    summary: Optional[str] = Field(
        None, description="Optional LLM-generated 1-sentence summary"
    )

    # Phase 72 EVT-02: subject attribution surface. Per CONTEXT Phase 72
    # Schema Note, NewsItem adds EXACTLY these two top-level fields. The 7
    # new draft-season flags (is_drafted, is_rumored_destination, etc.)
    # surface ONLY via the existing event_flags: List[str] field — no new
    # top-level boolean fields are introduced.
    subject_type: Optional[Literal["player", "coach", "team", "reporter"]] = Field(
        "player",
        description="Who/what the article is about (default 'player')",
    )
    team_abbr: Optional[str] = Field(
        None,
        description="3-letter team code when subject is a coach/team/reporter",
    )


class TeamEvents(BaseModel):
    """Aggregated per-team event counts used by the NEWS-03 density grid.

    Counts are derived from the structured event flags emitted by the
    rule-extractor (Plan 61-02). ``sentiment_label`` is a discrete bucket
    (``bullish``/``bearish``/``neutral``) — NOT a continuous score per D-03.
    """

    team: str = Field(..., description="3-letter team abbreviation")
    negative_event_count: int = Field(
        0,
        description=(
            "Bearish events: ruled_out, inactive, suspended, usage_drop, "
            "weather_risk, released"
        ),
    )
    positive_event_count: int = Field(
        0,
        description="Bullish events: returning, activated, usage_boost, signed",
    )
    neutral_event_count: int = Field(
        0, description="Neutral events: traded, questionable"
    )
    total_articles: int = Field(
        0, description="Total article/signal count contributing to this team"
    )
    sentiment_label: str = Field("neutral", description="bullish / bearish / neutral")
    top_events: List[str] = Field(
        default_factory=list,
        description="Human-readable summary of the 3 loudest events",
    )

    # Phase 72 EVT-02: non-player rollup counts populated by
    # team_weekly._load_non_player_counts. Reporter items are NEVER counted
    # here — they go to the separate non_player_news Silver channel.
    coach_news_count: int = Field(
        0, description="Coach-related news items rolled up to this team"
    )
    team_news_count: int = Field(
        0, description="Team-level news items (schedule, stadium, ownership)"
    )
    staff_news_count: int = Field(
        0, description="Staff news (placeholder for future GM/exec items)"
    )


class PlayerEventBadges(BaseModel):
    """Rule-extracted event badges for a single player (NEWS-04).

    Badges are deduplicated and sorted by occurrence count descending so
    the UI can render the most-mentioned event first. ``overall_label`` is
    a discrete bucket (D-03) — never a numerical sentiment score.
    """

    player_id: str
    badges: List[str] = Field(
        default_factory=list,
        description="Unique human-readable event labels, most frequent first",
    )
    overall_label: str = Field("neutral", description="bullish / bearish / neutral")
    article_count: int = Field(
        0, description="Number of Silver signal records for this player"
    )
    most_recent_article: Optional[NewsItem] = None


class Alert(BaseModel):
    """Active alert for a player — ruled out, inactive, or major sentiment shift."""

    player_id: str
    player_name: str
    team: Optional[str] = None
    position: Optional[str] = None
    alert_type: str = Field(
        ...,
        description="ruled_out / inactive / questionable / suspended / major_negative / major_positive",
    )
    sentiment_multiplier: Optional[float] = None
    latest_signal_at: Optional[str] = None
    doc_count: Optional[int] = None


class PlayerSentiment(BaseModel):
    """Aggregated weekly sentiment features for a single player."""

    player_id: str
    player_name: str
    season: int
    week: int
    sentiment_multiplier: float
    sentiment_score_avg: Optional[float] = None
    doc_count: int = 0
    is_ruled_out: bool = False
    is_inactive: bool = False
    is_questionable: bool = False
    is_suspended: bool = False
    is_returning: bool = False
    latest_signal_at: Optional[str] = None
    signal_staleness_hours: Optional[float] = None


class TeamSentiment(BaseModel):
    """Aggregated weekly sentiment summary for a single team."""

    team: str
    season: int
    week: int
    sentiment_score: float = 0.0
    sentiment_label: str = Field("neutral", description="positive / neutral / negative")
    signal_count: int = 0
    sentiment_multiplier: float = 1.0


# ---------------------------------------------------------------------------
# Draft models
# ---------------------------------------------------------------------------


class DraftPlayer(BaseModel):
    """A player on the draft board."""

    player_id: str
    player_name: str
    position: str
    team: Optional[str] = None
    projected_points: float
    model_rank: int
    adp_rank: Optional[float] = None
    adp_diff: Optional[float] = None
    value_tier: str = "fair_value"
    vorp: float = 0.0


class DraftBoardEntry(BaseModel):
    """Advisor-facing board entry.

    Simplified view used by the AI chat tool ``getDraftBoard`` (see
    ``web/frontend/src/app/api/chat/route.ts``). Mirrors :class:`DraftPlayer`
    but exposes the advisor-friendly ``adp`` / ``bye_week`` field names.
    """

    player_id: str
    player_name: str
    position: str
    team: Optional[str] = None
    projected_points: float
    adp: Optional[float] = None
    vorp: float = 0.0
    value_tier: str = "fair_value"
    bye_week: Optional[int] = None


class DraftBoardResponse(BaseModel):
    """Full draft board state.

    Carries two player views for backward compatibility:

    * ``players`` — legacy full-schema list consumed by the draft page
      (``web/frontend/src/features/draft/components/draft-tool-view.tsx``).
    * ``board`` — simplified list consumed by the AI advisor tool
      (``getDraftBoard`` in ``web/frontend/src/app/api/chat/route.ts``).

    Both lists reference the same available-player set; they only differ in
    field-name aliases (``adp_rank`` vs ``adp``) and the presence of
    ``bye_week``.
    """

    session_id: str
    players: List[DraftPlayer]
    board: List[DraftBoardEntry] = []
    my_roster: List[DraftPlayer]
    picks_taken: int
    my_pick_count: int
    remaining_needs: dict
    scoring_format: str
    roster_format: str
    n_teams: int


class DraftPickRequest(BaseModel):
    """Request to record a draft pick."""

    session_id: str
    player_id: str
    by_me: bool = True


class DraftPickResponse(BaseModel):
    """Response after a pick is recorded."""

    success: bool
    player: Optional[DraftPlayer] = None
    message: str = ""


class DraftRecommendation(BaseModel):
    """A recommended draft pick."""

    player_id: str
    player_name: str
    position: str
    team: Optional[str] = None
    projected_points: float
    model_rank: int
    vorp: float
    recommendation_score: float


class DraftRecommendationsResponse(BaseModel):
    """Recommendations for current draft position."""

    recommendations: List[DraftRecommendation]
    reasoning: str
    remaining_needs: dict


class MockDraftStartRequest(BaseModel):
    """Request to start a mock draft."""

    scoring: str = "half_ppr"
    roster_format: str = "standard"
    n_teams: int = 12
    user_pick: int = 1
    season: int = 2026


class MockDraftStartResponse(BaseModel):
    """Response after starting a mock draft."""

    session_id: str
    message: str


class MockDraftPickRequest(BaseModel):
    """Request to advance one pick in mock draft."""

    session_id: str


class MockDraftPickResponse(BaseModel):
    """Response after advancing a mock draft pick."""

    pick_number: int
    round_number: int
    is_user_turn: bool
    player_name: Optional[str] = None
    position: Optional[str] = None
    team: Optional[str] = None
    is_complete: bool = False
    draft_grade: Optional[str] = None
    total_pts: Optional[float] = None
    total_vorp: Optional[float] = None


class AdpPlayer(BaseModel):
    """A player's ADP entry."""

    player_name: str
    position: str
    team: Optional[str] = None
    adp_rank: float


class AdpResponse(BaseModel):
    """Latest ADP data."""

    players: List[AdpPlayer]
    source: str
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Teams / Roster / Current-Week models (Phase 64)
# ---------------------------------------------------------------------------


class CurrentWeekResponse(BaseModel):
    """Current NFL (season, week) pair derived from today's date and the latest
    local schedule parquet. ``source == 'schedule'`` means today's date falls inside
    a ``gameday .. gameday + 6 days`` window on a real schedule row; ``source ==
    'fallback'`` means the offseason/no-match path — the endpoint returned the
    max (season, week) found in the data lake.
    """

    season: int = Field(..., ge=2016, le=2030)
    week: int = Field(..., ge=1, le=22)
    source: Literal["schedule", "fallback"]


class RosterPlayer(BaseModel):
    """One row in a team's roster/starter response.

    ``slot_hint`` is a display-layer assignment (QB1/RB1/WR1/LT/RT/DE1/CB1/...) computed
    from snap_pct_* descending within the same depth_chart_position group. Entries
    outside the top-N per group carry ``slot_hint=None``.
    """

    player_id: str
    player_name: str
    team: str
    position: str
    depth_chart_position: Optional[str] = None
    jersey_number: Optional[int] = None
    status: str
    snap_pct_offense: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    snap_pct_defense: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    injury_status: Optional[str] = None
    slot_hint: Optional[str] = None


class TeamRosterResponse(BaseModel):
    """Response envelope for GET /api/teams/{team}/roster."""

    team: str
    season: int
    week: int
    side: Literal["offense", "defense", "all"]
    fallback: bool = False
    fallback_season: Optional[int] = None
    roster: List[RosterPlayer]
    defaulted: bool = Field(
        default=False,
        description=(
            "True when season/week were not supplied and the service resolved them "
            "from the latest schedule/roster parquet. Distinct from ``fallback`` which "
            "indicates the requested season had no roster data so an older one was used."
        ),
    )
    live_source: bool = Field(
        default=False,
        description=(
            "True when Sleeper-sourced live roster corrections (from "
            "``data/bronze/players/rosters_live/``) overrode at least one team or "
            "position in this response. Indicates the refresh_rosters.py daily "
            "cron is doing its job (phase 67 / v7.0)."
        ),
    )


# ---------------------------------------------------------------------------
# Defense metrics (phase 64-03)
# ---------------------------------------------------------------------------


class PositionalDefenseRank(BaseModel):
    """Defensive rank against a single offensive position.

    All four positions (QB/RB/WR/TE) are always returned for a team-week. If a
    position is missing from the week's silver data, ``avg_pts_allowed`` and
    ``rank`` are ``None`` and ``rating`` defaults to the league-median 72.
    """

    position: Literal["QB", "RB", "WR", "TE"]
    avg_pts_allowed: Optional[float] = None
    rank: Optional[int] = Field(default=None, ge=1, le=32)
    rating: int = Field(..., ge=50, le=99)


class TeamDefenseMetricsResponse(BaseModel):
    """Response envelope for GET /api/teams/{team}/defense-metrics.

    Every numeric field traces to a silver parquet column — no hardcoded
    placeholders. ``overall_def_rating`` is derived from ``def_sos_rank`` via
    ``round((1 - (rank - 1) / 31) * 49 + 50)`` (rank 1 → 99, rank 32 → 50).
    When ``def_sos_rank`` is NaN (e.g., week 1 before any prior aggregate) the
    rating defaults to the league-median 72 and the rank field is ``None``.
    """

    team: str
    season: int
    requested_week: int
    source_week: int
    fallback: bool = False
    fallback_season: Optional[int] = None
    overall_def_rating: int = Field(..., ge=50, le=99)
    def_sos_score: Optional[float] = None
    def_sos_rank: Optional[int] = Field(default=None, ge=1, le=32)
    adj_def_epa: Optional[float] = None
    positional: List[PositionalDefenseRank]
