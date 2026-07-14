'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Icons } from '@/components/icons';
import { Gx01Head } from '@/components/gx01';
import { getSeasonPhase } from '@/lib/nfl/season-phase';
import { cn } from '@/lib/utils';

/**
 * Mobile bottom tab bar (sketch 002-B/004-C winners) — app shell at phone
 * widths, hidden at md+. GX-01 occupies the raised center puck and toggles
 * the chat widget via the `gx01:toggle` window event (state stays owned by
 * ChatWidget). The 4th slot swaps seasonally per sketch 004-C: Draft during
 * draft-prep/offseason, Scores in-season (trigger = getSeasonPhase).
 */

export function MobileTabbar() {
  const pathname = usePathname();
  const inSeason = getSeasonPhase() === 'in-season';

  const seasonal = inSeason
    ? { href: '/dashboard/predictions', label: 'Scores', icon: Icons.football }
    : { href: '/dashboard/draft', label: 'Draft', icon: Icons.kanban };

  const tabs = [
    { href: '/dashboard', label: 'Home', icon: Icons.dashboard, exact: true },
    { href: '/dashboard/rankings', label: 'Ranks', icon: Icons.chartBar },
    null, // GX-01 center slot
    seasonal,
    { href: '/dashboard/leagues', label: 'League', icon: Icons.teams }
  ] as const;

  return (
    <nav className='wc-tabbar' aria-label='Primary mobile navigation'>
      {tabs.map((tab) => {
        if (tab === null) {
          return (
            <button
              key='gx01'
              type='button'
              className='wc-tab relative'
              onClick={() => window.dispatchEvent(new Event('gx01:toggle'))}
              aria-label='Toggle GX-01 advisor chat'
            >
              <span className='wc-tab-puck'>
                <Gx01Head className='scale-[0.82]' />
              </span>
              <span className='mt-[30px] text-[var(--wc-yellow,#ffd84d)]'>GX-01</span>
            </button>
          );
        }
        const active =
          'exact' in tab && tab.exact
            ? pathname === tab.href
            : pathname.startsWith(tab.href);
        const Icon = tab.icon;
        return (
          <Link key={tab.href} href={tab.href} className={cn('wc-tab', active && 'active')}>
            <Icon className='h-[17px] w-[17px]' />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
