import { clerkClient } from '@clerk/nextjs/server';
import type { PremiumUpdate } from './webhook-handlers';

/**
 * Apply a webhook-resolved premium update to Clerk user metadata.
 *
 * `publicMetadata.premium` is the single source of truth for gating;
 * `privateMetadata.stripeCustomerId` powers the customer-portal link.
 * `updateUserMetadata` merges shallowly, so other metadata keys survive.
 */
export async function applyPremiumUpdate(update: PremiumUpdate): Promise<void> {
  const client = await clerkClient();
  await client.users.updateUserMetadata(update.userId, {
    publicMetadata: { premium: update.premium },
    ...(update.stripeCustomerId
      ? { privateMetadata: { stripeCustomerId: update.stripeCustomerId } }
      : {})
  });
}
