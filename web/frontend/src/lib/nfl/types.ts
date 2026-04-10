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
  is_ruled_out: boolean;
  is_inactive: boolean;
  is_questionable: boolean;
  is_suspended: boolean;
  is_returning: boolean;
  body_snippet: string | null;
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
