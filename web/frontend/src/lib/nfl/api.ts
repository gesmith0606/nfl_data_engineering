import type {
  AdpResponse,
  Alert,
  CurrentWeekResponse,
  DraftBoardResponse,
  DraftPickRequest,
  DraftPickResponse,
  DraftPlatformsResponse,
  DraftRecommendationsResponse,
  DraftSyncLogRequest,
  DraftSyncLogResponse,
  GameSeasonsResponse,
  GamesResponse,
  HealthResponse,
  LineupResponse,
  LiveDraftParams,
  LiveDraftResponse,
  MockDraftPickRequest,
  MockDraftPickResponse,
  MockDraftStartRequest,
  MockDraftStartResponse,
  NewsItem,
  PlayerCorrelationsResponse,
  PlayerEventBadges,
  PlayerProjection,
  PlayerSearchResult,
  PlayerSentiment,
  PredictionResponse,
  ProjectionResponse,
  ScoringFormat,
  SentimentRankingsResponse,
  SentimentSummary,
  SentimentWindow,
  TeamDefenseMetricsResponse,
  TeamEvents,
  TeamLineup,
  TeamMatchupResponse,
  TeamRosterResponse,
  TopStoriesResponse,
  TeamSentiment,
} from "./types";

/**
 * Base URL for the FastAPI backend.
 * Uses the rewrite proxy in development (same origin) so we avoid CORS issues.
 */
const BASE_URL = typeof window !== "undefined" ? "" : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }
  const res = await fetch(url, {
    ...init,
    headers,
  });

  if (!res.ok) {
    throw new ApiError(
      `API request failed: ${res.status} ${res.statusText}`,
      res.status,
    );
  }

  return res.json() as Promise<T>;
}

/** Fetch player projections with optional filters. */
export async function fetchProjections(
  season: number,
  week: number,
  scoring: ScoringFormat,
  position?: string,
  team?: string,
  limit?: number,
): Promise<ProjectionResponse> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    scoring,
  });
  if (position && position !== "ALL") params.set("position", position);
  if (team) params.set("team", team);
  // Always request the full slate when neither team nor position is filtered.
  // The matchups page builds 32 team cards from one fetch — truncating to
  // the server-side default silently blanked out NYJ/CHI/MIN/etc. rosters.
  const effectiveLimit = limit ?? (position || team ? undefined : 1000);
  if (effectiveLimit) params.set("limit", String(effectiveLimit));

  return request<ProjectionResponse>(`/api/projections?${params}`);
}

/** Phase 74 SLEEP-01: Sleeper username login → user + leagues. */
export async function sleeperLogin(
  username: string,
  season?: number,
): Promise<import('./types').SleeperUserLoginResponse> {
  const params = new URLSearchParams();
  if (season != null) params.set('season', String(season));
  const qs = params.toString();
  const path = `/api/sleeper/user/login${qs ? `?${qs}` : ''}`;
  const url = `${BASE_URL}${path}`;
  const resp = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  });
  if (!resp.ok) {
    throw new Error(`Sleeper login failed: ${resp.status}`);
  }
  return (await resp.json()) as import('./types').SleeperUserLoginResponse;
}

/** Phase 74 SLEEP-02: List user leagues for a season. */
export async function fetchSleeperLeagues(
  userId: string,
  season?: number,
): Promise<import('./types').SleeperLeague[]> {
  const params = new URLSearchParams();
  if (season != null) params.set('season', String(season));
  return request<import('./types').SleeperLeague[]>(
    `/api/sleeper/leagues/${userId}${params.toString() ? `?${params}` : ''}`,
  );
}

/** Phase 74 SLEEP-03: Fetch league rosters; user_id marks the user's roster. */
export async function fetchSleeperRosters(
  leagueId: string,
  userId?: string,
): Promise<import('./types').SleeperRoster[]> {
  const params = new URLSearchParams();
  if (userId) params.set('user_id', userId);
  return request<import('./types').SleeperRoster[]>(
    `/api/sleeper/rosters/${leagueId}${params.toString() ? `?${params}` : ''}`,
  );
}

/** Phase 73 EXTP-03: Fetch multi-source projection comparison. */
export async function fetchProjectionsComparison(
  season: number,
  week: number,
  scoring: ScoringFormat = 'half_ppr' as ScoringFormat,
  position?: string,
  limit = 50,
): Promise<import('./types').ProjectionComparison> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    scoring,
    limit: String(limit),
  });
  if (position && position !== 'ALL') params.set('position', position);
  return request<import('./types').ProjectionComparison>(
    `/api/projections/comparison?${params}`,
  );
}

/** Fetch top projected players. */
export async function fetchTopProjections(
  season: number,
  week: number,
  scoring: ScoringFormat,
  limit = 20,
): Promise<ProjectionResponse> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    scoring,
    limit: String(limit),
  });
  return request<ProjectionResponse>(`/api/projections/top?${params}`);
}

/** Fetch game predictions. */
export async function fetchPredictions(
  season: number,
  week: number,
): Promise<PredictionResponse> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
  });
  return request<PredictionResponse>(`/api/predictions?${params}`);
}

/** Search players by name. */
export async function searchPlayers(
  query: string,
  season?: number,
  week?: number,
): Promise<PlayerSearchResult[]> {
  const params = new URLSearchParams({ q: query });
  if (season) params.set("season", String(season));
  if (week) params.set("week", String(week));
  return request<PlayerSearchResult[]>(`/api/players/search?${params}`);
}

/** Fetch a single player's projection detail. */
export async function fetchPlayer(
  playerId: string,
  season: number,
  week: number,
  scoring: ScoringFormat,
): Promise<PlayerProjection> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    scoring,
  });
  return request<PlayerProjection>(`/api/players/${playerId}?${params}`);
}

/**
 * Fetch a player's stability-gated correlation edges (UC3).
 * Returns an empty list (HTTP 200) when no correlation data exists.
 */
export async function fetchPlayerCorrelations(
  playerId: string,
  minRho = 0.1,
  limit = 10,
): Promise<PlayerCorrelationsResponse> {
  const params = new URLSearchParams({
    min_rho: String(minRho),
    limit: String(limit),
  });
  return request<PlayerCorrelationsResponse>(
    `/api/players/${playerId}/correlations?${params}`,
  );
}

/** Health check. */
export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

/**
 * Fetch a single team's lineup for a given week.
 *
 * The backend returns a `LineupResponse` envelope with the nested per-team
 * lineups in `lineups[]` (and a parallel flat representation in `lineup[]`
 * for the AI advisor). This unwraps to the single `TeamLineup` for the
 * requested team — `null` when the slice is empty (offseason / preseason).
 */
export async function fetchLineup(
  season: number,
  week: number,
  team: string,
): Promise<TeamLineup | null> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    team,
  });
  const envelope = await request<LineupResponse>(`/api/lineups?${params}`);
  return envelope.lineups[0] ?? null;
}

/** Fetch recent news items for a specific player. */
export async function fetchPlayerNews(
  playerId: string,
  season: number,
  week: number,
  limit = 10,
): Promise<NewsItem[]> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    limit: String(limit),
  });
  return request<NewsItem[]>(`/api/news/player/${encodeURIComponent(playerId)}?${params}`);
}

/** Fetch all active alerts for a season/week. */
export async function fetchAlerts(
  season: number,
  week: number,
): Promise<Alert[]> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
  });
  return request<Alert[]>(`/api/news/alerts?${params}`);
}

/** Fetch aggregated weekly sentiment for a player. */
export async function fetchPlayerSentiment(
  playerId: string,
  season: number,
  week: number,
): Promise<PlayerSentiment> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
  });
  return request<PlayerSentiment>(
    `/api/news/sentiment/${encodeURIComponent(playerId)}?${params}`,
  );
}

/** Fetch the full news feed with optional filters. */
export async function fetchNewsFeed(
  season: number,
  week?: number,
  source?: string,
  team?: string,
  playerId?: string,
  limit = 50,
  offset = 0,
): Promise<NewsItem[]> {
  const params = new URLSearchParams({ season: String(season) });
  if (week !== undefined) params.set('week', String(week));
  if (source) params.set('source', source);
  if (team) params.set('team', team);
  if (playerId) params.set('player_id', playerId);
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return request<NewsItem[]>(`/api/news/feed?${params}`);
}

/** Fetch top stories in a trailing day/week/month window. */
export async function fetchTopStories(
  window: SentimentWindow = 'week',
  limit = 12,
): Promise<TopStoriesResponse> {
  const params = new URLSearchParams({ window, limit: String(limit) });
  return request<TopStoriesResponse>(`/api/news/top-stories?${params}`);
}

/** Fetch live player sentiment rankings (risers/fallers) for a window. */
export async function fetchSentimentRankings(
  window: SentimentWindow = 'week',
  limit = 10,
): Promise<SentimentRankingsResponse> {
  const params = new URLSearchParams({ window, limit: String(limit) });
  return request<SentimentRankingsResponse>(
    `/api/news/sentiment-rankings?${params}`,
  );
}

/** Fetch sentiment summary for dashboard display. */
export async function fetchSentimentSummary(
  season: number,
  week: number,
): Promise<SentimentSummary> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
  });
  return request<SentimentSummary>(`/api/news/summary?${params}`);
}

/** Fetch aggregated team sentiment for a season/week. */
export async function fetchTeamSentiment(
  season: number,
  week: number,
): Promise<TeamSentiment[]> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
  });
  return request<TeamSentiment[]>(`/api/news/team-sentiment?${params}`);
}

/**
 * Fetch per-team event density (NEWS-03).
 *
 * Returns exactly 32 rows — one per NFL team — with counts derived from the
 * rule-extracted event flags. Zero-filled teams carry ``sentiment_label ===
 * 'neutral'`` so the grid always renders a stable 32-tile layout.
 */
export async function fetchTeamEvents(
  season: number,
  week: number,
): Promise<TeamEvents[]> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
  });
  return request<TeamEvents[]>(`/api/news/team-events?${params}`);
}

/**
 * Fetch deduplicated event badges for a single player (NEWS-04).
 *
 * Badges are sorted by occurrence count descending. ``overall_label`` is a
 * discrete bucket per D-03 — never a numerical sentiment score. Returns
 * zero-filled payload (empty ``badges``) when no data exists for the player.
 */
export async function fetchPlayerBadges(
  playerId: string,
  season: number,
  week: number,
): Promise<PlayerEventBadges> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
  });
  return request<PlayerEventBadges>(
    `/api/news/player-badges/${encodeURIComponent(playerId)}?${params}`,
  );
}

// ---------------------------------------------------------------------------
// Game archive
// ---------------------------------------------------------------------------

/** Fetch final game scores for a season / week. */
export async function fetchGames(season: number, week: number): Promise<GamesResponse> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week)
  });
  return request<GamesResponse>(`/api/games?${params}`);
}

/** Fetch the list of seasons with game data. */
export async function fetchGameSeasons(): Promise<GameSeasonsResponse> {
  return request<GameSeasonsResponse>('/api/games/seasons');
}

export { ApiError };

// ---------------------------------------------------------------------------
// Draft tool API functions
// ---------------------------------------------------------------------------

/** Fetch or create a draft board session. */
export async function fetchDraftBoard(
  scoring: ScoringFormat = 'half_ppr',
  rosterFormat: string = 'standard',
  nTeams: number = 12,
  season: number = 2026,
  sessionId?: string,
  adpSource?: string
): Promise<DraftBoardResponse> {
  const params = new URLSearchParams({
    scoring,
    roster_format: rosterFormat,
    n_teams: String(nTeams),
    season: String(season)
  })
  if (sessionId) params.set('session_id', sessionId)
  if (adpSource) params.set('adp_source', adpSource)
  return request<DraftBoardResponse>(`/api/draft/board?${params}`)
}

/** Record a draft pick. */
export async function draftPick(body: DraftPickRequest): Promise<DraftPickResponse> {
  return request<DraftPickResponse>('/api/draft/pick', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

/** Get draft recommendations for the current board state. */
export async function fetchDraftRecommendations(
  sessionId: string,
  topN: number = 5,
  position?: string
): Promise<DraftRecommendationsResponse> {
  const params = new URLSearchParams({ session_id: sessionId, top_n: String(topN) })
  if (position && position !== 'ALL') params.set('position', position)
  return request<DraftRecommendationsResponse>(`/api/draft/recommendations?${params}`)
}

/**
 * Sync a live draft (Sleeper public API, or Yahoo via server-side OAuth).
 * Picks are read straight from the platform and the recommendation comes from
 * our roster-aware engine (VORP + positional need + stacks) — not the
 * platform's autopick order. Poll this on an interval. Yahoo returns 503 when
 * the server has no OAuth grant — callers fall back to mirror mode.
 */
export async function fetchLiveDraft(
  params: LiveDraftParams
): Promise<LiveDraftResponse> {
  const q = new URLSearchParams()
  if (params.draftId) q.set('draft_id', params.draftId)
  if (params.username) q.set('username', params.username)
  if (params.leagueId) q.set('league_id', params.leagueId)
  if (params.mySlot != null) q.set('my_slot', String(params.mySlot))
  if (params.season != null) q.set('season', String(params.season))
  if (params.scoring) q.set('scoring', params.scoring)
  if (params.topN != null) q.set('top_n', String(params.topN))
  if (params.platform) q.set('platform', params.platform)
  return request<LiveDraftResponse>(`/api/draft/live?${q}`)
}

/**
 * Paste-sync: apply a pasted draft-room pick log to the board session.
 * ESPN's better-than-mirror-mode path — one paste catches the board up.
 */
export async function syncPickLog(
  body: DraftSyncLogRequest
): Promise<DraftSyncLogResponse> {
  return request<DraftSyncLogResponse>('/api/draft/sync-log', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

/** Detect the Yahoo-not-connected case so the UI can offer mirror mode. */
export function isServiceUnavailable(err: unknown): boolean {
  return err instanceof ApiError && err.status === 503
}

/** Start a mock draft simulation session. */
export async function startMockDraft(body: MockDraftStartRequest): Promise<MockDraftStartResponse> {
  return request<MockDraftStartResponse>('/api/draft/mock/start', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

/** Advance one pick in a mock draft simulation. */
export async function advanceMockDraft(body: MockDraftPickRequest): Promise<MockDraftPickResponse> {
  return request<MockDraftPickResponse>('/api/draft/mock/pick', {
    method: 'POST',
    body: JSON.stringify(body)
  })
}

/** Fetch latest ADP data. */
export async function fetchAdp(): Promise<AdpResponse> {
  return request<AdpResponse>('/api/draft/adp')
}

/**
 * Fetch per-platform draft-room presets (scoring/roster format/rounds/timer/
 * ADP source). Callers should fall back to hardcoded defaults on failure —
 * this endpoint is a parallel backend lane and may 404 until it ships.
 */
export async function fetchDraftPlatforms(): Promise<DraftPlatformsResponse> {
  return request<DraftPlatformsResponse>('/api/draft/platforms')
}

// ---------------------------------------------------------------------------
// Teams / Roster / Defense-metrics (Phase 64)
// ---------------------------------------------------------------------------

/**
 * Resolve the current NFL (season, week) from today's date against the local
 * schedule parquet. Returns ``source: 'fallback'`` during the offseason.
 */
export async function fetchCurrentWeek(): Promise<CurrentWeekResponse> {
  return request<CurrentWeekResponse>('/api/teams/current-week');
}

/**
 * Fetch a team's roster for a given season / week, optionally restricted to
 * offense or defense. Response carries ``fallback`` flags when the backend
 * had to walk back to a prior season (e.g. 2026 → 2025).
 */
export async function fetchTeamRoster(
  team: string,
  season: number,
  week: number,
  side: 'offense' | 'defense' | 'all' = 'all'
): Promise<TeamRosterResponse> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    side
  });
  return request<TeamRosterResponse>(
    `/api/teams/${encodeURIComponent(team)}/roster?${params}`
  );
}

/**
 * Resolve a team's opponent for a week from the Bronze schedule. Works before
 * model predictions exist; carries the schedule's Vegas lines. ``is_bye=true``
 * when the team has no game that week.
 */
export async function fetchTeamMatchup(
  team: string,
  season: number,
  week: number
): Promise<TeamMatchupResponse> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week)
  });
  return request<TeamMatchupResponse>(
    `/api/teams/${encodeURIComponent(team)}/matchup?${params}`
  );
}

/**
 * Fetch per-position defensive metrics for a team-week.
 *
 * Response ``positional[]`` always contains 4 entries (QB/RB/WR/TE) with
 * ``rank`` (1-32) and ``rating`` (50-99). Semantic: silver rank=1 = most
 * points allowed (weakest defense) — the frontend inverts for display.
 */
export async function fetchTeamDefenseMetrics(
  team: string,
  season: number,
  week: number
): Promise<TeamDefenseMetricsResponse> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week)
  });
  return request<TeamDefenseMetricsResponse>(
    `/api/teams/${encodeURIComponent(team)}/defense-metrics?${params}`
  );
}


// ---------------------------------------------------------------------------
// Multi-source rankings comparison
// ---------------------------------------------------------------------------

import type {
  MultiCompareResponse,
  RankingSource,
  RankingSortBy,
  LeagueOverviewResponse,
  LeagueDraftPrepResponse,
  MyWeekResponse,
  RosterReportResponse,
  WaiversResponse,
} from './types';

// ---------------------------------------------------------------------------
// League Sync API functions (/api/league/{league_id}/...)
// ---------------------------------------------------------------------------

/**
 * Fetch league overview: settings, scoring summary, and (when user_id is
 * supplied) the user's roster re-scored under the league's custom settings.
 */
export async function fetchLeagueOverview(
  leagueId: string,
  userId?: string,
  season?: number,
): Promise<LeagueOverviewResponse> {
  const params = new URLSearchParams()
  if (userId) params.set('user_id', userId)
  if (season) params.set('season', String(season))
  const qs = params.toString()
  return request<LeagueOverviewResponse>(
    `/api/league/${leagueId}/overview${qs ? `?${qs}` : ''}`,
  )
}

/**
 * Fetch the optimal starting lineup, bench, and drop candidates for the
 * user's roster in a league, re-scored under the league's exact settings.
 *
 * Mirrors the output of `scripts/draft_live.py --roster-report`.
 */
export async function fetchLeagueRosterReport(
  leagueId: string,
  userId: string,
  season?: number,
): Promise<RosterReportResponse> {
  const params = new URLSearchParams({ user_id: userId })
  if (season) params.set('season', String(season))
  return request<RosterReportResponse>(
    `/api/league/${leagueId}/roster-report?${params}`,
  )
}

/**
 * Fetch top-20 free-agent waiver targets for a league, ranked by league-
 * scored projection, annotated with which starter they'd upgrade over.
 */
export async function fetchLeagueWaivers(
  leagueId: string,
  userId: string,
  season?: number,
): Promise<WaiversResponse> {
  const params = new URLSearchParams({ user_id: userId })
  if (season) params.set('season', String(season))
  return request<WaiversResponse>(
    `/api/league/${leagueId}/waivers?${params}`,
  )
}

/**
 * Fetch the weekly "My Week" command center for the user's roster in a
 * league: optimal weekly lineup under league scoring, start/sit deltas vs
 * the currently-set lineup, and weekly-scored waiver targets.
 *
 * Returns mode='preseason' with a message when no weekly projection data
 * exists for the resolved (season, week) — the UI should surface the
 * message and point at the season-long Roster Report instead.
 */
export async function fetchLeagueMyWeek(
  leagueId: string,
  userId: string,
  season?: number,
  week?: number,
): Promise<MyWeekResponse> {
  const params = new URLSearchParams({ user_id: userId })
  if (season) params.set('season', String(season))
  if (week) params.set('week', String(week))
  return request<MyWeekResponse>(
    `/api/league/${leagueId}/my-week?${params}`,
  )
}

/**
 * Fetch the pre-draft analysis for a league: keeper candidates, draft info,
 * best-available targets with ADP annotation, and a rookie-specific view.
 *
 * Designed for the pre-season view when a connected league has no roster yet
 * (status='pre_draft' or empty players list). Returns gracefully when the
 * user has no roster — keeper_candidates will simply be empty.
 */
export async function fetchLeagueDraftPrep(
  leagueId: string,
  userId?: string,
  season?: number,
): Promise<LeagueDraftPrepResponse> {
  const params = new URLSearchParams()
  if (userId) params.set('user_id', userId)
  if (season) params.set('season', String(season))
  const qs = params.toString()
  return request<LeagueDraftPrepResponse>(
    `/api/league/${leagueId}/draft-prep${qs ? `?${qs}` : ''}`,
  )
}

/**
 * Fetch our projections + external rankings (Sleeper/ESPN/Yahoo) joined on
 * player name into a single side-by-side table.
 *
 * `yahoo` is served via FantasyPros consensus (provenance preserved in
 * `source_labels`). Empty source columns are returned as null per row.
 */
export async function fetchMultiCompareRankings(opts: {
  scoring?: ScoringFormat;
  position?: string | null;
  limit?: number;
  season?: number;
  sources?: RankingSource[];
  sort_by?: RankingSortBy;
}): Promise<MultiCompareResponse> {
  const params = new URLSearchParams();
  if (opts.scoring) params.set('scoring', opts.scoring);
  if (opts.position && opts.position !== 'ALL') params.set('position', opts.position);
  if (opts.limit) params.set('limit', String(opts.limit));
  if (opts.season) params.set('season', String(opts.season));
  if (opts.sources?.length) params.set('sources', opts.sources.join(','));
  if (opts.sort_by) params.set('sort_by', opts.sort_by);
  return request<MultiCompareResponse>(
    `/api/rankings/multi-compare?${params}`
  );
}
