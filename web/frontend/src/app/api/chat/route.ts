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
- If a player is injured (Out, IR, Doubtful), clearly warn the user.
- Present numbers clearly: "12.4 pts (floor: 6.2, ceiling: 22.1)".
- Be concise but thorough. Lead with the recommendation, then explain why.
- If you don't have data, say so honestly.

Current season: 2026
Default scoring: Half-PPR (unless user specifies otherwise)`;

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

/** Fetch a JSON resource from the FastAPI backend (server-side only). */
async function fastapiGet<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${FASTAPI_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      // Next.js: opt out of caching for live data
      cache: 'no-store'
    });
    if (!res.ok) return null;
    return res.json() as Promise<T>;
  } catch {
    return null;
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
          const data = await fastapiGet<{ projections: Array<{
            player_name: string;
            player_id: string;
            team: string;
            position: string;
            projected_points: number;
            projected_floor: number;
            projected_ceiling: number;
            injury_status: string | null;
          }> }>(`/api/projections?${params}`);

          if (!data?.projections?.length) {
            return { found: false, message: `No projection data for week ${week} of ${season}.` };
          }

          const name = playerName.toLowerCase();
          const match = data.projections.find((p) =>
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
          const data = await fastapiGet<{ projections: Array<{
            player_name: string;
            team: string;
            position: string;
            projected_points: number;
            projected_floor: number;
            projected_ceiling: number;
            injury_status: string | null;
          }> }>(`/api/projections?${params}`);

          if (!data?.projections?.length) {
            return { found: false, message: `No projection data for week ${week} of ${season}.` };
          }

          const findPlayer = (name: string) => {
            const lower = name.toLowerCase();
            return data.projections.find((p) =>
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
          const results = await fastapiGet<Array<{
            player_id: string;
            player_name: string;
            team: string;
            position: string;
          }>>(`/api/players/search?${params}`);

          if (!results?.length) {
            return { found: false, message: `No players matched "${query}".` };
          }
          return { found: true, players: results.slice(0, 10) };
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

          const items = await fastapiGet<Array<{
            title: string | null;
            source: string;
            published_at: string | null;
            player_name: string | null;
            team: string | null;
            body_snippet: string | null;
            is_ruled_out: boolean;
            is_questionable: boolean;
          }>>(`/api/news/feed?${params}`);

          if (!items?.length) {
            return { found: false, message: 'No news items available.' };
          }
          return { found: true, items };
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
