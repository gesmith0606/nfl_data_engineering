# Billing Launch Runbook — GIQ Premium

Step-by-step guide to activate the Clerk + Stripe premium paywall shipped in PR #58
(audited + hardened in the `feat(billing)` launch-readiness PR).

- **Prod frontend**: https://frontend-jet-seven-33.vercel.app (Vercel)
- **Price point**: $7.99/mo, 7-day free trial, cancel anytime
- **Design**: everything is env-flagged. With no keys set, the site is fully open and
  the pricing page shows "Premium subscriptions launch soon". Setting the keys flips
  auth + gating on with zero code changes. Unsetting them rolls everything back.

## How it works (30-second version)

```
Sign-up (Clerk) → /pricing → POST /api/billing/checkout → Stripe Checkout (7-day trial)
    → Stripe webhook (checkout.session.completed) → POST /api/billing/webhook
    → verifies signature → stamps publicMetadata.premium=true on the Clerk user
    → getSubscriptionStatus() reads that stamp server-side → premium surfaces unlock
Cancel via portal → subscription ends → customer.subscription.deleted webhook
    → premium=false → gates re-lock (including /api/chat LLM access)
```

Clerk `publicMetadata.premium` is the single source of truth — there is no database.
`privateMetadata.stripeCustomerId` (also stamped by the webhook) powers the portal link.

Premium surfaces: advisor (`/api/chat` is also gated server-side), leagues, lineups,
draft, full projections + floor/ceiling bands, multi-source compare. Free tier keeps
top-50 projections per position, game predictions, accuracy receipts, and news.

---

## 1. Clerk dashboard setup

1. Create an application at https://dashboard.clerk.com (name: GIQ).
   Enable **Email** (+ Google OAuth recommended) as sign-in methods.
2. You do NOT need Clerk Organizations or Clerk Billing — we use Stripe directly.
   (Ignore `web/frontend/docs/clerk_setup.md`'s billing section; it documents the
   upstream starter template, not our integration.)
3. For production: create a **production instance** (Clerk dev instances use
   `pk_test_`/`sk_test_` keys), add the Vercel domain
   `frontend-jet-seven-33.vercel.app` under **Domains**, and complete DNS/SSL steps
   Clerk shows.
4. Copy from **API Keys**:
   - Publishable key → `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
   - Secret key → `CLERK_SECRET_KEY`

## 2. Stripe dashboard setup

1. Create/activate a Stripe account at https://dashboard.stripe.com.
   Do everything below **in test mode first** (toggle top-right), QA (section 5),
   then repeat in live mode.
2. **Product + price**: Product catalog → Add product:
   - Name: `GIQ Premium`
   - Recurring price: **$7.99 / month**, USD
   - Copy the price id (`price_...`) → `NEXT_PUBLIC_STRIPE_PRICE_ID`
   - Note: the 7-day trial is set by the code at checkout
     (`subscription_data.trial_period_days: 7`) — you do not need to configure a
     trial on the price itself.
3. Recommended subscription settings (Settings → Billing → Subscriptions and emails):
   - "If a trial ends without a payment method" → cancel the subscription
   - Enable failed-payment retries (Smart Retries); after final retry → cancel the
     subscription. Cancellation is what fires `customer.subscription.deleted` and
     revokes premium.
4. **Webhook endpoint**: Developers → Webhooks → Add endpoint:
   - Endpoint URL: `https://frontend-jet-seven-33.vercel.app/api/billing/webhook`
   - Events to send (exactly these three):
     - `checkout.session.completed`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
   - After creating, click **Reveal** on the Signing secret (`whsec_...`) →
     `STRIPE_WEBHOOK_SECRET`
5. Copy from Developers → API keys: Secret key (`sk_...`) → `STRIPE_SECRET_KEY`.
   (The Stripe publishable key is NOT needed — we only use redirect Checkout/Portal.)
6. **Customer portal**: Settings → Billing → Customer portal → activate it and allow
   customers to cancel subscriptions (portal returns users to `/pricing`).

## 3. Vercel environment variables

Set on the frontend project (Production environment; add to Preview only if you want
to test there — Preview would need its own Stripe webhook endpoint URL):

| Variable | Value | NEXT_PUBLIC? | Notes |
|---|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_live_...` | yes (build-time inline) | Master flag — presence turns on auth + gating |
| `CLERK_SECRET_KEY` | `sk_live_...` (Clerk) | no | Server-side Clerk API |
| `STRIPE_SECRET_KEY` | `sk_live_...` (Stripe) | no | Presence turns on checkout/portal/webhook |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | no | Webhook signature verification |
| `NEXT_PUBLIC_STRIPE_PRICE_ID` | `price_...` | yes | The $7.99/mo price |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | `/auth/sign-in` | yes | Our sign-in lives at a non-default path |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | `/auth/sign-up` | yes | Ditto for sign-up |

Then **redeploy** — `NEXT_PUBLIC_*` vars are inlined at build time, so a new build is
required for them to take effect (a plain "Redeploy" of the latest build is enough).

## 4. Launch order

1. Test-mode QA passes (section 5) on a Preview deployment or locally.
2. Create the live-mode product, price, and webhook endpoint (section 2, live mode).
3. Set the 7 env vars in Vercel Production with **live** keys → redeploy.
4. Smoke-check prod (section 5, steps 1–4) with a real card, then immediately cancel
   in the portal (trial = $0 charged).
5. Watch Stripe Developers → Webhooks → endpoint → "Events" for delivery failures the
   first day. Any non-2xx response means premium stamps are not landing.

## 5. Manual QA checklist (Stripe test mode)

Use card `4242 4242 4242 4242`, any future expiry, any CVC/ZIP.

- [ ] **Flag off baseline**: with no env vars set, site fully open, pricing page says
      "launch soon", `/auth/sign-in` redirects home, `/api/billing/*` return 503.
- [ ] **Flag on, anonymous**: advisor/leagues/lineups/draft show the blurred upsell
      (never a 404); projections capped at top-50 per position, no floor/ceiling
      columns; rankings "Compare Sources" tab locked; `POST /api/chat` returns 403.
- [ ] **Sign-up**: create account at `/auth/sign-up` → still gated (signed in ≠ premium).
- [ ] **Checkout**: `/pricing` → "Start 7-day free trial" → Stripe Checkout shows
      $7.99/mo with 7-day trial → pay with test card → redirected to
      `/dashboard?upgraded=1`.
- [ ] **Webhook fired**: Stripe → Webhooks → endpoint shows `checkout.session.completed`
      delivered with 200. Clerk → user → Metadata shows `publicMetadata.premium: true`
      and `privateMetadata.stripeCustomerId`.
- [ ] **Unlock**: all premium surfaces render real content; full projections with
      bands; multi-compare loads; advisor chat streams.
- [ ] **Double-subscribe guard**: `curl -X POST .../api/billing/checkout` with the
      premium session cookie returns 409 (or observe the pricing page now shows
      "Manage subscription" instead of the checkout button).
- [ ] **Portal + cancel**: `/pricing` → "Manage subscription" → Stripe portal →
      cancel. For an immediate test, cancel the subscription from the Stripe
      dashboard instead ("Cancel immediately") to fire
      `customer.subscription.deleted` right away.
- [ ] **Revoked**: webhook delivered 200; Clerk metadata `premium: false`; premium
      pages show the upsell again; `POST /api/chat` returns 403 again.
- [ ] **Payment-failure path** (optional): in Stripe dashboard, on a test-clock or by
      updating the sub to a failing card (`4000 0000 0000 0341`), verify a
      `past_due`/`canceled` status via `customer.subscription.updated` revokes premium.
- [ ] **Forged webhook**: `curl -X POST .../api/billing/webhook -H 'stripe-signature: t=1,v1=bad' -d '{}'`
      returns 400.

## 6. Rollback

Billing misbehaving in prod? Unset in Vercel and redeploy:

1. Remove `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` → **full rollback**: auth unmounts,
   every gate opens (site behaves exactly as pre-billing), billing routes go 503.
   This is the one variable that controls the paywall.
2. Removing only `STRIPE_SECRET_KEY` / `NEXT_PUBLIC_STRIPE_PRICE_ID` keeps auth on
   but disables new checkouts/portal (pricing page reverts to "launch soon").
   Existing premium stamps in Clerk keep working.
3. Remember to **pause or delete the Stripe webhook endpoint** if rolling back for a
   long period (otherwise Stripe disables it after days of 503s and you must
   re-enable + get a new secret when relaunching).
4. Active subscribers are unaffected by a rollback (everything becomes free); to stop
   billing them you must cancel subscriptions in the Stripe dashboard.

## 7. Known launch notes

- **Repeat trials**: a customer who cancels and re-subscribes gets a fresh 7-day
  trial (checkout always sets `trial_period_days: 7`). Acceptable at launch;
  revisit if abused.
- **Webhook retries**: the endpoint returns 500 when the Clerk metadata write fails,
  so Stripe retries with backoff. Updates are idempotent (same stamp re-applied).
- **Free-tier cap is presentational**: the FastAPI backend
  (gesmith0606-nfl-data-api.hf.space) is public, so the top-50 cap and band-hiding
  happen in the frontend. Gating real premium *compute* (`/api/chat` LLM calls) is
  enforced server-side. Locking down the FastAPI data itself is future work.
- **`/api/billing/webhook` must stay middleware-exempt** — `proxy.ts` deliberately
  adds no route protection; the Stripe signature is the auth.
