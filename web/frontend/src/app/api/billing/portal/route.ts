import { currentUser } from '@clerk/nextjs/server';
import { isClerkEnabled, isStripeEnabled } from '@/lib/billing/flags';
import { getStripeClient } from '@/lib/billing/stripe';

/**
 * POST /api/billing/portal — create a Stripe customer-portal session for the
 * signed-in user (manage/cancel subscription). Returns { url }.
 */
export async function POST(req: Request) {
  if (!isClerkEnabled() || !isStripeEnabled()) {
    return Response.json({ error: 'Billing is not configured' }, { status: 503 });
  }

  const user = await currentUser();
  if (!user) {
    return Response.json({ error: 'Sign in first' }, { status: 401 });
  }

  const customerId = user.privateMetadata?.stripeCustomerId;
  if (typeof customerId !== 'string' || !customerId) {
    return Response.json({ error: 'No subscription on file' }, { status: 404 });
  }

  const origin = new URL(req.url).origin;
  try {
    const session = await getStripeClient().billingPortal.sessions.create({
      customer: customerId,
      return_url: `${origin}/pricing`
    });
    return Response.json({ url: session.url });
  } catch (error) {
    console.error('[billing] portal session failed', error);
    return Response.json({ error: 'Could not open billing portal' }, { status: 500 });
  }
}
