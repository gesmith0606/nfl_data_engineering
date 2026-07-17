import { currentUser } from '@clerk/nextjs/server';
import { hasPremiumAccess } from './access';
import { isClerkEnabled } from './flags';

/**
 * Server-side subscription status. This is THE gate premium layouts and
 * route handlers use — never trust client-only checks.
 *
 * Clerk publicMetadata (`premium: true`, stamped by the Stripe webhook) is
 * the single source of truth for premium status; there is no separate DB.
 */
export interface SubscriptionStatus {
  /** Auth + billing wired (Clerk publishable key present). */
  billingEnabled: boolean;
  signedIn: boolean;
  premium: boolean;
  /** Final verdict: may this request see premium surfaces? */
  hasAccess: boolean;
}

export async function getSubscriptionStatus(): Promise<SubscriptionStatus> {
  if (!isClerkEnabled()) {
    // Feature flag off — the site behaves exactly as before auth existed.
    return { billingEnabled: false, signedIn: false, premium: false, hasAccess: true };
  }

  let signedIn = false;
  let premium = false;
  try {
    const user = await currentUser();
    signedIn = Boolean(user);
    premium = user?.publicMetadata?.premium === true;
  } catch {
    // Half-configured Clerk (e.g. publishable key without secret key) must
    // not take pages down — treat the request as signed out.
    signedIn = false;
    premium = false;
  }

  return {
    billingEnabled: true,
    signedIn,
    premium,
    hasAccess: hasPremiumAccess({ clerkEnabled: true, signedIn, premium })
  };
}
