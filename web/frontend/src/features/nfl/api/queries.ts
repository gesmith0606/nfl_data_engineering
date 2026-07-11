import { queryOptions } from '@tanstack/react-query';
import {
  fetchAdp,
  fetchAlerts,
  fetchCurrentWeek,
  fetchDraftBoard,
  fetchDraftRecommendations,
  fetchGameSeasons,
  fetchGames,
  fetchHealth,
  fetchLineup,
  fetchNewsFeed,
  fetchPlayer,
  fetchPlayerBadges,
  fetchPlayerCorrelations,
  fetchPlayerNews,
  fetchPlayerSentiment,
  fetchPredictions,
  fetchProjections,
  fetchSentimentRankings,
  fetchSentimentSummary,
  fetchTopStories,
  fetchTeamDefenseMetrics,
  fetchTeamEvents,
  fetchTeamMatchup,
  fetchTeamRoster,
  fetchTeamSentiment,
  searchPlayers,
  fetchMultiCompareRankings,
} from './service';
import type {
  ScoringFormat,
  RankingSortBy,
  RankingSource,
  SentimentWindow
} from './types';

export const nflKeys = {
  all: ['nfl'] as const,
  projections: (season: number, week: number, scoring: ScoringFormat, position?: string) =>
    [...nflKeys.all, 'projections', { season, week, scoring, position }] as const,
  predictions: (season: number, week: number) =>
    [...nflKeys.all, 'predictions', { season, week }] as const,
  playerSearch: (query: string) => [...nflKeys.all, 'player-search', query] as const,
  playerDetail: (id: string, season: number, week: number, scoring: ScoringFormat) =>
    [...nflKeys.all, 'player', { id, season, week, scoring }] as const,
  lineup: (season: number, week: number, team: string) =>
    [...nflKeys.all, 'lineup', { season, week, team }] as const,
  health: () => [...nflKeys.all, 'health'] as const,
  draftBoard: (sessionId?: string) => [...nflKeys.all, 'draft-board', sessionId] as const,
  draftRecommendations: (sessionId: string, position?: string) =>
    [...nflKeys.all, 'draft-recs', { sessionId, position }] as const,
  adp: () => [...nflKeys.all, 'adp'] as const,
  currentWeek: () => [...nflKeys.all, 'current-week'] as const,
  teamRoster: (team: string, season: number, week: number, side: string) =>
    [...nflKeys.all, 'team-roster', { team, season, week, side }] as const,
  teamMatchup: (team: string, season: number, week: number) =>
    [...nflKeys.all, 'team-matchup', { team, season, week }] as const,
  topStories: (window: SentimentWindow, limit: number) =>
    [...nflKeys.all, 'top-stories', { window, limit }] as const,
  sentimentRankings: (window: SentimentWindow, limit: number) =>
    [...nflKeys.all, 'sentiment-rankings', { window, limit }] as const,
  teamDefenseMetrics: (team: string, season: number, week: number) =>
    [...nflKeys.all, 'team-defense-metrics', { team, season, week }] as const,
  multiCompare: (
    season: number,
    scoring: ScoringFormat,
    position: string | null,
    sortBy: RankingSortBy,
    sources: RankingSource[],
    limit: number
  ) =>
    [
      ...nflKeys.all,
      'multi-compare',
      { season, scoring, position, sortBy, sources, limit },
    ] as const,
  games: (season: number, week: number) =>
    [...nflKeys.all, 'games', { season, week }] as const,
  gameSeasons: () => [...nflKeys.all, 'game-seasons'] as const
};

export const projectionsQueryOptions = (
  season: number,
  week: number,
  scoring: ScoringFormat,
  position?: string
) =>
  queryOptions({
    queryKey: nflKeys.projections(season, week, scoring, position),
    queryFn: () => fetchProjections(season, week, scoring, position)
  });

export const predictionsQueryOptions = (season: number, week: number) =>
  queryOptions({
    queryKey: nflKeys.predictions(season, week),
    queryFn: () => fetchPredictions(season, week),
    retry: (failureCount, error) => {
      // Don't retry 404s — no data for this season/week
      if (error && 'status' in error && (error as { status: number }).status === 404) return false;
      return failureCount < 2;
    }
  });

export const playerSearchQueryOptions = (query: string) =>
  queryOptions({
    queryKey: nflKeys.playerSearch(query),
    queryFn: () => searchPlayers(query),
    enabled: query.length >= 2
  });

export const playerDetailQueryOptions = (
  id: string,
  season: number,
  week: number,
  scoring: ScoringFormat
) =>
  queryOptions({
    queryKey: nflKeys.playerDetail(id, season, week, scoring),
    queryFn: () => fetchPlayer(id, season, week, scoring)
  });

export const playerCorrelationsQueryOptions = (playerId: string) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'player-correlations', playerId] as const,
    queryFn: () => fetchPlayerCorrelations(playerId),
    enabled: !!playerId,
    // Correlation edges are rebuilt at most a few times a season.
    staleTime: 24 * 60 * 60 * 1000
  });

export const lineupQueryOptions = (season: number, week: number, team: string) =>
  queryOptions({
    queryKey: nflKeys.lineup(season, week, team),
    queryFn: () => fetchLineup(season, week, team),
    enabled: !!team
  });

export const healthQueryOptions = () =>
  queryOptions({
    queryKey: nflKeys.health(),
    queryFn: () => fetchHealth()
  });

export const playerNewsQueryOptions = (
  playerId: string,
  season: number,
  week: number,
  limit = 10
) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'player-news', { playerId, season, week, limit }] as const,
    queryFn: () => fetchPlayerNews(playerId, season, week, limit),
    enabled: !!playerId
  });

export const alertsQueryOptions = (season: number, week: number) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'alerts', { season, week }] as const,
    queryFn: () => fetchAlerts(season, week)
  });

export const playerSentimentQueryOptions = (
  playerId: string,
  season: number,
  week: number
) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'player-sentiment', { playerId, season, week }] as const,
    queryFn: () => fetchPlayerSentiment(playerId, season, week),
    enabled: !!playerId,
    retry: false
  });

export const newsFeedQueryOptions = (
  season: number,
  week?: number,
  source?: string,
  team?: string,
  limit = 50,
  offset = 0
) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'news-feed', { season, week, source, team, limit, offset }] as const,
    queryFn: () => fetchNewsFeed(season, week, source, team, undefined, limit, offset),
    refetchInterval: 5 * 60 * 1000
  });

export const teamSentimentQueryOptions = (season: number, week: number) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'team-sentiment', { season, week }] as const,
    queryFn: () => fetchTeamSentiment(season, week),
    refetchInterval: 5 * 60 * 1000
  });

export const teamEventsQueryOptions = (season: number, week: number) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'team-events', { season, week }] as const,
    queryFn: () => fetchTeamEvents(season, week),
    refetchInterval: 5 * 60 * 1000
  });

export const playerBadgesQueryOptions = (
  playerId: string,
  season: number,
  week: number
) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'player-badges', { playerId, season, week }] as const,
    queryFn: () => fetchPlayerBadges(playerId, season, week),
    enabled: !!playerId,
    refetchInterval: 5 * 60 * 1000
  });

export const sentimentSummaryQueryOptions = (season: number, week: number) =>
  queryOptions({
    queryKey: [...nflKeys.all, 'sentiment-summary', { season, week }] as const,
    queryFn: () => fetchSentimentSummary(season, week),
    refetchInterval: 5 * 60 * 1000
  });

export const draftBoardQueryOptions = (
  scoring: ScoringFormat = 'half_ppr',
  rosterFormat: string = 'standard',
  nTeams: number = 12,
  season: number = 2026,
  sessionId?: string
) =>
  queryOptions({
    queryKey: nflKeys.draftBoard(sessionId),
    queryFn: () => fetchDraftBoard(scoring, rosterFormat, nTeams, season, sessionId),
    staleTime: Infinity
  });

export const draftRecommendationsQueryOptions = (
  sessionId: string,
  topN: number = 5,
  position?: string
) =>
  queryOptions({
    queryKey: nflKeys.draftRecommendations(sessionId, position),
    queryFn: () => fetchDraftRecommendations(sessionId, topN, position),
    enabled: !!sessionId
  });

export const adpQueryOptions = () =>
  queryOptions({
    queryKey: nflKeys.adp(),
    queryFn: () => fetchAdp(),
    staleTime: 60 * 60 * 1000
  });

// ---------------------------------------------------------------------------
// Teams / Roster / Defense-metrics (Phase 64)
// ---------------------------------------------------------------------------

/** Current NFL (season, week). Cached for 1 hour — mid-week shifts are rare. */
export const currentWeekQueryOptions = () =>
  queryOptions({
    queryKey: nflKeys.currentWeek(),
    queryFn: () => fetchCurrentWeek(),
    staleTime: 60 * 60 * 1000
  });

/**
 * Team roster for a season / week, optionally filtered to offense or defense.
 * Disabled until ``team`` is non-null so we don't hit the endpoint with "null".
 */
export const teamRosterQueryOptions = (
  team: string | null,
  season: number,
  week: number,
  side: 'offense' | 'defense' | 'all' = 'all'
) =>
  queryOptions({
    queryKey: nflKeys.teamRoster(team ?? '', season, week, side),
    queryFn: () => fetchTeamRoster(team as string, season, week, side),
    enabled: !!team
  });

/** Top stories in a trailing day/week/month window. Refetch every 5 min. */
export const topStoriesQueryOptions = (window: SentimentWindow, limit = 12) =>
  queryOptions({
    queryKey: nflKeys.topStories(window, limit),
    queryFn: () => fetchTopStories(window, limit),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000
  });

/** Live player sentiment rankings for a window. Refetch every 5 min. */
export const sentimentRankingsQueryOptions = (
  window: SentimentWindow,
  limit = 10
) =>
  queryOptions({
    queryKey: nflKeys.sentimentRankings(window, limit),
    queryFn: () => fetchSentimentRankings(window, limit),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000
  });

/**
 * A team's opponent for a season / week resolved from the schedule.
 * Disabled until ``team`` is non-null. Schedules are static — cache for 1 hour.
 */
export const teamMatchupQueryOptions = (
  team: string | null,
  season: number,
  week: number
) =>
  queryOptions({
    queryKey: nflKeys.teamMatchup(team ?? '', season, week),
    queryFn: () => fetchTeamMatchup(team as string, season, week),
    enabled: !!team,
    staleTime: 60 * 60 * 1000
  });

/**
 * Team defensive metrics for a season / week.
 * Disabled until ``team`` is non-null so MatchupView doesn't query the opponent
 * slot before a team is selected.
 */
export const teamDefenseMetricsQueryOptions = (
  team: string | null,
  season: number,
  week: number
) =>
  queryOptions({
    queryKey: nflKeys.teamDefenseMetrics(team ?? '', season, week),
    queryFn: () => fetchTeamDefenseMetrics(team as string, season, week),
    enabled: !!team
  });

/**
 * Side-by-side rankings (ours + Sleeper + ESPN + Yahoo) joined on player name.
 *
 * Yahoo column is served via FantasyPros consensus; missing-source values
 * are returned as `null` per row. Default sort is `consensus` (mean of
 * available external ranks); the user can resort by any single source.
 */
export const multiCompareQueryOptions = (opts: {
  season: number;
  scoring: ScoringFormat;
  position: string | null;
  sort_by: RankingSortBy;
  sources: RankingSource[];
  limit: number;
}) =>
  queryOptions({
    queryKey: nflKeys.multiCompare(
      opts.season,
      opts.scoring,
      opts.position,
      opts.sort_by,
      opts.sources,
      opts.limit
    ),
    queryFn: () =>
      fetchMultiCompareRankings({
        season: opts.season,
        scoring: opts.scoring,
        position: opts.position,
        sort_by: opts.sort_by,
        sources: opts.sources,
        limit: opts.limit,
      }),
    staleTime: 30 * 60 * 1000 // 30 minutes — external sources cache 24h server-side
  });

// ---------------------------------------------------------------------------
// Game archive
// ---------------------------------------------------------------------------

/**
 * Game results for a season / week. Stale after 1 hour — scores are final
 * once posted and rarely change, but we still want the cache to refresh
 * during live games on Sunday.
 */
export const gamesQueryOptions = (season: number, week: number) =>
  queryOptions({
    queryKey: nflKeys.games(season, week),
    queryFn: () => fetchGames(season, week),
    staleTime: 60 * 60 * 1000,
    retry: (failureCount, error) => {
      // 404 (no data for the slice) and 422 (out-of-range params) are
      // deterministic — retrying cannot help.
      if (error && 'status' in error) {
        const status = (error as { status: number }).status;
        if (status === 404 || status === 422) return false;
      }
      return failureCount < 2;
    }
  });

/**
 * Available seasons. Very stable — only changes once per NFL season.
 * Cache for 24 hours.
 */
export const gameSeasonsQueryOptions = () =>
  queryOptions({
    queryKey: nflKeys.gameSeasons(),
    queryFn: () => fetchGameSeasons(),
    staleTime: 24 * 60 * 60 * 1000
  });
