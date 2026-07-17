/**
 * Billing feature flags — everything auth/payments is gated on env presence.
 *
 * Design constraint (PLAN 2): the Clerk app and Stripe account may not exist
 * yet. When `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is absent the site must render
 * exactly as it does today — no auth, everything accessible, build green.
 * Setting the key activates auth + premium gating with zero code changes.
 *
 * `NEXT_PUBLIC_*` vars are inlined at build time, so these helpers are safe
 * in both server and client components.
 */

/** Clerk auth is active when the publishable key is present. */
export function isClerkEnabled(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
}

/** Stripe checkout/portal/webhook are active when the secret key is present. */
export function isStripeEnabled(): boolean {
  return Boolean(process.env.STRIPE_SECRET_KEY);
}

/** The Stripe Price the premium subscription checks out against. */
export function getStripePriceId(): string | undefined {
  return process.env.NEXT_PUBLIC_STRIPE_PRICE_ID || undefined;
}
