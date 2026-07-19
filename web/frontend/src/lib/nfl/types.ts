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

/**
 * A correlated player pair inside a lineup (UC3).
 * `insight` is 'stack_bonus' (positive rho — ceilings hit together) or
 * 'shared_ceiling_warning' (negative rho — one's spike is the other's dud).
 * Mirrors `web/api/models/schemas.py::StackInsight`.
 */
export interface StackInsight {
  player_id_a: string;
  player_id_b: string;
  player_name_a: string;
  player_name_b: string;
  relation: string;
  rho: number;
  n_games: number;
  insight: 'stack_bonus' | 'shared_ceiling_warning';
}

/** One stability-gated correlation edge from a player's perspective (UC3). */
export interface PlayerCorrelation {
  other_player_id: string;
  other_player_name: string;
  relation: string;
  rho: number;
  n_games: number;
}

/** Envelope for `/api/players/{id}/correlations`. */
export interface PlayerCorrelationsResponse {
  player_id: string;
  correlations: PlayerCorrelation[];
  generated_at: string;
}

/** Full team lineup for a given week. */
export interface TeamLineup {
  team: string;
  season: number;
  week: number;
  offense: LineupPlayer[];
  defense: LineupPlayer[];
  implied_total: number | null;
  team_projected_total: number | null;
  /** Correlated pairs among the offense (optional — older API responses omit it). */
  stacks?: StackInsight[];
}

/**
 * Backend envelope returned by `/api/lineups`. Carries both nested
 * (`lineups`) and flat (`lineup`) representations so the website's lineup
 * widget and the AI advisor's `getTeamRoster` tool both have the shape they
 * expect. Mirrors `web/api/models/schemas.py::LineupResponse`.
 */
export interface LineupResponse {
  season: number;
  week: number;
  lineups: TeamLineup[];
  lineup: unknown[];
  generated_at: string;
  data_as_of: string | null;
  defaulted: boolean;
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
  /**
   * Phase 72 EVT-02: subject attribution surface. Defaults to "player".
   * Per CONTEXT Phase 72 Schema Note, the 7 new draft-season flags
   * (Drafted, Coaching Change, etc.) surface ONLY via event_flags — no
   * new top-level boolean fields are introduced.
   */
  subject_type?: 'player' | 'coach' | 'team' | 'reporter' | null;
  team_abbr?: string | null;
}

/** Discrete overall sentiment bucket (D-03) — never a continuous score. */
export type OverallSentimentLabel = 'bullish' | 'bearish' | 'neutral';

/** Trailing time window for the sentiment pulse views. */
export type SentimentWindow = 'day' | 'week' | 'month';

/** A NewsItem ranked for the trailing-window Top Stories list. */
export interface TopStory extends NewsItem {
  /** |sentiment| × confidence + event weight, recency-decayed. */
  story_score: number;
}

/** Response envelope for GET /api/news/top-stories. */
export interface TopStoriesResponse {
  window: SentimentWindow;
  as_of: string;
  story_count: number;
  stories: TopStory[];
}

/** One player's aggregated sentiment over a trailing window. */
export interface SentimentRankingEntry {
  player_id: string | null;
  player_name: string;
  team: string | null;
  doc_count: number;
  avg_sentiment: number;
  label: OverallSentimentLabel;
  latest_headline: string | null;
  latest_published_at: string | null;
  event_flags: string[];
}

/** Response envelope for GET /api/news/sentiment-rankings. */
export interface SentimentRankingsResponse {
  window: SentimentWindow;
  as_of: string;
  player_count: number;
  risers: SentimentRankingEntry[];
  fallers: SentimentRankingEntry[];
}

// ---------------------------------------------------------------------------
// League Sync types (/api/league/{league_id}/...)
// ---------------------------------------------------------------------------

/** A player on a user's Sleeper roster with league-re-scored projection data. */
export interface LeagueRosterPlayer {
  sleeper_player_id: string
  player_name: string | null
  position: string | null
  team: string | null
  projected_season_points: number | null
  vorp: number | null
}

/** A scoring delta badge (e.g. 'TE +1.0 rec premium'). */
export interface ScoringDeltaBadge {
  key: string
  label: string
  value: number
}

/** Response for GET /api/league/{league_id}/overview. */
export interface LeagueOverviewResponse {
  league_id: string
  league_name: string
  season: string
  status: string | null
  total_rosters: number | null
  roster_positions: string[]
  scoring_format_label: string
  scoring_deltas: ScoringDeltaBadge[]
  unmodeled_keys: string[]
  user_roster: LeagueRosterPlayer[]
  /** User's team name in this league (null when unset or no user_id given). */
  team_name?: string | null
}

/** A starter slot in the optimal lineup report. */
export interface StarterSlot {
  slot: string
  player_name: string | null
  position: string | null
  team: string | null
  projected_season_points: number | null
}

/** A drop candidate from the roster optimizer. */
export interface DropCandidate {
  player_name: string | null
  position: string | null
  value: number
  reason: string
}

/** Response for GET /api/league/{league_id}/roster-report. */
export interface RosterReportResponse {
  league_id: string
  user_id: string
  roster_size: number
  roster_format: string
  starters: StarterSlot[]
  bench: LeagueRosterPlayer[]
  drop_candidates: DropCandidate[]
  unmatched_player_ids: string[]
}

/** A single free-agent waiver target. */
export interface WaiverTarget {
  sleeper_player_id: string
  player_name: string | null
  position: string | null
  team: string | null
  projected_season_points: number | null
  vorp: number | null
  upgrades_over: string | null
  upgrade_slot: string | null
}

/** Response for GET /api/league/{league_id}/waivers. */
export interface WaiversResponse {
  league_id: string
  user_id: string
  roster_positions: string[]
  targets: WaiverTarget[]
}

// ---------------------------------------------------------------------------
// My Week types (/api/league/{league_id}/my-week)
// ---------------------------------------------------------------------------

/** A player scored for a single NFL week under league scoring. */
export interface MyWeekPlayer {
  sleeper_player_id: string
  player_name: string | null
  position: string | null
  team: string | null
  /** League-scored projected points for the requested week. */
  projected_points: number | null
  floor: number | null
  ceiling: number | null
  injury_status: string | null
  is_bye_week: boolean
  /** True for Out-tier designations (Out / IR / PUP / NFI). */
  is_out: boolean
}

/** A starting-lineup slot filled by the weekly optimal lineup. */
export interface MyWeekSlot extends MyWeekPlayer {
  slot: string
}

/** A free agent ranked by league-scored weekly projection. */
export interface MyWeekWaiverTarget extends MyWeekPlayer {
  upgrades_over: string | null
  upgrade_slot: string | null
}

/** Current-vs-optimal lineup delta for the week. */
export interface LineupChanges {
  to_start: MyWeekSlot[]
  to_bench: MyWeekPlayer[]
  current_points: number
  optimal_points: number
  /** optimal_points - current_points (0 when the set lineup is optimal). */
  net_gain: number
}

/** Response for GET /api/league/{league_id}/my-week. */
export interface MyWeekResponse {
  league_id: string
  user_id: string
  season: number
  week: number | null
  /** 'weekly' when weekly projections exist; 'preseason' otherwise. */
  mode: 'weekly' | 'preseason'
  message: string | null
  scoring_format_label: string
  roster_positions: string[]
  optimal_starters: MyWeekSlot[]
  bench: MyWeekPlayer[]
  changes: LineupChanges | null
  waiver_targets: MyWeekWaiverTarget[]
  unmatched_player_ids: string[]
}

// ---------------------------------------------------------------------------
// Draft-Prep types (/api/league/{league_id}/draft-prep)
// ---------------------------------------------------------------------------

/** Draft metadata for an upcoming or active Sleeper draft. */
export interface DraftInfo {
  draft_id: string
  status: string
  type: string
  rounds: number
  /** User's draft slot (1-based), or null if draft_order not set by commissioner yet. */
  user_slot: number | null
}

/** A player on the user's keeper roster, ranked for keeper-decision analysis. */
export interface KeeperCandidate {
  sleeper_player_id: string
  player_name: string | null
  position: string | null
  team: string | null
  projected_season_points: number | null
  /** True when years_exp <= taxi_years-1 per league settings. */
  taxi_eligible: boolean
}

/** An unrostered skill-position player ranked for draft targeting. */
export interface BestAvailablePlayer {
  sleeper_player_id: string
  player_name: string | null
  position: string | null
  team: string | null
  projected_season_points: number | null
  /** Consensus ADP rank from adp_latest.csv; null when player has no ADP entry. */
  adp_rank: number | null
  /** 1-based rank by projected_season_points among all unrostered players. */
  projection_rank: number
  /** adp_rank - projection_rank; positive = market undervalues vs our model. */
  value: number | null
  /** Years of NFL experience (0 = rookie). */
  years_exp: number | null
}

/** Response for GET /api/league/{league_id}/draft-prep. */
export interface LeagueDraftPrepResponse {
  league_id: string
  user_id: string
  draft_info: DraftInfo | null
  keeper_candidates: KeeperCandidate[]
  best_available: BestAvailablePlayer[]
  rookies: BestAvailablePlayer[]
  rookie_note: string
}

/** A connected Sleeper league persisted in localStorage. */
export interface ConnectedLeague {
  league_id: string
  league_name: string
  season: string
  user_id: string
  username: string
  roster_positions: string[]
  scoring_format_label: string
  connected_at: string
}

/** Phase 74 SLEEP-01..04: Sleeper user / league / roster types. */
export interface SleeperUser {
  user_id: string;
  username: string;
  display_name: string | null;
  avatar: string | null;
}

export interface SleeperLeague {
  league_id: string;
  name: string;
  season: string;
  total_rosters: number | null;
  sport: string | null;
  status: string | null;
  settings: Record<string, unknown> | null;
}

export interface SleeperUserLoginResponse {
  user: SleeperUser;
  leagues: SleeperLeague[];
}

export interface SleeperRosterPlayer {
  player_id: string;
  player_name: string | null;
  position: string | null;
  team: string | null;
  slot: string | null;
}

export interface SleeperRoster {
  roster_id: number;
  league_id: string;
  owner_user_id: string | null;
  is_user_roster: boolean;
  starters: SleeperRosterPlayer[];
  bench: SleeperRosterPlayer[];
}

/**
 * Phase 73 EXTP-03: Multi-source projection comparison row. Each external
 * source field is nullable — a missing source renders as an em-dash in the UI
 * (per CONTEXT D-06 fail-open).
 */
export interface ProjectionComparisonRow {
  player_id: string;
  player_name: string;
  position: string | null;
  team: string | null;
  ours: number | null;
  espn: number | null;
  sleeper: number | null;
  yahoo: number | null;
  delta_vs_ours: number | null;
}

export interface ProjectionComparison {
  season: number;
  week: number;
  scoring_format: string;
  rows: ProjectionComparisonRow[];
  source_labels: Record<string, string>;
  data_as_of: Record<string, string>;
}

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
  /**
   * Phase 72 EVT-02: non-player rollup counts populated by
   * team_weekly._load_non_player_counts. Reporters are NEVER counted here.
   */
  coach_news_count?: number;
  team_news_count?: number;
  staff_news_count?: number;
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

// ---------------------------------------------------------------------------
// Game archive types (/api/games, /api/games/seasons)
// ---------------------------------------------------------------------------

/** Final score record for a single NFL game. */
export interface GameResult {
  game_id: string;
  season: number;
  week: number;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  winner: string | null;
  point_spread_result: number | null;
  total_points: number | null;
  game_date: string | null;
  game_time: string | null;
}

/** Envelope for a list of game results. */
export interface GamesResponse {
  season: number;
  week: number;
  games: GameResult[];
  count: number;
}

/** Season metadata entry from /api/games/seasons. */
export interface GameSeasonEntry {
  season: number;
  game_count: number;
  has_player_stats: boolean;
}

/** Envelope for the seasons list. */
export interface GameSeasonsResponse {
  seasons: GameSeasonEntry[];
}

/** Scoring format options. */
export type ScoringFormat = "ppr" | "half_ppr" | "standard";

/** Position filter options. */
export type Position = "ALL" | "QB" | "RB" | "WR" | "TE" | "K" | "DST";

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
  /** Null for positions without a points model yet (e.g. DST). */
  projected_points: number | null
  model_rank: number
  adp_rank: number | null
  adp_diff: number | null
  value_tier: 'undervalued' | 'fair_value' | 'overvalued'
  /** Null for positions without a points model yet (e.g. DST). */
  vorp: number | null
  /** Draft-worthy tier grouping (1 = top tier); null when not yet computed. */
  tier?: number | null
  /** Standard deviation of ADP across sources/drafts; null when unavailable. */
  adp_stdev?: number | null
  /** Season-points floor (real quantile band or a documented proxy); null when unavailable. */
  floor?: number | null
  /** Season-points ceiling — see `floor` for provenance. */
  ceiling?: number | null
}

/** Draft strategy: re-ranks the pool by floor/ceiling band, or leaves the default (balanced) order. */
export type DraftStrategy = 'floor' | 'balanced' | 'ceiling'

/**
 * Aggregate floor/ceiling exposure of the user's drafted roster.
 * `volatility_index` is the mean of (ceiling - floor) / projected across
 * rostered players that carry bands — higher means boomier/riskier. Null
 * when no rostered player has bands.
 */
export interface RosterRisk {
  floor_sum: number
  ceiling_sum: number
  projected_sum: number
  volatility_index?: number | null
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
  /** ADP source used for the value-score merge (ffc|espn); null when using the adp_latest.csv fallback. */
  adp_source?: string | null
  /** Draft strategy applied at session creation (floor|balanced|ceiling); defaults to balanced. */
  strategy?: DraftStrategy | string
  /** Aggregate floor/ceiling exposure of the user's roster; null when empty or bandless. */
  roster_risk?: RosterRisk | null
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
  /** Probability (0-1) the player is gone before your next pick; null when not modeled. */
  gone_probability?: number | null
  /** This player's position's wait_cost (see PositionWait); null when it couldn't be computed. */
  wait_cost?: number | null
}

/**
 * Cost-of-waiting for one position: expected drop in best-available VORP
 * between the current pick and the user's next pick.
 */
export interface PositionWait {
  position: string
  best_now_vorp: number
  expected_best_next_vorp: number
  wait_cost: number
}

/** Recommendations response. */
export interface DraftRecommendationsResponse {
  recommendations: DraftRecommendation[]
  reasoning: string
  remaining_needs: Record<string, number>
  /** Per-position cost of waiting one pick; empty when the next pick number can't be determined. */
  position_wait?: PositionWait[]
}

/** A recommendation during a live draft, with roster-fit + stack context. */
export interface LiveDraftRecommendation extends DraftRecommendation {
  fills_need: boolean
  stack_note: string
  /** Consensus ADP rank, when the ADP join matched. */
  adp_rank: number | null
  /** adp_rank - model_rank; positive = falling to you / undervalued. */
  adp_diff: number | null
}

/** A noteworthy draft event (steal, reach, positional run, value drop). */
export interface LiveDraftKeyMoment {
  kind: string
  pick_no: number
  player: string
  detail: string
}

/** Live-synced draft state driven by our roster-aware recommendation engine. */
export interface LiveDraftResponse {
  draft_id: string
  status: string
  n_teams: number
  picks_made: number
  my_slot: number | null
  on_the_clock_slot: number | null
  is_my_turn: boolean
  picks_until_my_turn: number | null
  my_next_pick_no: number | null
  my_roster: DraftPlayer[]
  remaining_needs: Record<string, number>
  recommendations: LiveDraftRecommendation[]
  reasoning: string
  key_moments: LiveDraftKeyMoment[]
  unmatched_count: number
  platform: string
}

/** Platforms the live co-pilot supports (Sleeper/Yahoo auto-sync; ESPN paste/mirror). */
export type DraftPlatform = 'sleeper' | 'espn' | 'yahoo'

/** Connection params for live draft sync. */
export interface LiveDraftParams {
  draftId?: string
  username?: string
  leagueId?: string
  mySlot?: number
  season?: number
  scoring?: ScoringFormat
  topN?: number
  platform?: DraftPlatform
}

/** Request to apply a pasted draft-room pick log to a board session. */
export interface DraftSyncLogRequest {
  session_id: string
  text: string
  my_slot?: number
}

/** Result of a paste-sync application. */
export interface DraftSyncLogResponse {
  matched: number
  applied: number
  already_drafted: number
  my_picks_applied: number
  /** Sample of unmatched lines (truncated); unmatched_count is the true total. */
  unmatched_lines: string[]
  unmatched_count: number
  picks_taken: number
}

/** Request to start a mock draft. */
export interface MockDraftStartRequest {
  scoring: string
  roster_format: string
  n_teams: number
  user_pick: number
  season: number
  /** Platform room preset (espn|sleeper|yahoo); backend fills unset fields. */
  platform?: string
  /** ADP source for the value-score merge (ffc|espn); defaults from platform preset when unset. */
  adp_source?: string
  /** Draft strategy (floor|balanced|ceiling); defaults to balanced. */
  strategy?: DraftStrategy | string
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
  /** Draft-room style the config was pre-filled from ('espn'/'sleeper'/'yahoo'/'custom'). */
  platform?: string
  /** ADP source for the value-score merge (ffc|espn); mock draft only. */
  adp_source?: string
  /** Pick clock length in seconds for mock draft; null/undefined = clock off. */
  timer_seconds?: number | null
  /** Draft strategy dial (floor|balanced|ceiling); defaults to balanced. */
  strategy?: DraftStrategy | string
}

/** One platform's draft-room defaults from GET /api/draft/platforms. */
export interface DraftPlatformPreset {
  scoring_format: string
  roster_format: string
  rounds: number
  timer_seconds: number
  adp_source: string
  roster_slots: Record<string, number>
}

/** Response for GET /api/draft/platforms — one preset per supported room style. */
export type DraftPlatformsResponse = Record<string, DraftPlatformPreset>

// ---------------------------------------------------------------------------
// Post-draft report (GET /api/draft/mock/report)
// ---------------------------------------------------------------------------

/** The highest-VORP player still available at the moment of a user pick. */
export interface MockDraftReportAlternative {
  player_name: string
  vorp: number | null
}

/** One of the user's picks in a completed/in-progress mock draft, with receipts. */
export interface MockDraftReportPick {
  round: number
  overall_pick: number
  player_name: string
  position: string
  projected_points: number | null
  vorp: number | null
  adp_rank: number | null
  /** overall_pick - adp_rank. Positive = steal (fell past ADP); negative = reach. */
  adp_delta: number | null
  best_alternative: MockDraftReportAlternative | null
  /** This pick's vorp - best_alternative's vorp. */
  vorp_delta: number | null
}

/** Whole-draft summary for the user's roster. */
export interface MockDraftReportSummary {
  total_projected: number
  total_vorp: number
  floor_sum: number | null
  ceiling_sum: number | null
  letter_grade: string
  grade_notes: string[]
}

/** Response for GET /api/draft/mock/report. */
export interface MockDraftReportResponse {
  session_id: string
  picks: MockDraftReportPick[]
  summary: MockDraftReportSummary
}

// ---------------------------------------------------------------------------
// Undo (POST /api/draft/undo, POST /api/draft/mock/undo)
// ---------------------------------------------------------------------------

export interface DraftUndoResponse {
  success: boolean
  player: DraftPlayer | null
  message: string
}

export interface MockDraftUndoResponse {
  success: boolean
  /** Picks remaining on the board after undo. */
  pick_number: number
  message: string
}

// ---------------------------------------------------------------------------
// Stack hints (GET /api/draft/stack-hints) — concurrent backend lane, may 404
// ---------------------------------------------------------------------------

export type StackHintKind = 'stack_bonus' | 'shared_ceiling_warning'

export interface StackHint {
  player_name: string
  position: string
  team: string | null
  rostered_player_name: string
  rho: number
  n_games: number
  kind: StackHintKind
}

export interface StackHintsResponse {
  hints: StackHint[]
}

// ---------------------------------------------------------------------------
// Sleepers (GET /api/draft/sleepers) — concurrent backend lane, may 404
// ---------------------------------------------------------------------------

export interface SleeperEdge {
  player_name: string
  position: string
  team: string | null
  model_rank: number
  adp_rank: number | null
  adp_gap: number | null
  projected_points: number | null
  reason: string
}

/** Backend may return either a bare array or `{ sleepers: [] }` at integration. */
export type SleepersResponse = SleeperEdge[] | { sleepers: SleeperEdge[] }

// ---------------------------------------------------------------------------
// Draft Intel (GET /api/draft/intel) — concurrent backend lane, may 404
// ---------------------------------------------------------------------------

export interface DraftIntelManager {
  user_id: string
  display_name: string
  team_name: string | null
  tendencies: string
  summary: string[]
}

export interface DraftIntelResponse {
  league_id: string
  seasons_analyzed: number
  managers: DraftIntelManager[]
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
  /**
   * Per-player Madden-style rating (50-99) computed by the backend from PFR
   * seasonal defense stat percentiles. ``null`` for players without rated
   * production (rookies, offense, specialists) — display falls back to the
   * team positional anchor.
   */
  madden_rating: number | null;
  /** Human-readable stat basis for madden_rating (tooltip copy). */
  rating_detail: string | null;
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
 * A team's opponent for a given week, resolved from the Bronze schedule.
 *
 * Available as soon as the league publishes the schedule (May) — months
 * before model predictions exist — so the matchup UI can always find the
 * opponent. ``spread_line``/``total_line`` are the schedule's Vegas lines
 * (positive spread = home team favored, nflverse convention). ``is_bye``
 * with ``opponent === null`` means the team has no game that week.
 */
export interface TeamMatchupResponse {
  team: string;
  season: number;
  week: number;
  opponent: string | null;
  is_home: boolean | null;
  home_team: string | null;
  away_team: string | null;
  game_id: string | null;
  gameday: string | null;
  gametime: string | null;
  spread_line: number | null;
  total_line: number | null;
  is_bye: boolean;
  fallback: boolean;
  fallback_season: number | null;
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

// ---------------------------------------------------------------------------
// Multi-source rankings comparison (/api/rankings/multi-compare)
// ---------------------------------------------------------------------------

export type RankingSource = 'sleeper' | 'espn' | 'yahoo' | 'draftsharks' | 'ftn';
export type RankingSortBy = 'consensus' | 'ours' | RankingSource;
export type RankBasis = 'overall' | 'positional';

export interface MultiCompareRow {
  rank: number; // 1..N display order based on the active sort
  player_name: string;
  position: string;
  team: string;
  // Headline ranks — semantics depend on `rank_basis` in the response:
  //   "overall"    → 1..N flat across all positions (Bijan #1, Lamar #16, …)
  //   "positional" → 1..N within position (QB1/QB2, RB1/RB2, …)
  our_rank: number | null;
  sleeper_rank: number | null;
  espn_rank: number | null;
  yahoo_rank: number | null;
  draftsharks_rank: number | null;
  ftn_rank: number | null;
  // Both kinds are always exposed so the UI can resort/relabel client-side.
  our_pos_rank: number | null;
  our_overall_rank: number | null;
  sleeper_pos_rank: number | null;
  sleeper_overall_rank: number | null;
  espn_pos_rank: number | null;
  espn_overall_rank: number | null;
  yahoo_pos_rank: number | null;
  yahoo_overall_rank: number | null;
  draftsharks_pos_rank: number | null;
  draftsharks_overall_rank: number | null;
  ftn_pos_rank: number | null;
  ftn_overall_rank: number | null;
  our_projected_points: number | null;
  rank_diff_vs_sleeper: number | null;
  rank_diff_vs_espn: number | null;
  rank_diff_vs_yahoo: number | null;
  rank_diff_vs_draftsharks: number | null;
  rank_diff_vs_ftn: number | null;
}

export interface MultiCompareResponse {
  scoring_format: ScoringFormat;
  position_filter: string | null;
  season: number;
  sources: RankingSource[];
  sort_by: RankingSortBy;
  rank_basis: RankBasis;
  source_labels: Record<string, string>;
  our_projections_available: boolean;
  stale: Record<string, boolean>;
  cache_age_hours: Record<string, number | null>;
  last_updated: Record<string, string | null>;
  players: MultiCompareRow[];
  compared_at: string;
}
