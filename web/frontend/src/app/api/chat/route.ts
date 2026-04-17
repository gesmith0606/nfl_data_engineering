import { convertToModelMessages, streamText, stepCountIs, tool, UIMessage } from 'ai';
import { google } from '@ai-sdk/google';
import { createGroq } from '@ai-sdk/groq';
import { z } from 'zod';

export const maxDuration = 30;

const FASTAPI_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const SYSTEM_PROMPT = `You are a fantasy football advisor for the NFL Analytics platform.
You help users with start/sit decisions, trade analysis, waiver wire pickups,
and general fantasy football questions.

RULES:
- Always use your tools to look up real data before giving advice. Never guess stats.
- When comparing players, fetch projections for BOTH and compare floor, ceiling, and projected points.
- Always mention the scoring format since advice differs between PPR/Half-PPR/Standard.
- If a player is injured (Out, IR, Doubtful), clearly warn the user with ⚠️.
- Present numbers clearly: "12.4 pts (floor: 6.2, ceiling: 22.1)".
- Be concise but thorough. Lead with the recommendation, then explain why.
- If you don't have data, say so honestly.
- Format responses with **bold player names**, bullet points for key factors, and clear headers.

AVAILABLE CAPABILITIES:
- Look up any player's projection, floor, ceiling, and injury status.
- Compare two players head-to-head for start/sit decisions.
- Search for players by name fragment.
- Get position rankings (top N QBs, RBs, WRs, TEs, Ks).
- Get game predictions with spreads, totals, and confidence tiers.
- Get a team's full roster/lineup with projections.
- Get team sentiment and outlook.
- Get player-specific news and injury updates.
- Get draft board with ADP, VORP, and value tiers.
- Get overall sentiment summary with bullish/bearish players.

POSITION-SPECIFIC GUIDANCE:
- QB: Prioritize passing volume, rushing upside, and favorable matchup vs weak pass defenses.
  Look for QBs with 2+ TD upside and floor above 18 pts in Half-PPR.
- RB: Prioritize workload (carries + targets), game script (team favored = more rushing), and snap share.
  In negative game scripts RBs lose value; in positive scripts (team leading) they get clock-killing carries.
  RBs in run-heavy offenses with spread < -7 get a usage multiplier boost.
- WR: Prioritize target share, air yards, and matchup vs CB depth. Look at floor/ceiling spread —
  high-ceiling WRs are good in GPPs; high-floor WRs are safer for cash. PPR/Half-PPR scoring
  significantly boosts slot receivers.
- TE: TE is a two-tier position. Elite TEs (top 5) are set-and-forget; others are matchup dependent.
  Look for TEs against weak safety coverage and those with 5+ target share on their team.
- K: Avoid recommending kickers unless the user specifically asks. When asked, prefer kickers
  on high-scoring offenses with dome games or favorable weather.

TRADE ANALYSIS:
- When analyzing trades, fetch projections for ALL players involved.
- Compare VORP (value over replacement): QB replacement = rank 13, RB = rank 25, WR = rank 30, TE = rank 13.
- Consider remaining schedule strength and bye weeks.
- Consider roster context: what positions does the user need most?
- A trade that looks even in projected points may favor one side if it fills a positional need.

WAIVER WIRE:
- Recommend players projected above 10 pts who are likely available (not top-5 at their position).
- Check injury news first — waiver pickups are often injury replacements.
- Prioritize handcuffs (backup RBs behind injured starters) and slot receivers getting increased targets.
- Factor in upcoming schedule: avoid players with tough matchups in the next 2 weeks.

Current season: 2026
Default scoring: Half-PPR (unless user specifies otherwise)
Current week: Check projections data for the latest week available.`;

/**
 * Returns the primary Gemini model, falling back to Groq Llama if Google
 * credentials are unavailable.
 */
function getModel() {
  if (process.env.GOOGLE_GENERATIVE_AI_API_KEY) {
    return google('gemini-2.5-flash');
  }

  if (process.env.GROQ_API_KEY) {
    console.warn('GOOGLE_GENERATIVE_AI_API_KEY not set — falling back to Groq');
    const groq = createGroq({ apiKey: process.env.GROQ_API_KEY });
    return groq('llama-3.1-8b-instant');
  }

  throw new Error(
    'No AI provider credentials found. Set GOOGLE_GENERATIVE_AI_API_KEY or GROQ_API_KEY.'
  );
}

type FetchResult<T> =
  | { ok: true; data: T }
  | { ok: false; reason: 'backend_down' | 'not_found' | 'error'; message: string };

/** Fetch a JSON resource from the FastAPI backend (server-side only). */
async function fastapiGet<T>(path: string): Promise<FetchResult<T>> {
  const url = `${FASTAPI_URL}${path}`;
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      // Next.js: opt out of caching for live data
      cache: 'no-store'
    });
    if (res.status === 404) {
      return { ok: false, reason: 'not_found', message: `No data found at ${path}` };
    }
    if (!res.ok) {
      return {
        ok: false,
        reason: 'error',
        message: `Backend returned HTTP ${res.status} for ${path}`
      };
    }
    const data = await res.json() as T;
    return { ok: true, data };
  } catch (err) {
    // Connection refused / DNS failure — backend is down
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[advisor] FastAPI unreachable at ${url}: ${msg}`);
    return {
      ok: false,
      reason: 'backend_down',
      message:
        'The data backend is currently unavailable. Please try again in a moment.'
    };
  }
}

export async function POST(req: Request) {
  const { messages }: { messages: UIMessage[] } = await req.json();

  const model = getModel();

  const result = streamText({
    model,
    system: SYSTEM_PROMPT,
    messages: await convertToModelMessages(messages),
    stopWhen: stepCountIs(5),
    tools: {
      getPlayerProjection: tool({
        description:
          'Look up the weekly fantasy projection for a specific player. Returns projected points, floor, ceiling, and injury status.',
        inputSchema: z.object({
          playerName: z
            .string()
            .describe('The player full name, e.g. "Patrick Mahomes"'),
          season: z.number().default(2026).describe('NFL season year'),
          week: z
            .number()
            .min(1)
            .max(18)
            .describe('NFL week number (1–18)'),
          scoring: z
            .enum(['ppr', 'half_ppr', 'standard'])
            .default('half_ppr')
            .describe('Fantasy scoring format')
        }),
        execute: async ({ playerName, season, week, scoring }) => {
          const params = new URLSearchParams({
            season: String(season),
            week: String(week),
            scoring
          });
          type ProjectionPayload = { projections: Array<{
            player_name: string;
            player_id: string;
            team: string;
            position: string;
            projected_points: number;
            projected_floor: number;
            projected_ceiling: number;
            injury_status: string | null;
          }> };
          const result = await fastapiGet<ProjectionPayload>(`/api/projections?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.projections?.length) {
            return { found: false, message: `No projection data for week ${week} of ${season}.` };
          }

          const name = playerName.toLowerCase();
          const match = result.data.projections.find((p) =>
            p.player_name.toLowerCase().includes(name)
          );

          if (!match) {
            return {
              found: false,
              message: `Player "${playerName}" not found in week ${week} projections.`
            };
          }

          return {
            found: true,
            player_name: match.player_name,
            team: match.team,
            position: match.position,
            projected_points: match.projected_points,
            projected_floor: match.projected_floor,
            projected_ceiling: match.projected_ceiling,
            injury_status: match.injury_status ?? 'Active',
            scoring_format: scoring,
            season,
            week
          };
        }
      }),

      compareStartSit: tool({
        description:
          'Compare two players head-to-head for a start/sit decision. Returns side-by-side projections for both players.',
        inputSchema: z.object({
          player1: z.string().describe('First player full name'),
          player2: z.string().describe('Second player full name'),
          season: z.number().default(2026),
          week: z.number().min(1).max(18),
          scoring: z
            .enum(['ppr', 'half_ppr', 'standard'])
            .default('half_ppr')
        }),
        execute: async ({ player1, player2, season, week, scoring }) => {
          const params = new URLSearchParams({
            season: String(season),
            week: String(week),
            scoring
          });
          type ComparePayload = { projections: Array<{
            player_name: string;
            team: string;
            position: string;
            projected_points: number;
            projected_floor: number;
            projected_ceiling: number;
            injury_status: string | null;
          }> };
          const result = await fastapiGet<ComparePayload>(`/api/projections?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.projections?.length) {
            return { found: false, message: `No projection data for week ${week} of ${season}.` };
          }

          const findPlayer = (name: string) => {
            const lower = name.toLowerCase();
            return result.data.projections.find((p) =>
              p.player_name.toLowerCase().includes(lower)
            ) ?? null;
          };

          const p1 = findPlayer(player1);
          const p2 = findPlayer(player2);

          return {
            found: true,
            scoring_format: scoring,
            season,
            week,
            player1: p1
              ? {
                  name: p1.player_name,
                  team: p1.team,
                  position: p1.position,
                  projected_points: p1.projected_points,
                  floor: p1.projected_floor,
                  ceiling: p1.projected_ceiling,
                  injury_status: p1.injury_status ?? 'Active'
                }
              : { name: player1, error: 'Not found in projections' },
            player2: p2
              ? {
                  name: p2.player_name,
                  team: p2.team,
                  position: p2.position,
                  projected_points: p2.projected_points,
                  floor: p2.projected_floor,
                  ceiling: p2.projected_ceiling,
                  injury_status: p2.injury_status ?? 'Active'
                }
              : { name: player2, error: 'Not found in projections' }
          };
        }
      }),

      searchPlayers: tool({
        description:
          'Search for NFL players by name fragment. Useful when unsure of exact spelling or to discover player IDs.',
        inputSchema: z.object({
          query: z.string().describe('Name fragment to search, e.g. "mahom"'),
          season: z.number().optional().describe('Optional season filter'),
          week: z.number().optional().describe('Optional week filter')
        }),
        execute: async ({ query, season, week }) => {
          const params = new URLSearchParams({ q: query });
          if (season) params.set('season', String(season));
          if (week) params.set('week', String(week));
          type SearchPayload = Array<{
            player_id: string;
            player_name: string;
            team: string;
            position: string;
          }>;
          const result = await fastapiGet<SearchPayload>(`/api/players/search?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.length) {
            return { found: false, message: `No players matched "${query}".` };
          }
          return { found: true, players: result.data.slice(0, 10) };
        }
      }),

      getNewsFeed: tool({
        description:
          'Fetch the latest NFL news, injury updates, and player reports.',
        inputSchema: z.object({
          season: z.number().default(2025).describe('Season to pull news from'),
          week: z
            .number()
            .optional()
            .describe('Optional week filter; omit for all weeks'),
          limit: z
            .number()
            .default(10)
            .describe('Maximum number of news items to return')
        }),
        execute: async ({ season, week, limit }) => {
          const params = new URLSearchParams({
            season: String(season),
            limit: String(limit)
          });
          if (week !== undefined) params.set('week', String(week));

          type NewsPayload = Array<{
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
            body_snippet: string | null;
            is_ruled_out: boolean;
            is_inactive: boolean;
            is_questionable: boolean;
            is_suspended: boolean;
            is_returning: boolean;
          }>;
          const result = await fastapiGet<NewsPayload>(`/api/news/feed?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.length) {
            return { found: false, message: 'No news items available.' };
          }
          return { found: true, items: result.data };
        }
      }),

      getPositionRankings: tool({
        description:
          'Get the top players at a specific position, ranked by projected fantasy points. Use for questions like "Who are the top 10 RBs?" or "Best QBs this week?".',
        inputSchema: z.object({
          position: z
            .enum(['QB', 'RB', 'WR', 'TE', 'K'])
            .describe('Position to rank'),
          limit: z
            .number()
            .min(1)
            .max(50)
            .default(10)
            .describe('Number of players to return'),
          season: z.number().default(2026).describe('NFL season year'),
          week: z
            .number()
            .min(1)
            .max(18)
            .describe('NFL week number (1-18)'),
          scoring: z
            .enum(['ppr', 'half_ppr', 'standard'])
            .default('half_ppr')
            .describe('Fantasy scoring format')
        }),
        execute: async ({ position, limit, season, week, scoring }) => {
          const params = new URLSearchParams({
            season: String(season),
            week: String(week),
            scoring,
            position,
            limit: String(limit)
          });
          type RankingsPayload = { projections: Array<{
            player_name: string;
            player_id: string;
            team: string;
            position: string;
            projected_points: number;
            projected_floor: number;
            projected_ceiling: number;
            injury_status: string | null;
          }> };
          const result = await fastapiGet<RankingsPayload>(`/api/projections?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.projections?.length) {
            return { found: false, message: `No ${position} projections for week ${week} of ${season}.` };
          }

          const ranked = result.data.projections
            .sort((a, b) => b.projected_points - a.projected_points)
            .slice(0, limit)
            .map((p, i) => ({
              rank: i + 1,
              player_name: p.player_name,
              team: p.team,
              projected_points: p.projected_points,
              projected_floor: p.projected_floor,
              projected_ceiling: p.projected_ceiling,
              injury_status: p.injury_status ?? 'Active'
            }));

          return {
            found: true,
            position,
            scoring_format: scoring,
            season,
            week,
            rankings: ranked
          };
        }
      }),

      getGamePredictions: tool({
        description:
          'Get game predictions with spreads, totals, and confidence tiers. Use for questions like "What games have the biggest edges?" or "Who wins Chiefs vs Bills?".',
        inputSchema: z.object({
          season: z.number().default(2024).describe('NFL season year'),
          week: z
            .number()
            .min(1)
            .max(18)
            .describe('NFL week number (1-18)')
        }),
        execute: async ({ season, week }) => {
          const params = new URLSearchParams({
            season: String(season),
            week: String(week)
          });
          type PredictionPayload = { predictions: Array<{
            game_id: string;
            home_team: string;
            away_team: string;
            predicted_spread: number;
            predicted_total: number;
            vegas_spread: number;
            vegas_total: number;
            edge_spread: number;
            edge_total: number;
            confidence_tier: string;
            ats_pick: string;
            ou_pick: string;
          }> };
          const result = await fastapiGet<PredictionPayload>(`/api/predictions?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.predictions?.length) {
            return { found: false, message: `No predictions for week ${week} of ${season}.` };
          }

          return {
            found: true,
            season,
            week,
            predictions: result.data.predictions.map((g) => ({
              matchup: `${g.away_team} @ ${g.home_team}`,
              predicted_spread: g.predicted_spread,
              predicted_total: g.predicted_total,
              vegas_spread: g.vegas_spread,
              vegas_total: g.vegas_total,
              edge_spread: g.edge_spread,
              edge_total: g.edge_total,
              confidence_tier: g.confidence_tier,
              ats_pick: g.ats_pick,
              ou_pick: g.ou_pick
            }))
          };
        }
      }),

      getTeamRoster: tool({
        description:
          'Get a team roster/lineup with projected fantasy points. Use for questions like "Show me the Chiefs roster" or "Who is starting for the Packers?".',
        inputSchema: z.object({
          team: z
            .string()
            .describe('NFL team abbreviation, e.g. "KC", "GB", "SF"'),
          season: z.number().default(2026).describe('NFL season year'),
          week: z
            .number()
            .min(1)
            .max(18)
            .default(1)
            .describe('NFL week number (1-18)'),
          scoring: z
            .enum(['ppr', 'half_ppr', 'standard'])
            .default('half_ppr')
            .describe('Fantasy scoring format')
        }),
        execute: async ({ team, season, week, scoring }) => {
          const params = new URLSearchParams({
            season: String(season),
            week: String(week),
            scoring,
            team: team.toUpperCase()
          });
          type LineupPayload = { lineup: Array<{
            player_name: string;
            player_id: string;
            team: string;
            position: string;
            projected_points: number;
            projected_floor: number;
            projected_ceiling: number;
            injury_status: string | null;
            is_starter: boolean;
          }> };
          const result = await fastapiGet<LineupPayload>(`/api/lineups?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.lineup?.length) {
            return { found: false, message: `No lineup data for ${team.toUpperCase()} in week ${week} of ${season}.` };
          }

          const roster = result.data.lineup.map((p) => ({
            player_name: p.player_name,
            position: p.position,
            projected_points: p.projected_points,
            projected_floor: p.projected_floor,
            projected_ceiling: p.projected_ceiling,
            injury_status: p.injury_status ?? 'Active',
            is_starter: p.is_starter
          }));

          return {
            found: true,
            team: team.toUpperCase(),
            season,
            week,
            scoring_format: scoring,
            roster
          };
        }
      }),

      getTeamSentiment: tool({
        description:
          'Get team-level sentiment and outlook scores. Use for questions like "What is the outlook for the Jets?" or "Which teams are trending up?".',
        inputSchema: z.object({
          season: z.number().default(2025).describe('Season to pull sentiment from')
        }),
        execute: async ({ season }) => {
          const params = new URLSearchParams({
            season: String(season)
          });
          type TeamSentimentPayload = Array<{
            team: string;
            sentiment_score: number;
            article_count: number;
            bullish_count: number;
            bearish_count: number;
          }>;
          const result = await fastapiGet<TeamSentimentPayload>(`/api/news/team?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.length) {
            return { found: false, message: 'No team sentiment data available.' };
          }

          const teams = result.data
            .sort((a, b) => b.sentiment_score - a.sentiment_score)
            .map((t) => ({
              team: t.team,
              sentiment_score: t.sentiment_score,
              article_count: t.article_count,
              bullish_count: t.bullish_count,
              bearish_count: t.bearish_count
            }));

          return { found: true, season, teams };
        }
      }),

      getPlayerNews: tool({
        description:
          'Get recent news and injury updates for a specific player. Use for questions like "Any news on Tyreek Hill?" or "Is Pacheco healthy?".',
        inputSchema: z.object({
          playerName: z
            .string()
            .describe('Player name to search for news about'),
          season: z.number().default(2025).describe('Season to pull news from'),
          limit: z
            .number()
            .default(5)
            .describe('Maximum number of news items')
        }),
        execute: async ({ playerName, season, limit }) => {
          const params = new URLSearchParams({
            season: String(season),
            limit: String(Math.max(limit * 5, 25))
          });
          type NewsPayload = Array<{
            title: string | null;
            source: string;
            url: string | null;
            published_at: string | null;
            sentiment: number | null;
            category: string | null;
            player_name: string | null;
            team: string | null;
            body_snippet: string | null;
            is_ruled_out: boolean;
            is_inactive: boolean;
            is_questionable: boolean;
          }>;
          const result = await fastapiGet<NewsPayload>(`/api/news/feed?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }

          const name = playerName.toLowerCase();
          const playerItems = result.data.filter((item) => {
            const itemName = (item.player_name ?? '').toLowerCase();
            const itemTitle = (item.title ?? '').toLowerCase();
            const itemBody = (item.body_snippet ?? '').toLowerCase();
            return (
              itemName.includes(name) ||
              itemTitle.includes(name) ||
              itemBody.includes(name)
            );
          }).slice(0, limit);

          if (!playerItems.length) {
            return {
              found: false,
              message: `No recent news found for "${playerName}".`
            };
          }

          return {
            found: true,
            player_name: playerName,
            items: playerItems.map((item) => ({
              title: item.title,
              source: item.source,
              published_at: item.published_at,
              sentiment: item.sentiment,
              category: item.category,
              team: item.team,
              snippet: item.body_snippet,
              is_ruled_out: item.is_ruled_out,
              is_questionable: item.is_questionable
            }))
          };
        }
      }),

      getDraftBoard: tool({
        description:
          'Get the draft board with ADP, VORP, and value tiers. Use for questions like "What is the best value pick?" or "Who should I draft at pick 5?".',
        inputSchema: z.object({
          scoring: z
            .enum(['ppr', 'half_ppr', 'standard'])
            .default('half_ppr')
            .describe('Fantasy scoring format'),
          limit: z
            .number()
            .min(1)
            .max(200)
            .default(50)
            .describe('Number of players to return')
        }),
        execute: async ({ scoring, limit }) => {
          const params = new URLSearchParams({ scoring });
          type DraftPayload = { board: Array<{
            player_name: string;
            player_id: string;
            team: string;
            position: string;
            adp: number;
            projected_points: number;
            vorp: number;
            value_tier: string;
            bye_week: number | null;
          }> };
          const result = await fastapiGet<DraftPayload>(`/api/draft/board?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }
          if (!result.data.board?.length) {
            return { found: false, message: 'No draft board data available.' };
          }

          const board = result.data.board.slice(0, limit).map((p, i) => ({
            overall_rank: i + 1,
            player_name: p.player_name,
            team: p.team,
            position: p.position,
            adp: p.adp,
            projected_points: p.projected_points,
            vorp: p.vorp,
            value_tier: p.value_tier,
            bye_week: p.bye_week
          }));

          return {
            found: true,
            scoring_format: scoring,
            board
          };
        }
      }),

      getSentimentSummary: tool({
        description:
          'Get overall sentiment summary including most bullish and bearish players, source stats, and trend data. Use for questions like "What is the overall sentiment?" or "Who are the most hyped players?".',
        inputSchema: z.object({
          season: z.number().default(2025).describe('Season to pull summary from')
        }),
        execute: async ({ season }) => {
          const params = new URLSearchParams({
            season: String(season)
          });
          type SummaryPayload = {
            total_articles: number;
            sources: Array<{ source: string; count: number }>;
            bullish_players: Array<{ player_name: string; team: string; sentiment_score: number }>;
            bearish_players: Array<{ player_name: string; team: string; sentiment_score: number }>;
            average_sentiment: number;
          };
          const result = await fastapiGet<SummaryPayload>(`/api/news/summary?${params}`);

          if (!result.ok) {
            return { found: false, message: result.message };
          }

          return {
            found: true,
            season,
            total_articles: result.data.total_articles,
            sources: result.data.sources,
            average_sentiment: result.data.average_sentiment,
            bullish_players: result.data.bullish_players,
            bearish_players: result.data.bearish_players
          };
        }
      })
    }
  });

  return result.toUIMessageStreamResponse({
    onError: (error: unknown) => {
      if (error instanceof Error) return error.message;
      if (typeof error === 'string') return error;
      return 'An unexpected error occurred';
    }
  });
}
