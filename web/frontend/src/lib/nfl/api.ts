import type {
  Alert,
  HealthResponse,
  NewsItem,
  PlayerProjection,
  PlayerSearchResult,
  PlayerSentiment,
  PredictionResponse,
  ProjectionResponse,
  ScoringFormat,
  TeamLineup,
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
  if (limit) params.set("limit", String(limit));

  return request<ProjectionResponse>(`/api/projections?${params}`);
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

/** Health check. */
export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

/** Fetch a single team's lineup for a given week. */
export async function fetchLineup(
  season: number,
  week: number,
  team: string,
): Promise<TeamLineup> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    team,
  });
  return request<TeamLineup>(`/api/lineups?${params}`);
}

/** Fetch all team lineups for a given week. */
export async function fetchAllLineups(
  season: number,
  week: number,
): Promise<TeamLineup[]> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
  });
  return request<TeamLineup[]>(`/api/lineups/all?${params}`);
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

export { ApiError };
