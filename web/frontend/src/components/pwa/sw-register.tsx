'use client';

import { useEffect } from 'react';

/**
 * Registers the navigation-only service worker (public/sw.js).
 *
 * Production-only: a SW in dev intercepts HMR navigations and serves the
 * offline fallback on every recompile, so registration is skipped there.
 * Renders nothing — mounted once in the root layout.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') return;
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch((err) => {
      // Non-fatal: the site works identically without the SW.
      console.warn('[pwa] service worker registration failed', err);
    });
  }, []);

  return null;
}
