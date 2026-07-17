/**
 * Pure premium-access logic — no Clerk/Stripe imports so it is unit-testable
 * and shared by server components, route handlers, and tests.
 */

export interface AccessContext {
  /** Is auth wired at all (NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY present)? */
  clerkEnabled: boolean;
  /** Is there a signed-in Clerk user? */
  signedIn: boolean;
  /** Does the user's Clerk publicMetadata carry `premium: true`? */
  premium: boolean;
}

/**
 * Decide whether premium surfaces are accessible.
 *
 * Keys absent → everything is open (the site behaves exactly as before auth
 * existed). Keys present → only signed-in users with `premium: true` in
 * Clerk publicMetadata get premium surfaces.
 */
export function hasPremiumAccess(ctx: AccessContext): boolean {
  if (!ctx.clerkEnabled) return true;
  return ctx.signedIn && ctx.premium;
}

/** Subscription statuses that count as an active premium subscription. */
export const PREMIUM_SUBSCRIPTION_STATUSES = new Set(['active', 'trialing']);

/** Premium surfaces and their upsell copy (single source of truth). */
export const PREMIUM_SURFACES = {
  advisor: {
    title: 'AI Advisor',
    description:
      'Start/sit calls, trade takes, and matchup answers from GX-01 — grounded in our projections, not vibes.'
  },
  leagues: {
    title: 'League Sync',
    description:
      'Connect your Sleeper league: your roster, your scoring, who to start and who to drop this week.'
  },
  lineups: {
    title: 'Lineup Builder',
    description:
      'Field-view optimal lineups with projected points at every slot — built from the same model that beats the consensus.'
  },
  draft: {
    title: 'Draft Tools',
    description:
      'Live draft board with ADP, VORP, tier breaks, and pick-by-pick recommendations.'
  },
  'multi-compare': {
    title: 'Multi-Source Compare',
    description:
      'Our projections side-by-side with ESPN, Sleeper, Yahoo, Draft Sharks, and FTN — with the deltas that matter.'
  },
  projections: {
    title: 'Full Projections',
    description:
      'Every ranked player with floor/ceiling bands — the free tier shows the top 50 per position.'
  }
} as const;

export type PremiumSurface = keyof typeof PREMIUM_SURFACES;
