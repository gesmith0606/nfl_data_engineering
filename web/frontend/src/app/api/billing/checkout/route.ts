import { currentUser } from '@clerk/nextjs/server';
import { getStripePriceId, isClerkEnabled, isStripeEnabled } from '@/lib/billing/flags';
import { getStripeClient } from '@/lib/billing/stripe';

/**
 * POST /api/billing/checkout — create a Stripe subscription Checkout Session
 * for the signed-in Clerk user. Returns { url } to redirect the browser to.
 *
 * Feature-flagged: 503 when Clerk/Stripe env is absent, so the route is inert
 * until George creates the accounts and sets the keys.
 */
export async function POST(req: Request) {
  if (!isClerkEnabled() || !isStripeEnabled() || !getStripePriceId()) {
    return Response.json({ error: 'Billing is not configured' }, { status: 503 });
  }

  const user = await currentUser();
  if (!user) {
    return Response.json({ error: 'Sign in to upgrade' }, { status: 401 });
  }

  const origin = new URL(req.url).origin;
  const existingCustomerId = user.privateMetadata?.stripeCustomerId;
  const email = user.emailAddresses.find(
    (address) => address.id === user.primaryEmailAddressId
  )?.emailAddress;

  try {
    const session = await getStripeClient().checkout.sessions.create({
      mode: 'subscription',
      line_items: [{ price: getStripePriceId(), quantity: 1 }],
      client_reference_id: user.id,
      metadata: { clerkUserId: user.id },
      subscription_data: {
        trial_period_days: 7,
        metadata: { clerkUserId: user.id }
      },
      allow_promotion_codes: true,
      ...(typeof existingCustomerId === 'string'
        ? { customer: existingCustomerId }
        : email
          ? { customer_email: email }
          : {}),
      success_url: `${origin}/dashboard?upgraded=1`,
      cancel_url: `${origin}/pricing`
    });
    return Response.json({ url: session.url });
  } catch (error) {
    console.error('[billing] checkout session failed', error);
    return Response.json({ error: 'Could not start checkout' }, { status: 500 });
  }
}
