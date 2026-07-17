import type { Metadata } from 'next';
import Link from 'next/link';
import { Icons } from '@/components/icons';
import {
  CheckoutButton,
  ManageSubscriptionButton
} from '@/features/billing/components/billing-buttons';
import { isClerkEnabled, isStripeEnabled } from '@/lib/billing/flags';
import { getSubscriptionStatus } from '@/lib/billing/subscription';

export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Pricing',
  description:
    'GIQ Premium — full projections with floor/ceiling bands, AI advisor, league sync, lineup builder, and draft tools. Free tier includes top-50 projections, game predictions, and the accuracy receipts.'
};

/**
 * Pricing — broadcast design language (sketch 001-B): near-black panels,
 * mint rule, wc-display type, yellow kicker, periwinkle CTA. $7.99/mo with a
 * 7-day trial is placeholder copy; the actual charge comes from the Stripe
 * Price behind NEXT_PUBLIC_STRIPE_PRICE_ID.
 */
const FREE_FEATURES = [
  'Top-50 projections per position',
  'Game predictions vs the Vegas line',
  'Model accuracy receipts — misses included',
  'News & sentiment feed'
];

const PREMIUM_FEATURES = [
  'Full projections + floor/ceiling bands',
  'GX-01 AI advisor — start/sit, trades, matchups',
  'League sync — your roster, your scoring',
  'Lineup builder with optimal allocation',
  'Draft tools — ADP, VORP, live co-pilot',
  'Custom-scoring re-ranks',
  'Multi-source compare (ESPN / Sleeper / Yahoo / DS / FTN)'
];

function FeatureList({ items, accent }: { items: string[]; accent?: boolean }) {
  return (
    <ul className='space-y-3'>
      {items.map((item) => (
        <li key={item} className='flex items-start gap-2.5 text-sm leading-relaxed'>
          <Icons.check
            className={
              accent
                ? 'mt-0.5 h-4 w-4 shrink-0 text-[var(--wc-mint,#91edd0)]'
                : 'mt-0.5 h-4 w-4 shrink-0 text-[#9aa3b8]'
            }
          />
          <span className={accent ? 'text-[#e6eaf2]' : 'text-[#9aa3b8]'}>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export default async function PricingPage() {
  const status = await getSubscriptionStatus();
  const billingLive = isClerkEnabled() && isStripeEnabled();

  return (
    <div className='min-h-screen bg-[var(--wc-stadium,#070a12)] text-white'>
      {/* Broadcast nav — same near-black bar + mint rule as the marketing home. */}
      <nav className='sticky top-0 z-50 flex h-[52px] items-center gap-6 border-b-2 border-[var(--wc-mint,#91edd0)] bg-[var(--wc-bar,#05070d)] px-4 md:px-7'>
        <Link
          href='/'
          className='wc-display mr-3 whitespace-nowrap text-2xl font-extrabold tracking-[0.14em] text-white'
        >
          G<span className='text-[var(--wc-mint,#91edd0)]'>IQ</span>
        </Link>
        <span className='flex-1' />
        <Link
          href='/dashboard'
          className='wc-display whitespace-nowrap rounded-full bg-[var(--wc-peri,#5b67c7)] px-4 py-1 text-[13px] tracking-[0.1em] text-white transition-colors hover:bg-[var(--wc-peri-bright,#6e7ce0)]'
        >
          Open App
        </Link>
      </nav>

      <main className='mx-auto max-w-5xl px-5 py-16 md:py-24'>
        <div className='text-center'>
          <div className='wc-display mb-3 text-sm tracking-[0.2em] text-[var(--wc-yellow,#ffd84d)]'>
            PRICING
          </div>
          <h1 className='wc-display text-[clamp(32px,4.5vw,56px)] font-extrabold leading-[1.08] tracking-[0.03em]'>
            The model that beats the consensus.
            <br />
            <span className='text-[var(--wc-yellow,#ffd84d)]'>Now in your lineup.</span>
          </h1>
          <p className='mx-auto mt-4 max-w-[600px] text-lg leading-relaxed text-[#9aa3b8]'>
            The receipts stay free. Premium unlocks the tools that turn them into wins — your
            league, your scoring, every week.
          </p>
        </div>

        <div className='mt-14 grid gap-6 md:grid-cols-2'>
          {/* Free tier */}
          <section className='rounded-xl border border-white/10 bg-[var(--wc-bar-hi,#131722)] p-7'>
            <h2 className='wc-display text-xl font-extrabold tracking-[0.08em]'>FREE</h2>
            <div className='mt-3 flex items-baseline gap-1'>
              <span className='wc-display text-4xl font-extrabold'>$0</span>
              <span className='text-sm text-[#9aa3b8]'>/ forever</span>
            </div>
            <p className='mt-2 text-sm text-[#9aa3b8]'>Proof of model quality, on the house.</p>
            <div className='my-6 h-px bg-white/10' />
            <FeatureList items={FREE_FEATURES} />
            <Link
              href='/dashboard'
              className='wc-display mt-8 inline-flex w-full items-center justify-center rounded-full border border-white/20 px-6 py-2.5 text-[14px] tracking-[0.1em] text-[#cfd6e4] transition-colors hover:border-[var(--wc-mint,#91edd0)] hover:text-[var(--wc-mint,#91edd0)]'
            >
              Open the app
            </Link>
          </section>

          {/* Premium tier */}
          <section className='relative overflow-hidden rounded-xl border border-[var(--wc-mint,#91edd0)]/50 bg-[var(--wc-bar-hi,#131722)] p-7'>
            <div className='absolute inset-x-0 top-0 h-[3px] bg-[var(--wc-rail-x,linear-gradient(90deg,#91edd0,#91edd0))]' />
            <div className='flex items-center justify-between'>
              <h2 className='wc-display text-xl font-extrabold tracking-[0.08em] text-[var(--wc-mint,#91edd0)]'>
                PREMIUM
              </h2>
              <span className='wc-display rounded-full bg-[rgba(255,216,77,0.12)] px-3 py-1 text-[11px] tracking-[0.16em] text-[var(--wc-yellow,#ffd84d)]'>
                7-DAY FREE TRIAL
              </span>
            </div>
            <div className='mt-3 flex items-baseline gap-1'>
              <span className='wc-display text-4xl font-extrabold'>$7.99</span>
              <span className='text-sm text-[#9aa3b8]'>/ month · cancel anytime</span>
            </div>
            <p className='mt-2 text-sm text-[#9aa3b8]'>
              Everything in Free, plus the full toolkit.
            </p>
            <div className='my-6 h-px bg-white/10' />
            <FeatureList items={PREMIUM_FEATURES} accent />
            <div className='mt-8'>
              {!billingLive ? (
                <div className='rounded-lg border border-white/10 bg-[rgba(255,255,255,0.03)] px-4 py-3 text-center text-sm text-[#9aa3b8]'>
                  Premium subscriptions launch soon — everything is free while we finish
                  wiring billing.
                </div>
              ) : status.premium ? (
                <div className='space-y-3 text-center'>
                  <div className='wc-display text-sm tracking-[0.12em] text-[var(--wc-mint,#91edd0)]'>
                    YOU&apos;RE PREMIUM ✓
                  </div>
                  <ManageSubscriptionButton className='w-full' />
                </div>
              ) : (
                <CheckoutButton className='w-full' />
              )}
            </div>
          </section>
        </div>

        <p className='mt-10 text-center text-xs text-[#5b6577]'>
          Payments processed by Stripe. Subscriptions renew monthly and can be cancelled any
          time from the billing portal.
        </p>
      </main>
    </div>
  );
}
