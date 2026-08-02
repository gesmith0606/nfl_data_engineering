// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '../route';
import { getSubscriptionStatus } from '@/lib/billing/subscription';
import { streamText } from 'ai';

// Phase 83 TOOL-01/TOOL-02 — exercises getProjectionComparison and
// getMatchupAdvantages the same way premium-gate.test.ts exercises the route:
// `tool()` is mocked to the identity function so the definitions passed to
// `streamText` are the real tool objects, then `streamText` is mocked to
// capture them so each tool's `execute` can be called directly against a
// stubbed `fetch`.
vi.mock('@/lib/billing/subscription', () => ({
  getSubscriptionStatus: vi.fn()
}));

vi.mock('ai', () => ({
  streamText: vi.fn(),
  convertToModelMessages: vi.fn(async () => []),
  stepCountIs: vi.fn(() => 'stop-when'),
  tool: vi.fn((definition: unknown) => definition)
}));

vi.mock('@ai-sdk/google', () => ({
  google: vi.fn(() => 'gemini-model')
}));

vi.mock('@ai-sdk/groq', () => ({
  createGroq: vi.fn(() => () => 'groq-model')
}));

const mockGetSubscriptionStatus = vi.mocked(getSubscriptionStatus);
const mockStreamText = vi.mocked(streamText);

function chatRequest() {
  return new Request('https://frontend-jet-seven-33.vercel.app/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages: [] })
  });
}

type AdvisorTool = { execute: (args: never) => Promise<Record<string, unknown>> };
type ToolMap = Record<string, AdvisorTool>;

/** Drives POST() once and captures the real `tools` object passed to streamText. */
async function getTools(): Promise<ToolMap> {
  let captured: ToolMap | undefined;
  mockStreamText.mockImplementationOnce((config: unknown) => {
    captured = (config as { tools: ToolMap }).tools;
    return { toUIMessageStreamResponse: () => new Response('stream') } as never;
  });
  const res = await POST(chatRequest());
  if (res.status !== 200 || !captured) {
    throw new Error(`streamText was not invoked (status ${res.status})`);
  }
  return captured;
}

describe('advisor tools — Phase 83 (TOOL-01/TOOL-02)', () => {
  const originalGoogleKey = process.env.GOOGLE_GENERATIVE_AI_API_KEY;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.GOOGLE_GENERATIVE_AI_API_KEY = 'test-key';
    mockGetSubscriptionStatus.mockResolvedValue({
      billingEnabled: false,
      signedIn: false,
      premium: false,
      hasAccess: true
    });
  });

  afterEach(() => {
    if (originalGoogleKey === undefined) delete process.env.GOOGLE_GENERATIVE_AI_API_KEY;
    else process.env.GOOGLE_GENERATIVE_AI_API_KEY = originalGoogleKey;
    vi.unstubAllGlobals();
  });

  describe('getProjectionComparison', () => {
    it('returns the matched player\'s per-source comparison', async () => {
      const tools = await getTools();
      vi.stubGlobal(
        'fetch',
        vi.fn(
          async () =>
            new Response(
              JSON.stringify({
                rows: [
                  {
                    player_name: 'Justin Jefferson',
                    position: 'WR',
                    team: 'MIN',
                    ours: 18.4,
                    espn: 20.1,
                    sleeper: 19.5,
                    yahoo: 17.9,
                    delta_vs_ours: 1.37
                  }
                ],
                source_labels: {
                  espn: 'ESPN',
                  sleeper: 'Sleeper',
                  yahoo: 'Yahoo via FantasyPros consensus'
                }
              }),
              { status: 200 }
            )
        )
      );

      const result = await tools.getProjectionComparison.execute({
        player_name: 'jefferson',
        season: 2026,
        week: 5,
        scoring: 'half_ppr'
      } as never);

      expect(result.found).toBe(true);
      expect(result.player_name).toBe('Justin Jefferson');
      expect(result.team).toBe('MIN');
      expect(result.espn).toBe(20.1);
      expect(result.sleeper).toBe(19.5);
      expect(result.delta_vs_ours).toBeCloseTo(1.37);
      expect(result.resolved_week_auto).toBe(false);
    });

    it('reports not-found for a player missing from the comparison table', async () => {
      const tools = await getTools();
      vi.stubGlobal(
        'fetch',
        vi.fn(
          async () =>
            new Response(
              JSON.stringify({
                rows: [
                  {
                    player_name: 'Someone Else',
                    position: 'RB',
                    team: 'KC',
                    ours: 10,
                    espn: 11,
                    sleeper: 9,
                    yahoo: 10,
                    delta_vs_ours: 0
                  }
                ],
                source_labels: {}
              }),
              { status: 200 }
            )
        )
      );

      const result = await tools.getProjectionComparison.execute({
        player_name: 'nobody matches this string',
        season: 2026,
        week: 5,
        scoring: 'half_ppr'
      } as never);

      expect(result.found).toBe(false);
      expect(result.message).toMatch(/not found/i);
    });

    it('reports empty comparison data without erroring', async () => {
      const tools = await getTools();
      vi.stubGlobal(
        'fetch',
        vi.fn(
          async () => new Response(JSON.stringify({ rows: [], source_labels: {} }), { status: 200 })
        )
      );

      const result = await tools.getProjectionComparison.execute({
        player_name: 'jefferson',
        season: 2026,
        week: 5,
        scoring: 'half_ppr'
      } as never);

      expect(result.found).toBe(false);
      expect(result.message).toMatch(/no external-projection comparison data/i);
    });

    it('surfaces a clear message when the backend is unreachable', async () => {
      const tools = await getTools();
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => {
          throw new Error('fetch failed: ECONNREFUSED');
        })
      );

      const result = await tools.getProjectionComparison.execute({
        player_name: 'jefferson',
        season: 2026,
        week: 5,
        scoring: 'half_ppr'
      } as never);

      expect(result.found).toBe(false);
      expect(result.message).toMatch(/backend.*unavailable|unavailable/i);
    });
  });

  describe('getMatchupAdvantages', () => {
    const defenseMetricsPayload = {
      team: 'KC',
      season: 2026,
      requested_week: 5,
      source_week: 5,
      fallback: false,
      overall_def_rating: 74,
      def_sos_rank: 12,
      positional: [
        { position: 'QB', avg_pts_allowed: 18.2, rank: 10, rating: 70 },
        { position: 'RB', avg_pts_allowed: 22.1, rank: 28, rating: 90 },
        { position: 'WR', avg_pts_allowed: 30.4, rank: 15, rating: 68 },
        { position: 'TE', avg_pts_allowed: 10.1, rank: 3, rating: 55 }
      ]
    };

    it('returns per-position defensive ranks for a valid team, normalizing case', async () => {
      const tools = await getTools();
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => new Response(JSON.stringify(defenseMetricsPayload), { status: 200 }))
      );

      const result = await tools.getMatchupAdvantages.execute({
        team: 'kc',
        week: 5,
        season: 2026
      } as never);

      expect(result.found).toBe(true);
      expect(result.team).toBe('KC');
      expect(result.team_name).toBe('Kansas City Chiefs');
      expect(result.overall_def_rating).toBe(74);
      expect(result.by_position).toHaveLength(4);
      // Rank 28 (RB) is the highest rank number = easiest matchup to target.
      expect(result.best_position_to_target).toBe('RB');
    });

    it('rejects an unrecognized team abbreviation without calling the backend', async () => {
      const tools = await getTools();
      const fetchSpy = vi.fn();
      vi.stubGlobal('fetch', fetchSpy);

      const result = await tools.getMatchupAdvantages.execute({
        team: 'ZZZ',
        week: 5,
        season: 2026
      } as never);

      expect(result.found).toBe(false);
      expect(result.message).toMatch(/not a recognized nfl team/i);
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('surfaces the backend 404 for a team missing from silver data', async () => {
      const tools = await getTools();
      vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 404 })));

      const result = await tools.getMatchupAdvantages.execute({
        team: 'KC',
        week: 5,
        season: 2026
      } as never);

      expect(result.found).toBe(false);
      expect(typeof result.message).toBe('string');
    });

    it('surfaces a clear message when the backend is unreachable', async () => {
      const tools = await getTools();
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => {
          throw new Error('fetch failed: ECONNREFUSED');
        })
      );

      const result = await tools.getMatchupAdvantages.execute({
        team: 'KC',
        week: 5,
        season: 2026
      } as never);

      expect(result.found).toBe(false);
      expect(result.message).toMatch(/backend.*unavailable|unavailable/i);
    });
  });
});
