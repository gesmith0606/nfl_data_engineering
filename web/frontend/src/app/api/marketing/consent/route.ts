import { clerkClient, currentUser } from "@clerk/nextjs/server";
import { isClerkEnabled } from "@/lib/billing/flags";

/**
 * POST /api/marketing/consent — record the signed-in user's marketing-email
 * opt-in/out on Clerk `publicMetadata.marketingConsent` (+ `marketingConsentAt`
 * timestamp). Clerk is the user list; this stamp is what keeps emailing it
 * CAN-SPAM/GDPR-clean. Default is opt-out — the caller must explicitly send
 * `consent: true`.
 *
 * Feature-flagged like the rest of billing/auth: 503 when Clerk isn't
 * configured, 401 when signed out. `updateUserMetadata` merges shallowly, so
 * this never touches `publicMetadata.premium`.
 */
export async function POST(req: Request) {
  if (!isClerkEnabled()) {
    return Response.json({ error: "Not configured" }, { status: 503 });
  }

  const user = await currentUser();
  if (!user) {
    return Response.json({ error: "Sign in required" }, { status: 401 });
  }

  const body = (await req.json().catch(() => ({}))) as { consent?: unknown };
  const consent = body.consent === true;

  try {
    const client = await clerkClient();
    await client.users.updateUserMetadata(user.id, {
      publicMetadata: { marketingConsent: consent, marketingConsentAt: new Date().toISOString() },
    });
    return Response.json({ ok: true, consent });
  } catch (error) {
    console.error("[marketing] consent update failed", error);
    return Response.json({ error: "Could not save preference" }, { status: 500 });
  }
}
