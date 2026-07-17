import { applyPremiumUpdate } from '@/lib/billing/clerk-admin';
import { isStripeEnabled } from '@/lib/billing/flags';
import { getStripeClient } from '@/lib/billing/stripe';
import { resolvePremiumUpdate } from '@/lib/billing/webhook-handlers';

/**
 * POST /api/billing/webhook — Stripe webhook endpoint.
 *
 * Verifies the Stripe signature against STRIPE_WEBHOOK_SECRET, then stamps
 * `premium: true/false` into Clerk publicMetadata (the single source of
 * truth for gating — no separate DB). Handles:
 *   - checkout.session.completed        → premium: true (+ remember customer)
 *   - customer.subscription.updated     → premium follows status active/trialing
 *   - customer.subscription.deleted     → premium: false
 *
 * NOTE: this route must stay exempt from any auth middleware — Stripe calls
 * it unauthenticated; the signature check is the auth.
 */
export async function POST(req: Request) {
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!isStripeEnabled() || !webhookSecret) {
    return Response.json({ error: 'Billing is not configured' }, { status: 503 });
  }

  const signature = req.headers.get('stripe-signature');
  if (!signature) {
    return Response.json({ error: 'Missing stripe-signature header' }, { status: 400 });
  }

  const payload = await req.text();
  let event;
  try {
    event = getStripeClient().webhooks.constructEvent(payload, signature, webhookSecret);
  } catch (error) {
    console.error('[billing] webhook signature verification failed', error);
    return Response.json({ error: 'Invalid signature' }, { status: 400 });
  }

  const update = resolvePremiumUpdate(event);
  if (update) {
    try {
      await applyPremiumUpdate(update);
    } catch (error) {
      // 500 so Stripe retries — metadata update is the whole point.
      console.error('[billing] failed to update Clerk metadata', error);
      return Response.json({ error: 'Metadata update failed' }, { status: 500 });
    }
  }

  return Response.json({ received: true });
}
