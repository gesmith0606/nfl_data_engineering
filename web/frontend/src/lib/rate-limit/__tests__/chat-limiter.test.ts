import { beforeEach, describe, expect, it } from 'vitest';
import {
  checkBodySize,
  checkRateLimit,
  clientIp,
  resetChatLimiter
} from '../chat-limiter';

const T0 = Date.parse('2026-11-21T12:00:00Z');

describe('chat limiter', () => {
  beforeEach(() => {
    resetChatLimiter();
    delete process.env.CHAT_DAILY_REQUEST_CAP;
  });

  it('allows 10 per minute then 429 with Retry-After', () => {
    for (let i = 0; i < 10; i++) expect(checkRateLimit('1.1.1.1', T0 + i).ok).toBe(true);
    const r = checkRateLimit('1.1.1.1', T0 + 10);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.status).toBe(429);
      expect(r.retryAfter).toBeGreaterThan(0);
    }
    expect(checkRateLimit('1.1.1.1', T0 + 61_000).ok).toBe(true);
  });

  it('isolates IPs', () => {
    for (let i = 0; i < 10; i++) checkRateLimit('a', T0);
    expect(checkRateLimit('b', T0).ok).toBe(true);
  });

  it('caps 60 per day per IP', () => {
    for (let i = 0; i < 60; i++) expect(checkRateLimit('d', T0 + i * 7_000).ok).toBe(true);
    expect(checkRateLimit('d', T0 + 60 * 7_000).ok).toBe(false);
  });

  it('503s past the global daily cap', () => {
    process.env.CHAT_DAILY_REQUEST_CAP = '2';
    expect(checkRateLimit('x', T0).ok).toBe(true);
    expect(checkRateLimit('y', T0).ok).toBe(true);
    const r = checkRateLimit('z', T0);
    expect(!r.ok && r.status).toBe(503);
  });

  it('rejects oversized or malformed bodies', () => {
    const msg = { role: 'user', parts: [{ type: 'text', text: 'hi' }] };
    expect(checkBodySize([msg])).toBeNull();
    const many = checkBodySize(Array(31).fill(msg));
    expect(!!many && !many.ok && many.status).toBe(413);
    const big = checkBodySize([
      { role: 'user', parts: [{ type: 'text', text: 'x'.repeat(24_001) }] }
    ]);
    expect(!!big && !big.ok && big.status).toBe(413);
    expect(checkBodySize('nope')).toMatchObject({ status: 400 });
  });

  it('reads first x-forwarded-for hop', () => {
    const req = new Request('http://x', { headers: { 'x-forwarded-for': '9.9.9.9, 10.0.0.1' } });
    expect(clientIp(req)).toBe('9.9.9.9');
    expect(clientIp(new Request('http://x'))).toBe('unknown');
  });
});
