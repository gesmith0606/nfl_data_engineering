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
