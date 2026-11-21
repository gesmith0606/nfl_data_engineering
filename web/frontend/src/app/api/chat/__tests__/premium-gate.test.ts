// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '../route';
import { resetChatLimiter } from '@/lib/rate-limit/chat-limiter';
import { getSubscriptionStatus } from '@/lib/billing/subscription';
import { streamText } from 'ai';

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

describe('POST /api/chat premium gate', () => {
  const originalGoogleKey = process.env.GOOGLE_GENERATIVE_AI_API_KEY;

  beforeEach(() => {
    resetChatLimiter();
    vi.clearAllMocks();
    process.env.GOOGLE_GENERATIVE_AI_API_KEY = 'test-key';
    mockStreamText.mockReturnValue({
      toUIMessageStreamResponse: () => new Response('stream')
    } as never);
  });

  afterEach(() => {
    if (originalGoogleKey === undefined) delete process.env.GOOGLE_GENERATIVE_AI_API_KEY;
    else process.env.GOOGLE_GENERATIVE_AI_API_KEY = originalGoogleKey;
  });

  it('returns 403 without spending LLM tokens when access is denied', async () => {
    mockGetSubscriptionStatus.mockResolvedValue({
      billingEnabled: true,
      signedIn: false,
      premium: false,
      hasAccess: false
    });
    const res = await POST(chatRequest());
    expect(res.status).toBe(403);
    expect(mockStreamText).not.toHaveBeenCalled();
  });

  it('blocks signed-in users whose subscription was cancelled', async () => {
    mockGetSubscriptionStatus.mockResolvedValue({
      billingEnabled: true,
      signedIn: true,
      premium: false,
      hasAccess: false
    });
    const res = await POST(chatRequest());
    expect(res.status).toBe(403);
    expect(mockStreamText).not.toHaveBeenCalled();
  });

  it('streams for premium sessions', async () => {
    mockGetSubscriptionStatus.mockResolvedValue({
      billingEnabled: true,
      signedIn: true,
      premium: true,
      hasAccess: true
    });
    const res = await POST(chatRequest());
    expect(res.status).toBe(200);
    expect(mockStreamText).toHaveBeenCalledTimes(1);
  });

  it('streams when billing is disabled (free-when-unconfigured)', async () => {
    mockGetSubscriptionStatus.mockResolvedValue({
      billingEnabled: false,
      signedIn: false,
      premium: false,
      hasAccess: true
    });
    const res = await POST(chatRequest());
    expect(res.status).toBe(200);
    expect(mockStreamText).toHaveBeenCalledTimes(1);
  });
});

describe('POST /api/chat abuse limits', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetChatLimiter();
    process.env.GOOGLE_GENERATIVE_AI_API_KEY = 'test-key';
    mockGetSubscriptionStatus.mockResolvedValue({
      billingEnabled: false,
      signedIn: false,
      premium: false,
      hasAccess: true
    });
    mockStreamText.mockReturnValue({
      toUIMessageStreamResponse: () => new Response('stream')
    } as never);
  });

  const post = (messages: unknown[]) =>
    POST(
      new Request('https://x.test/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-forwarded-for': '7.7.7.7' },
        body: JSON.stringify({ messages })
      })
    );

  it('413s oversized conversations before spending tokens', async () => {
    const msg = { role: 'user', parts: [{ type: 'text', text: 'a' }] };
    const res = await post(Array(31).fill(msg));
    expect(res.status).toBe(413);
    expect(mockStreamText).not.toHaveBeenCalled();
  });

  it('429s with Retry-After after 10 requests in a minute', async () => {
    for (let i = 0; i < 10; i++) expect((await post([])).status).toBe(200);
    const res = await post([]);
    expect(res.status).toBe(429);
    expect(res.headers.get('Retry-After')).toBeTruthy();
  });
});
