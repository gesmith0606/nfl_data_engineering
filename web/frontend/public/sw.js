/**
 * GIQ service worker — minimal, navigation-only.
 *
 * Strategy: network-first for page navigations with an offline fallback.
 * API responses (/api/*) and static assets are deliberately NOT cached —
 * projections, alerts, and odds must never be served stale from a SW cache
 * (Next.js already fingerprints/immutable-caches its own static assets).
 *
 * Bump CACHE_VERSION when offline.html or the precache list changes.
 */
const CACHE_VERSION = 'giq-v1';
const OFFLINE_URL = '/offline.html';
const PRECACHE = [OFFLINE_URL, '/icons/icon-192.png', '/icons/icon-512.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_VERSION)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Navigations only — never intercept API calls, RSC fetches, or assets.
  if (request.mode !== 'navigate' || request.method !== 'GET') return;

  event.respondWith(
    fetch(request).catch(async () => {
      const cached = await caches.match(OFFLINE_URL);
      return cached || Response.error();
    })
  );
});

// Web-push scaffolding (flagged OFF — see src/lib/push/flags.ts). Delivery
// lands later; these handlers are inert until a push server exists and
// NEXT_PUBLIC_VAPID_PUBLIC_KEY is set.
self.addEventListener('push', (event) => {
  if (!event.data) return;
  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: 'GIQ', body: event.data.text() };
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || 'GIQ', {
      body: payload.body || '',
      icon: '/icons/icon-192.png',
      data: { url: payload.url || '/dashboard' }
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/dashboard';
  event.waitUntil(self.clients.openWindow(url));
});
