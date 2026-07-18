// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '../webhook/route';
import { applyPremiumUpdate } from '@/lib/billing/clerk-admin';
import { getStripeClient } from '@/lib/billing/stripe';

vi.mock('@/lib/billing/clerk-admin', () => ({
  applyPremiumUpdate: vi.fn()
}));

vi.mock('@/lib/billing/stripe', () => ({
  getStripeClient: vi.fn()
}));

const mockApplyPremiumUpdate = vi.mocked(applyPremiumUpdate);
const mockGetStripeClient = vi.mocked(getStripeClient);

const ENV_KEYS = ['STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET'] as const;
const savedEnv: Record<string, string | undefined> = {};

function webhookRequest(body = '{}', signature: string | null = 't=1,v1=sig') {
  const headers: Record<string, string> = {};
  if (signature !== null) headers['stripe-signature'] = signature;
  return new Request('https://frontend-jet-seven-33.vercel.app/api/billing/webhook', {
    method: 'POST',
    headers,
    body
  });
}

describe('POST /api/billing/webhook', () => {
  const constructEvent = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    for (const key of ENV_KEYS) savedEnv[key] = process.env[key];
    process.env.STRIPE_SECRET_KEY = 'sk_test_123';
    process.env.STRIPE_WEBHOOK_SECRET = 'whsec_123';
    mockGetStripeClient.mockReturnValue({ webhooks: { constructEvent } } as never);
    mockApplyPremiumUpdate.mockResolvedValue(undefined);
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      if (savedEnv[key] === undefined) delete process.env[key];
      else process.env[key] = savedEnv[key];
    }
  });

  it('returns 503 when the webhook secret is not configured', async () => {
    delete process.env.STRIPE_WEBHOOK_SECRET;
    const res = await POST(webhookRequest());
    expect(res.status).toBe(503);
    expect(constructEvent).not.toHaveBeenCalled();
  });

  it('returns 400 when the stripe-signature header is missing', async () => {
    const res = await POST(webhookRequest('{}', null));
    expect(res.status).toBe(400);
    expect(constructEvent).not.toHaveBeenCalled();
  });

  it('returns 400 and touches nothing when signature verification fails', async () => {
    constructEvent.mockImplementation(() => {
      throw new Error('No signatures found matching the expected signature');
    });
    const res = await POST(webhookRequest('{"forged":true}'));
    expect(res.status).toBe(400);
    expect(mockApplyPremiumUpdate).not.toHaveBeenCalled();
  });

  it('verifies the raw payload against the configured secret', async () => {
    constructEvent.mockReturnValue({ type: 'invoice.paid', data: { object: {} } });
    await POST(webhookRequest('{"id":"evt_1"}', 't=2,v1=abc'));
    expect(constructEvent).toHaveBeenCalledWith('{"id":"evt_1"}', 't=2,v1=abc', 'whsec_123');
  });

  it('stamps premium on checkout.session.completed', async () => {
    constructEvent.mockReturnValue({
      type: 'checkout.session.completed',
      data: { object: { client_reference_id: 'user_123', customer: 'cus_abc' } }
    });
    const res = await POST(webhookRequest());
    expect(res.status).toBe(200);
    expect(mockApplyPremiumUpdate).toHaveBeenCalledWith({
      userId: 'user_123',
      premium: true,
      stripeCustomerId: 'cus_abc'
    });
  });

  it('revokes premium on customer.subscription.deleted (cancellation)', async () => {
    constructEvent.mockReturnValue({
      type: 'customer.subscription.deleted',
      data: { object: { status: 'canceled', metadata: { clerkUserId: 'user_123' } } }
    });
    const res = await POST(webhookRequest());
    expect(res.status).toBe(200);
    expect(mockApplyPremiumUpdate).toHaveBeenCalledWith({ userId: 'user_123', premium: false });
  });

  it('acks irrelevant events without touching Clerk (idempotent no-op)', async () => {
    constructEvent.mockReturnValue({ type: 'invoice.paid', data: { object: {} } });
    const res = await POST(webhookRequest());
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ received: true });
    expect(mockApplyPremiumUpdate).not.toHaveBeenCalled();
  });

  it('returns 500 so Stripe retries when the Clerk update fails', async () => {
    constructEvent.mockReturnValue({
      type: 'checkout.session.completed',
      data: { object: { client_reference_id: 'user_123', customer: 'cus_abc' } }
    });
    mockApplyPremiumUpdate.mockRejectedValue(new Error('clerk 500'));
    const res = await POST(webhookRequest());
    expect(res.status).toBe(500);
  });
});
