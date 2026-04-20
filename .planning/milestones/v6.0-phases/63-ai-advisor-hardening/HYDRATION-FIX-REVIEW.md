# Hydration Fix Review — commit 9276e01

**Status: PASS — no regressions, both fixes are correct.**

## next.config.ts — allowedDevOrigins

Correct fix. Next.js 15 rejects cross-origin dev requests (HMR websocket + client
bundle boot) from any origin not explicitly allowed. Adding `localhost`,
`127.0.0.1`, `0.0.0.0`, and `*.local` covers the common aliases without
widening the surface beyond local development. The `allowedDevOrigins` key is
dev-server-only and has no effect in production builds.

Minor note: `0.0.0.0` as an origin is unusual (browsers do not send it as an
`Origin` header), but it is harmless.

## query-provider.tsx — useState for QueryClient

Correct fix. `getQueryClient()` already implements a module-level singleton
(`browserQueryClient`) on the client, so multiple calls return the same instance.
However, wrapping it in `useState(() => getQueryClient())` is still the right
pattern: it makes the component self-documenting, guards against any future
change to `getQueryClient`, and matches the official TanStack Query Next.js
App Router recommendation. No query state is reset by this change.

## Regressions

None. Server-side rendering path is unaffected (`isServer` guard in
`getQueryClient` returns a fresh client per request as before). The
`allowedDevOrigins` field is stripped from production builds by Next.js.
