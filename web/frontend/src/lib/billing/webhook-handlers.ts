import type Stripe from 'stripe';
import { PREMIUM_SUBSCRIPTION_STATUSES } from './access';

/**
 * Pure Stripe webhook → premium-status resolution. No SDK calls, no Clerk —
 * the route handler verifies the signature and applies the returned update,
 * which keeps this logic unit-testable with plain event fixtures.
 */

export interface PremiumUpdate {
  /** Clerk user id the event resolves to. */
  userId: string;
  /** New premium flag for Clerk publicMetadata. */
  premium: boolean;
  /** Stripe customer id to remember (privateMetadata) for the portal link. */
  stripeCustomerId?: string;
}

function customerId(customer: string | { id: string } | null | undefined): string | undefined {
  if (!customer) return undefined;
  return typeof customer === 'string' ? customer : customer.id;
}

/**
 * Map a verified Stripe event to a premium-metadata update, or null when the
 * event is irrelevant or cannot be attributed to a Clerk user.
 *
 * Attribution: checkout sessions carry the Clerk user id in
 * `client_reference_id` (and `metadata.clerkUserId`); subscriptions carry it
 * in `metadata.clerkUserId` because checkout sets `subscription_data.metadata`.
 */
export function resolvePremiumUpdate(event: Stripe.Event): PremiumUpdate | null {
  switch (event.type) {
    case 'checkout.session.completed': {
      const session = event.data.object as Stripe.Checkout.Session;
      const userId = session.client_reference_id ?? session.metadata?.clerkUserId;
      if (!userId) return null;
      return {
        userId,
        premium: true,
        stripeCustomerId: customerId(session.customer)
      };
    }
    case 'customer.subscription.updated': {
      const subscription = event.data.object as Stripe.Subscription;
      const userId = subscription.metadata?.clerkUserId;
      if (!userId) return null;
      return {
        userId,
        premium: PREMIUM_SUBSCRIPTION_STATUSES.has(subscription.status),
        stripeCustomerId: customerId(subscription.customer)
      };
    }
    case 'customer.subscription.deleted': {
      const subscription = event.data.object as Stripe.Subscription;
      const userId = subscription.metadata?.clerkUserId;
      if (!userId) return null;
      return { userId, premium: false };
    }
    default:
      return null;
  }
}
