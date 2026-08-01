# Web Push (push-v2) — status and activation steps

**Status (2026-08-01): honestly OFF.** The PWA + roster-alerts UI shipped in
PR #61, but delivery is a deliberate stub: with `NEXT_PUBLIC_VAPID_PUBLIC_KEY`
unset, the client never prompts and `POST /api/push/subscribe` returns 501
(`web/frontend/src/app/api/push/subscribe/route.ts`, flags in
`src/lib/push/flags.ts`). Nothing pretends push works — in-app alerts
(alerts bell) are unaffected.

## Why this is parked (not a code gap first)

Real delivery needs two pieces of infrastructure only the operator can
provision — writing the sender code before these exist would be untestable:

1. **A subscription store.** Vercel serverless has no disk; the HF Space is
   rebuilt daily (ephemeral); the git repo is public (push endpoints embed
   capability secrets — must NOT be committed). Cheapest fits: Vercel KV /
   Upstash Redis free tier, or Supabase free tier.
2. **VAPID keys + env vars.** `npx web-push generate-vapid-keys`, then set
   `NEXT_PUBLIC_VAPID_PUBLIC_KEY` + `VAPID_PRIVATE_KEY` (Vercel env), plus the
   store credentials (e.g. `KV_REST_API_URL` / `KV_REST_API_TOKEN`).

## Activation checklist (operator)

- [ ] Provision the store (Upstash/Vercel KV) — copy REST URL + token
- [ ] `npx web-push generate-vapid-keys`
- [ ] Add the 4 env vars to Vercel (prod + preview)
- [ ] Add `KV_*` + `VAPID_*` as GitHub Actions secrets (sender runs in the
      data workflows after Gold refresh)
- [ ] Then ask for the push-v2 implementation pass: persist subscriptions in
      the store, sender step in daily-sentiment/sunday-refresh (web-push npm
      pkg or pywebpush), prune dead subscriptions on 404/410 responses

Until the boxes are checked, the stub is the correct state.
