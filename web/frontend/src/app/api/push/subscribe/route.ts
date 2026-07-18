/**
 * POST /api/push/subscribe — web-push subscription intake STUB.
 *
 * SCAFFOLDING (v1, delivery lands later): there is no subscription store or
 * push sender yet. Flagged off via env — with `NEXT_PUBLIC_VAPID_PUBLIC_KEY`
 * absent this returns 501 so nothing can pretend push works. When the key is
 * present the payload is validated and acknowledged with 202 but NOT stored;
 * the follow-up phase adds persistence + a sender in the weekly pipeline.
 *
 * Route handlers win over the /api/:path* rewrite to the FastAPI backend
 * (same pattern as /api/version and /api/billing/*).
 */

import { isPushEnabled } from '@/lib/push/flags';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  if (!isPushEnabled()) {
    return Response.json(
      { error: 'Web push is not enabled on this deployment.' },
      { status: 501 }
    );
  }

  let body: { endpoint?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }
  if (typeof body.endpoint !== 'string' || !body.endpoint) {
    return Response.json({ error: 'Missing subscription endpoint.' }, { status: 400 });
  }

  // TODO(push-v2): persist the subscription and wire a sender. Until then the
  // subscription is acknowledged but intentionally dropped.
  return Response.json({ accepted: true, stored: false }, { status: 202 });
}
