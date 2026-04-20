/** Fantasy projection for a single player-week. */
export interface PlayerProjection {
  player_id: string;
  player_name: string;
  team: string;
  position: string;
  projected_points: number;
  projected_floor: number;
  projected_ceiling: number;

  // Stat projections (null when not applicable for position)
  proj_pass_yards: number | null;
  proj_pass_tds: number | null;
  proj_rush_yards: number | null;
  proj_rush_tds: number | null;
  proj_rec: number | null;
  proj_rec_yards: number | null;
  proj_rec_tds: number | null;

  // Kicker stats
  proj_fg_makes: number | null;
  proj_xp_makes: number | null;

  scoring_format: string;
  season: number;
  week: number;

  // Metadata
  position_rank: number | null;
  injury_status: string | null;
}

/** Model prediction for a single game. */
export interface GamePrediction {
  game_id: string;
  season: number;
  week: number;
  home_team: string;
  away_team: string;
  predicted_spread: number;
  predicted_total: number;
  vegas_spread: number | null;
  vegas_total: number | null;
  spread_edge: number | null;
  total_edge: number | null;
  confidence_tier: string;
  ats_pick: string;
  ou_pick: string;
}

/** Envelope for a list of player projections. */
export interface ProjectionResponse {
  season: number;
  week: number;
  scoring_format: string;
  projections: PlayerProjection[];
  generated_at: string;
}

/** Envelope for a list of game predictions. */
export interface PredictionResponse {
  season: number;
  week: number;
  predictions: GamePrediction[];
  generated_at: string;
}

/** Lightweight result for player search. */
export interface PlayerSearchResult {
  player_id: string;
  player_name: string;
  team: string;
  position: string;
}

/** Health-check payload. */
export interface HealthResponse {
  status: string;
  version: string;
}

/** A player positioned on the field lineup view. */
export interface LineupPlayer {
  player_id: string;
  player_name: string;
  position: string;
  field_position: string; // "qb", "rb", "wr_left", "wr_right", "wr_slot", "te", "k"
  projected_points: number | null;
  projected_floor: number | null;
  projected_ceiling: number | null;
  snap_pct: number | null;
  depth_rank: number;
  is_starter: boolean;
}

/** Full team lineup for a given week. */
export interface TeamLineup {
  team: string;
  season: number;
  week: number;
  offense: LineupPlayer[];
  implied_total: number | null;
  team_projected_total: number | null;
}

/** A single news article or report associated with a player. */
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
  is_ruled_out: boolean;
  is_inactive: boolean;
  is_questionable: boolean;
  is_suspended: boolean;
  is_returning: boolean;
  body_snippet: string | null;
  /** Plan 61-05: human-readable event labels from the rule-extractor. */
  event_flags: string[];
  /** Plan 61-06: optional LLM-generated 1-sentence summary (feature-flagged). */
  summary: string | null;
}

/** Discrete overall sentiment bucket (D-03) — never a continuous score. */
export type OverallSentimentLabel = 'bullish' | 'bearish' | 'neutral';

/**
 * Per-team event density row (NEWS-03).
 *
 * Exactly 32 rows are returned by ``GET /api/news/team-events`` — missing
 * teams are zero-filled so the grid layout is stable.
 */
export interface TeamEvents {
  team: string;
  negative_event_count: number;
  positive_event_count: number;
  neutral_event_count: number;
  total_articles: number;
  sentiment_label: OverallSentimentLabel;
  top_events: string[];
}

/** Event badges for a single player (NEWS-04). */
export interface PlayerEventBadges {
  player_id: string;
  badges: string[];
  overall_label: OverallSentimentLabel;
  article_count: number;
  most_recent_article: NewsItem | null;
}

/** Active alert for a player with a significant status or sentiment event. */
export interface Alert {
  player_id: string;
  player_name: string;
  team: string | null;
  position: string | null;
  alert_type: 'ruled_out' | 'inactive' | 'questionable' | 'suspended' | 'major_negative' | 'major_positive';
  sentiment_multiplier: number | null;
  latest_signal_at: string | null;
  doc_count: number | null;
}

/** Aggregated weekly sentiment features for a single player. */
export interface PlayerSentiment {
  player_id: string;
  player_name: string;
  season: number;
  week: number;
  sentiment_multiplier: number;
  sentiment_score_avg: number | null;
  doc_count: number;
  is_ruled_out: boolean;
  is_inactive: boolean;
  is_questionable: boolean;
  is_suspended: boolean;
  is_returning: boolean;
  latest_signal_at: string | null;
  signal_staleness_hours: number | null;
}

/** Aggregated weekly sentiment summary for a single team. */
export interface TeamSentiment {
  team: string;
  season: number;
  week: number;
  sentiment_score: number;
  sentiment_label: 'positive' | 'neutral' | 'negative';
  signal_count: number;
  sentiment_multiplier: number;
}

/** Dashboard-level sentiment summary. */
export interface SentimentSummary {
  season: number;
  week: number;
  total_players: number;
  total_docs: number;
  sources: Record<string, number>;
  top_positive: SentimentPlayer[];
  top_negative: SentimentPlayer[];
  sentiment_distribution: {
    positive: number;
    neutral: number;
    negative: number;
  };
}

/** A player entry in the sentiment summary top lists. */
export interface SentimentPlayer {
  player_id: string;
  player_name: string;
  sentiment_multiplier: number;
  doc_count: number;
}

/** Scoring format options. */
export type ScoringFormat = "ppr" | "half_ppr" | "standard";

/** Position filter options. */
export type Position = "ALL" | "QB" | "RB" | "WR" | "TE" | "K";

/** Sort direction. */
export type SortDirection = "asc" | "desc";

/** Column sort configuration. */
export interface SortConfig {
  key: string;
  direction: SortDirection;
}

// ---------------------------------------------------------------------------
// Draft tool types
// ---------------------------------------------------------------------------

/** A player on the draft board. */
export interface DraftPlayer {
  player_id: string
  player_name: string
  position: string
  team: string | null
  projected_points: number
  model_rank: number
  adp_rank: number | null
  adp_diff: number | null
  value_tier: 'undervalued' | 'fair_value' | 'overvalued'
  vorp: number
}

/** Full draft board state from the API. */
export interface DraftBoardResponse {
  session_id: string
  players: DraftPlayer[]
  my_roster: DraftPlayer[]
  picks_taken: number
  my_pick_count: number
  remaining_needs: Record<string, number>
  scoring_format: string
  roster_format: string
  n_teams: number
}

/** Request body for recording a draft pick. */
export interface DraftPickRequest {
  session_id: string
  player_id: string
  by_me: boolean
}

/** Response after recording a draft pick. */
export interface DraftPickResponse {
  success: boolean
  player: DraftPlayer | null
  message: string
}

/** A single draft recommendation. */
export interface DraftRecommendation {
  player_id: string
  player_name: string
  position: string
  team: string | null
  projected_points: number
  model_rank: number
  vorp: number
  recommendation_score: number
}

/** Recommendations response. */
export interface DraftRecommendationsResponse {
  recommendations: DraftRecommendation[]
  reasoning: string
  remaining_needs: Record<string, number>
}

/** Request to start a mock draft. */
export interface MockDraftStartRequest {
  scoring: string
  roster_format: string
  n_teams: number
  user_pick: number
  season: number
}

/** Response after starting a mock draft. */
export interface MockDraftStartResponse {
  session_id: string
  message: string
}

/** Request to advance one pick in mock draft. */
export interface MockDraftPickRequest {
  session_id: string
}

/** Response after advancing a mock draft pick. */
export interface MockDraftPickResponse {
  pick_number: number
  round_number: number
  is_user_turn: boolean
  player_name: string | null
  position: string | null
  team: string | null
  is_complete: boolean
  draft_grade: string | null
  total_pts: number | null
  total_vorp: number | null
}

/** ADP entry for a player. */
export interface AdpPlayer {
  player_name: string
  position: string
  team: string | null
  adp_rank: number
}

/** ADP response envelope. */
export interface AdpResponse {
  players: AdpPlayer[]
  source: string
  updated_at: string | null
}

/** Draft configuration for starting a new draft. */
export interface DraftConfig {
  scoring: ScoringFormat
  roster_format: 'standard' | 'superflex' | '2qb'
  n_teams: number
  user_pick: number
  season: number
}

// ---------------------------------------------------------------------------
// Teams / Roster / Defense-metrics types (Phase 64)
// ---------------------------------------------------------------------------

/**
 * Current NFL (season, week) resolved from the local schedule parquet.
 *
 * ``source === 'schedule'`` means today's date falls inside a real gameday
 * window. ``source === 'fallback'`` means we're in the offseason (April/May)
 * or the requested season has no schedule rows — the endpoint returned the
 * max (season, week) in the data lake so the UI can still render.
 */
export interface CurrentWeekResponse {
  season: number;
  week: number;
  source: 'schedule' | 'fallback';
}

/**
 * One row of a team's roster with depth-chart, snap-count, and slot metadata.
 *
 * ``slot_hint`` is the display-layer assignment (QB1/RB1/WR1/LT/RT/DE1/CB1/…)
 * computed by the backend from snap_pct ordering. Entries outside the top-N
 * per depth-chart group carry ``slot_hint === null``.
 */
export interface RosterPlayer {
  player_id: string;
  player_name: string;
  team: string;
  position: string;
  depth_chart_position: string | null;
  jersey_number: number | null;
  status: string;
  snap_pct_offense: number | null;
  snap_pct_defense: number | null;
  injury_status: string | null;
  slot_hint: string | null;
}

/** Team roster response. The array field is named ``roster`` (not ``players``). */
export interface TeamRosterResponse {
  team: string;
  season: number;
  week: number;
  side: 'offense' | 'defense' | 'all';
  fallback: boolean;
  fallback_season: number | null;
  roster: RosterPlayer[];
}

/**
 * Defensive rank against a single offensive position (QB/RB/WR/TE).
 *
 * Semantic note: silver ``rank=1`` means **weakest defense** (most points
 * allowed to this position). The backend's ``rating`` follows the same
 * direction — high rating means offense will have an easy time. The frontend
 * inverts this for display so a "tough defender" reads as rating=99.
 */
export interface PositionalDefenseRank {
  position: 'QB' | 'RB' | 'WR' | 'TE';
  avg_pts_allowed: number | null;
  rank: number | null;
  rating: number;
}

/**
 * Team defensive metrics aggregated from silver layer.
 *
 * ``requested_week`` is the week the UI asked for; ``source_week`` is the
 * week whose silver row actually backed the response (can differ when the
 * service walks back to find data).
 */
export interface TeamDefenseMetricsResponse {
  team: string;
  season: number;
  requested_week: number;
  source_week: number;
  fallback: boolean;
  fallback_season: number | null;
  overall_def_rating: number;
  def_sos_score: number | null;
  def_sos_rank: number | null;
  adj_def_epa: number | null;
  positional: PositionalDefenseRank[];
}
