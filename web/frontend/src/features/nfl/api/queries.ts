import { queryOptions } from '@tanstack/react-query';
import {
  fetchAdp,
  fetchAlerts,
  fetchDraftBoard,
  fetchDraftRecommendations,
  fetchHealth,
  fetchLineup,
  fetchNewsFeed,
  fetchPlayer,
  fetchPlayerBadges,
  fetchPlayerNews,
  fetchPlayerSentiment,
  fetchPredictions,
  fetchProjections,
  fetchSentimentSummary,
  fetchTeamEvents,
  fetchTeamSentiment,
  searchPlayers,
} from './service';
import type { ScoringFormat } from './types';

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
  adp: () => [...nflKeys.all, 'adp'] as const
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
