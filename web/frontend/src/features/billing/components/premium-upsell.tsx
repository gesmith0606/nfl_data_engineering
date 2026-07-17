import Link from 'next/link';
import { Icons } from '@/components/icons';
import { PREMIUM_SURFACES, type PremiumSurface } from '@/lib/billing/access';
import { cn } from '@/lib/utils';

export type { PremiumSurface };

/**
 * Free-tier view of a premium surface — a blurred decorative preview with an
 * upgrade CTA (conversion pattern), never a 404. IMPORTANT: the preview rows
 * are fake/decorative; no premium data is rendered or sent to the client.
 *
 * Broadcast design language: near-black panel, mint rule, wc-display type,
 * yellow kicker, periwinkle CTA (sketches 001-B/003/005).
 */
const PREVIEW_ROWS = [
  ['1', 'J. ████████', 'KC', '24.6', '18.1 – 31.2'],
  ['2', 'L. ██████', 'BAL', '23.8', '17.4 – 30.5'],
  ['3', 'J. ██████', 'BUF', '23.1', '16.8 – 29.7'],
  ['4', 'C. ████████', 'PHI', '21.9', '15.9 – 28.4'],
  ['5', 'B. ██████', 'CIN', '21.2', '15.2 – 27.6']
] as const;

export function PremiumUpsell({
  surface,
  signedIn,
  className
}: {
  surface: PremiumSurface;
  signedIn: boolean;
  className?: string;
}) {
  const copy = PREMIUM_SURFACES[surface];

  return (
    <section
      className={cn(
        'relative overflow-hidden rounded-xl border border-white/10 bg-[var(--wc-bar-hi,#131722)]',
        className
      )}
      aria-label={`${copy.title} — premium feature`}
    >
      {/* Decorative blurred preview — fake rows, no real data. */}
      <div aria-hidden='true' className='pointer-events-none select-none blur-[6px]'>
        <div className='border-b-2 border-[var(--wc-mint,#91edd0)] px-5 py-3'>
          <span className='wc-display text-sm tracking-[0.2em] text-[#cfd6e4]'>
            {copy.title.toUpperCase()}
          </span>
        </div>
        <table className='w-full text-left text-sm text-[#9aa3b8]'>
          <tbody>
            {PREVIEW_ROWS.map((row) => (
              <tr key={row[0]} className='border-b border-white/5'>
                {row.map((cell, i) => (
                  <td key={i} className='px-5 py-3 whitespace-nowrap'>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Overlay CTA */}
      <div className='absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[rgba(5,7,13,0.72)] px-6 text-center'>
        <span className='flex h-10 w-10 items-center justify-center rounded-full border border-[var(--wc-yellow,#ffd84d)]/40 bg-[rgba(255,216,77,0.08)]'>
          <Icons.lock className='h-5 w-5 text-[var(--wc-yellow,#ffd84d)]' />
        </span>
        <div className='wc-display text-xs tracking-[0.2em] text-[var(--wc-yellow,#ffd84d)]'>
          PREMIUM
        </div>
        <h3 className='wc-display text-2xl font-extrabold tracking-[0.04em] text-white'>
          {copy.title}
        </h3>
        <p className='max-w-[460px] text-sm leading-relaxed text-[#cfd6e4]'>{copy.description}</p>
        <div className='mt-2 flex flex-wrap items-center justify-center gap-3'>
          <Link
            href='/pricing'
            className='wc-display rounded-full bg-[var(--wc-peri,#5b67c7)] px-5 py-2 text-[13px] tracking-[0.1em] text-white transition-colors hover:bg-[var(--wc-peri-bright,#6e7ce0)]'
          >
            Go Premium — $7.99/mo
          </Link>
          {!signedIn && (
            <Link
              href='/auth/sign-in'
              className='wc-display rounded-full border border-white/20 px-5 py-2 text-[13px] tracking-[0.1em] text-[#cfd6e4] transition-colors hover:border-[var(--wc-mint,#91edd0)] hover:text-[var(--wc-mint,#91edd0)]'
            >
              Sign in
            </Link>
          )}
        </div>
        <p className='text-xs text-[#9aa3b8]'>7-day free trial · cancel anytime</p>
      </div>
    </section>
  );
}
