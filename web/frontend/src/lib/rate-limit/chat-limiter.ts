/**
 * Abuse limits for the public /api/chat route (it spends LLM credits and,
 * while billing is off, every visitor is anonymous).
 *
 * CAVEAT: this state lives in module memory, so it is per serverless
 * instance and resets on cold start. It is best-effort only. The real fix is
 * a shared store (Vercel KV / Upstash Redis) -- deliberately not added yet.
 */

export const MAX_MESSAGES = 30;
export const MAX_TOTAL_CHARS = 24_000;
export const PER_MINUTE = 10;
export const PER_DAY = 60;
const MINUTE_MS = 60_000;
const DAY_MS = 86_400_000;
// Bound memory: beyond this many tracked IPs, new ones share the "unknown"
// bucket (failing closed would lock every real user out).
const MAX_TRACKED_IPS = 5_000;

export type LimitResult =
  | { ok: true }
  | { ok: false; status: 400 | 413 | 429 | 503; error: string; retryAfter?: number };

const hits = new Map<string, number[]>();
let globalDay = { key: '', count: 0 };

export function resetChatLimiter(): void {
  hits.clear();
  globalDay = { key: '', count: 0 };
}

export function clientIp(req: Request): string {
  const first = req.headers.get('x-forwarded-for')?.split(',')[0]?.trim();
  return first || 'unknown';
}

/** Total characters of text parts (or legacy string content) across messages. */
export function totalTextChars(messages: unknown[]): number {
  let n = 0;
  for (const m of messages) {
    const msg = m as { content?: unknown; parts?: Array<{ text?: unknown }> };
    if (typeof msg?.content === 'string') n += msg.content.length;
    if (Array.isArray(msg?.parts)) {
      for (const p of msg.parts) if (typeof p?.text === 'string') n += p.text.length;
    }
  }
  return n;
}

/** Returns an error result when the body is malformed or too large, else null. */
export function checkBodySize(messages: unknown): LimitResult | null {
  if (!Array.isArray(messages)) {
    return { ok: false, status: 400, error: 'Invalid request.' };
  }
  if (messages.length > MAX_MESSAGES || totalTextChars(messages) > MAX_TOTAL_CHARS) {
    return {
      ok: false,
      status: 413,
      error: 'This conversation is too long. Please start a new chat.'
    };
  }
  return null;
}

/**
 * Per-IP sliding windows (10/min, 60/day) plus a global daily ceiling
 * (`CHAT_DAILY_REQUEST_CAP`, default 2000). Records the hit when allowed.
 */
export function checkRateLimit(ip: string, now: number = Date.now()): LimitResult {
  const dayKey = new Date(now).toISOString().slice(0, 10);
  if (globalDay.key !== dayKey) globalDay = { key: dayKey, count: 0 };
  const cap = Number(process.env.CHAT_DAILY_REQUEST_CAP) || 2000;
  if (globalDay.count >= cap) {
    return {
      ok: false,
      status: 503,
      error: 'The advisor is at capacity today. Try again tomorrow.'
    };
  }

  const id = hits.has(ip) || hits.size < MAX_TRACKED_IPS ? ip : 'unknown';
  const recent = (hits.get(id) ?? []).filter((t) => now - t < DAY_MS);
  const lastMinute = recent.filter((t) => now - t < MINUTE_MS);
  hits.set(id, recent);
  if (lastMinute.length >= PER_MINUTE) {
    const retryAfter = Math.max(1, Math.ceil((lastMinute[0] + MINUTE_MS - now) / 1000));
    return { ok: false, status: 429, error: 'Too many requests. Please slow down.', retryAfter };
  }
  if (recent.length >= PER_DAY) {
    const retryAfter = Math.max(1, Math.ceil((recent[0] + DAY_MS - now) / 1000));
    return {
      ok: false,
      status: 429,
      error: 'Daily advisor limit reached. Try again tomorrow.',
      retryAfter
    };
  }
  recent.push(now);
  globalDay.count += 1;
  return { ok: true };
}
