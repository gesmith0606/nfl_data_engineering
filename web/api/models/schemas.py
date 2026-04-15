"""
Pydantic response models for the NFL Data Engineering API.

All models use ``Optional`` syntax compatible with Python 3.9.
"""

from typing import List, Optional

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


class ProjectionResponse(BaseModel):
    """Envelope for a list of player projections."""

    season: int
    week: int
    scoring_format: str
    projections: List[PlayerProjection]
    generated_at: str


class PredictionResponse(BaseModel):
    """Envelope for a list of game predictions."""

    season: int
    week: int
    predictions: List[GamePrediction]
    generated_at: str


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


class LineupResponse(BaseModel):
    """Envelope for lineup endpoint responses."""

    season: int
    week: int
    lineups: List[TeamLineup]
    generated_at: str


class HealthResponse(BaseModel):
    """Health-check payload."""

    status: str
    version: str
    db_status: Optional[str] = None


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
    sentiment_label: str = Field(
        "neutral", description="positive / neutral / negative"
    )
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


class DraftBoardResponse(BaseModel):
    """Full draft board state."""

    session_id: str
    players: List[DraftPlayer]
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
