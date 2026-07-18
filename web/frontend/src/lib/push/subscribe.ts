/**
 * Web-push subscribe helper — SCAFFOLDING, flagged OFF by default.
 *
 * Nothing calls this yet. When `NEXT_PUBLIC_VAPID_PUBLIC_KEY` lands, an
 * opt-in UI (e.g. inside the alerts sheet) can call `subscribeToPush()` to
 * request permission, subscribe via the already-registered service worker
 * (public/sw.js), and POST the subscription to /api/push/subscribe. Delivery
 * (storing subscriptions + sending pushes from the pipeline) is a later phase.
 *
 * No dependencies added — uses the standard Push API only.
 */

import { getVapidPublicKey, isPushEnabled } from './flags';

/** Decode a base64url VAPID key into the Uint8Array PushManager expects. */
function urlBase64ToUint8Array(base64Url: string): Uint8Array {
  const padding = '='.repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export type PushSubscribeResult =
  | { status: 'subscribed' }
  | { status: 'disabled' | 'unsupported' | 'permission-denied' | 'error'; reason?: string };

/**
 * Request notification permission, subscribe, and register the subscription
 * with the (stub) backend. Safe to call unconditionally — resolves with a
 * status instead of throwing.
 */
export async function subscribeToPush(): Promise<PushSubscribeResult> {
  if (!isPushEnabled()) return { status: 'disabled' };
  if (
    typeof window === 'undefined' ||
    !('serviceWorker' in navigator) ||
    !('PushManager' in window) ||
    !('Notification' in window)
  ) {
    return { status: 'unsupported' };
  }

  try {
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') return { status: 'permission-denied' };

    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(getVapidPublicKey() as string) as BufferSource
    });

    const res = await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription.toJSON())
    });
    if (!res.ok) return { status: 'error', reason: `subscribe endpoint ${res.status}` };
    return { status: 'subscribed' };
  } catch (err) {
    return { status: 'error', reason: err instanceof Error ? err.message : String(err) };
  }
}
