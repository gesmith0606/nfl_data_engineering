import { clerkMiddleware } from '@clerk/nextjs/server';
import { NextResponse } from 'next/server';

/**
 * Feature-flagged middleware (PLAN 2): when the Clerk publishable key is
 * absent this is the same pass-through the site always had. When keys are
 * present, `clerkMiddleware` provides the session context that server-side
 * premium gating (`getSubscriptionStatus`) and the billing route handlers
 * read via `auth()`/`currentUser()`.
 *
 * Deliberately NO route protection here: premium pages must still render for
 * anonymous users (blurred preview + upgrade CTA — not a redirect or 404),
 * and /api/billing/webhook must stay reachable by Stripe. Enforcement lives
 * server-side in premium layouts and the billing route handlers.
 */
const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

function passthrough() {
  return NextResponse.next();
}

export default clerkEnabled ? clerkMiddleware() : passthrough;

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)'
  ]
};
