import { describe, expect, it } from 'vitest';
import type Stripe from 'stripe';
import { hasPremiumAccess } from '../access';
import { resolvePremiumUpdate } from '../webhook-handlers';

describe('hasPremiumAccess (PLAN 2 feature flag)', () => {
  it('grants everything when Clerk keys are absent (site behaves as today)', () => {
    expect(
      hasPremiumAccess({ clerkEnabled: false, signedIn: false, premium: false })
    ).toBe(true);
    expect(hasPremiumAccess({ clerkEnabled: false, signedIn: true, premium: false })).toBe(
      true
    );
  });

  it('denies anonymous sessions when Clerk is enabled', () => {
    expect(hasPremiumAccess({ clerkEnabled: true, signedIn: false, premium: false })).toBe(
      false
    );
  });

  it('denies signed-in users without premium metadata', () => {
    expect(hasPremiumAccess({ clerkEnabled: true, signedIn: true, premium: false })).toBe(
      false
    );
  });

  it('grants signed-in premium users', () => {
    expect(hasPremiumAccess({ clerkEnabled: true, signedIn: true, premium: true })).toBe(
      true
    );
  });

  it('never grants premium metadata without a session', () => {
    expect(hasPremiumAccess({ clerkEnabled: true, signedIn: false, premium: true })).toBe(
      false
    );
  });
});

function makeEvent(type: string, object: Record<string, unknown>): Stripe.Event {
  return { type, data: { object } } as unknown as Stripe.Event;
}

describe('resolvePremiumUpdate (Stripe event → Clerk metadata)', () => {
  it('grants premium on checkout.session.completed via client_reference_id', () => {
    const update = resolvePremiumUpdate(
      makeEvent('checkout.session.completed', {
        client_reference_id: 'user_123',
        customer: 'cus_abc'
      })
    );
    expect(update).toEqual({ userId: 'user_123', premium: true, stripeCustomerId: 'cus_abc' });
  });

  it('falls back to metadata.clerkUserId on checkout completion', () => {
    const update = resolvePremiumUpdate(
      makeEvent('checkout.session.completed', {
        client_reference_id: null,
        metadata: { clerkUserId: 'user_456' },
        customer: { id: 'cus_def' }
      })
    );
    expect(update).toEqual({ userId: 'user_456', premium: true, stripeCustomerId: 'cus_def' });
  });

  it('returns null when checkout cannot be attributed to a user', () => {
    expect(
      resolvePremiumUpdate(
        makeEvent('checkout.session.completed', { client_reference_id: null, metadata: {} })
      )
    ).toBeNull();
  });

  it.each(['active', 'trialing'])('keeps premium for %s subscriptions', (status) => {
    const update = resolvePremiumUpdate(
      makeEvent('customer.subscription.updated', {
        status,
        metadata: { clerkUserId: 'user_123' },
        customer: 'cus_abc'
      })
    );
    expect(update?.premium).toBe(true);
  });

  it.each(['past_due', 'canceled', 'unpaid', 'incomplete'])(
    'revokes premium for %s subscriptions',
    (status) => {
      const update = resolvePremiumUpdate(
        makeEvent('customer.subscription.updated', {
          status,
          metadata: { clerkUserId: 'user_123' },
          customer: 'cus_abc'
        })
      );
      expect(update?.premium).toBe(false);
    }
  );

  it('revokes premium on customer.subscription.deleted', () => {
    const update = resolvePremiumUpdate(
      makeEvent('customer.subscription.deleted', {
        status: 'canceled',
        metadata: { clerkUserId: 'user_123' }
      })
    );
    expect(update).toEqual({ userId: 'user_123', premium: false });
  });

  it('ignores subscription events without a clerkUserId', () => {
    expect(
      resolvePremiumUpdate(
        makeEvent('customer.subscription.deleted', { status: 'canceled', metadata: {} })
      )
    ).toBeNull();
  });

  it('ignores unrelated event types', () => {
    expect(resolvePremiumUpdate(makeEvent('invoice.paid', {}))).toBeNull();
  });
});
