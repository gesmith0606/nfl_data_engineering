import Stripe from 'stripe';

/**
 * Lazy Stripe client — instantiated only when STRIPE_SECRET_KEY is present,
 * so builds and deployments without Stripe configured never touch the SDK.
 */
let cachedClient: Stripe | null = null;

export function getStripeClient(): Stripe {
  const secretKey = process.env.STRIPE_SECRET_KEY;
  if (!secretKey) {
    throw new Error('STRIPE_SECRET_KEY is not set — billing is disabled');
  }
  if (!cachedClient) {
    cachedClient = new Stripe(secretKey);
  }
  return cachedClient;
}
