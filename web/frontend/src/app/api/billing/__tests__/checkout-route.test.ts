// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '../checkout/route';
import { currentUser } from '@clerk/nextjs/server';
import { getStripeClient } from '@/lib/billing/stripe';

vi.mock('@clerk/nextjs/server', () => ({
  currentUser: vi.fn()
}));

vi.mock('@/lib/billing/stripe', () => ({
  getStripeClient: vi.fn()
}));

const mockCurrentUser = vi.mocked(currentUser);
const mockGetStripeClient = vi.mocked(getStripeClient);

const ENV_KEYS = [
  'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY',
  'STRIPE_SECRET_KEY',
  'NEXT_PUBLIC_STRIPE_PRICE_ID'
] as const;
const savedEnv: Record<string, string | undefined> = {};

function makeUser(overrides: Record<string, unknown> = {}) {
  return {
    id: 'user_123',
    publicMetadata: {},
    privateMetadata: {},
    primaryEmailAddressId: 'email_1',
    emailAddresses: [{ id: 'email_1', emailAddress: 'fan@example.com' }],
    ...overrides
  } as never;
}

describe('POST /api/billing/checkout', () => {
  const sessionsCreate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    for (const key of ENV_KEYS) savedEnv[key] = process.env[key];
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = 'pk_test_123';
    process.env.STRIPE_SECRET_KEY = 'sk_test_123';
    process.env.NEXT_PUBLIC_STRIPE_PRICE_ID = 'price_123';
    sessionsCreate.mockResolvedValue({ url: 'https://checkout.stripe.com/c/pay/cs_test' });
    mockGetStripeClient.mockReturnValue({
      checkout: { sessions: { create: sessionsCreate } }
    } as never);
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      if (savedEnv[key] === undefined) delete process.env[key];
      else process.env[key] = savedEnv[key];
    }
  });

  const request = () =>
    new Request('https://frontend-jet-seven-33.vercel.app/api/billing/checkout', {
      method: 'POST'
    });

  it('returns 503 when billing env is not configured', async () => {
    delete process.env.STRIPE_SECRET_KEY;
    const res = await POST(request());
    expect(res.status).toBe(503);
    expect(sessionsCreate).not.toHaveBeenCalled();
  });

  it('returns 401 for signed-out users', async () => {
    mockCurrentUser.mockResolvedValue(null);
    const res = await POST(request());
    expect(res.status).toBe(401);
    expect(sessionsCreate).not.toHaveBeenCalled();
  });

  it('returns 409 for already-premium users instead of double-subscribing', async () => {
    mockCurrentUser.mockResolvedValue(makeUser({ publicMetadata: { premium: true } }));
    const res = await POST(request());
    expect(res.status).toBe(409);
    expect(sessionsCreate).not.toHaveBeenCalled();
  });

  it('creates a trial subscription session stamped with the Clerk user id', async () => {
    mockCurrentUser.mockResolvedValue(makeUser());
    const res = await POST(request());
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ url: 'https://checkout.stripe.com/c/pay/cs_test' });
    expect(sessionsCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'subscription',
        client_reference_id: 'user_123',
        metadata: { clerkUserId: 'user_123' },
        subscription_data: {
          trial_period_days: 7,
          metadata: { clerkUserId: 'user_123' }
        },
        customer_email: 'fan@example.com',
        success_url: 'https://frontend-jet-seven-33.vercel.app/dashboard?upgraded=1',
        cancel_url: 'https://frontend-jet-seven-33.vercel.app/pricing'
      })
    );
  });

  it('reuses the stored Stripe customer for returning subscribers', async () => {
    mockCurrentUser.mockResolvedValue(
      makeUser({ privateMetadata: { stripeCustomerId: 'cus_abc' } })
    );
    const res = await POST(request());
    expect(res.status).toBe(200);
    const args = sessionsCreate.mock.calls[0][0];
    expect(args.customer).toBe('cus_abc');
    expect(args.customer_email).toBeUndefined();
  });

  it('returns 500 when Stripe rejects the session', async () => {
    mockCurrentUser.mockResolvedValue(makeUser());
    sessionsCreate.mockRejectedValue(new Error('stripe down'));
    const res = await POST(request());
    expect(res.status).toBe(500);
  });
});
