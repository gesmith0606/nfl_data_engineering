/**
 * Web-push feature flags — mirrors the env-presence gating of
 * `src/lib/billing/flags.ts` (isClerkEnabled).
 *
 * SCAFFOLDING ONLY (v1): there is no push server yet. Setting
 * `NEXT_PUBLIC_VAPID_PUBLIC_KEY` activates the client subscribe path and the
 * /api/push/subscribe stub, but delivery lands in a later phase (needs a
 * VAPID key pair, a subscription store, and a sender in the weekly pipeline).
 * With the key absent the site is byte-identical to today: no permission
 * prompts, no subscribe calls, route returns 501.
 *
 * `NEXT_PUBLIC_*` vars are inlined at build time, so these helpers are safe
 * in both server and client components.
 */

/** Web-push subscribe flow is active when the VAPID public key is present. */
export function isPushEnabled(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY);
}

/** The application server key browsers subscribe against. */
export function getVapidPublicKey(): string | undefined {
  return process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY || undefined;
}
