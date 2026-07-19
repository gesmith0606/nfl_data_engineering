'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useKBar } from 'kbar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { Icons } from '@/components/icons';
import { AlertsBell } from '@/features/alerts/components/alerts-bell';
import { NavAuth } from '@/features/billing/components/nav-auth';
import { cn } from '@/lib/utils';

/**
 * Broadcast top nav — the site-wide shell (sketches 001-B/003/005). The same
 * near-black bar with the 2px mint rule that fronts the marketing home now
 * frames every app page: GIQ brand → /, the six-item broadcast IA, a More
 * menu for secondary surfaces, and a ⌘K search trigger. Below md the links
 * hide — the mobile tab bar owns navigation there.
 */

const PRIMARY = [
  { label: 'News', href: '/dashboard/news' },
  { label: 'Rankings', href: '/dashboard/rankings' },
  { label: 'Scores', href: '/dashboard/predictions' },
  { label: 'Matchups', href: '/dashboard/matchups' },
  { label: 'My League', href: '/dashboard/leagues' },
  { label: 'Draft Room', href: '/dashboard/draft' }
] as const;

const MORE = [
  { label: 'Home Hub', href: '/dashboard' },
  { label: 'Projections', href: '/dashboard/projections' },
  { label: 'Players', href: '/dashboard/players' },
  { label: 'Lineups', href: '/dashboard/lineups' },
  { label: 'Game Results', href: '/dashboard/games' },
  { label: 'Model Accuracy', href: '/dashboard/accuracy' },
  { label: 'AI Advisor', href: '/dashboard/advisor' }
] as const;

function SearchButton() {
  const { query } = useKBar();
  return (
    <button
      type='button'
      onClick={() => query.toggle()}
      aria-label='Search (⌘K)'
      className='flex h-9 w-9 items-center justify-center rounded-full text-[#cfd6e4] transition-colors hover:text-[var(--wc-mint,#91edd0)] focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-[var(--wc-mint,#91edd0)]'
    >
      <Icons.search className='h-[18px] w-[18px]' />
    </button>
  );
}

export function BroadcastNav() {
  const pathname = usePathname();
  const moreActive = MORE.some((item) =>
    item.href === '/dashboard' ? pathname === '/dashboard' : pathname.startsWith(item.href)
  );

  return (
    <nav
      className='sticky top-0 z-50 flex h-[52px] items-center gap-6 border-b-2 border-[var(--wc-mint,#91edd0)] bg-[var(--wc-bar,#05070d)] px-4 md:px-7'
      aria-label='Primary navigation'
    >
      <Link
        href='/'
        className='wc-display mr-1 whitespace-nowrap text-2xl font-extrabold tracking-[0.14em] text-white md:mr-3'
      >
        G<span className='text-[var(--wc-mint,#91edd0)]'>IQ</span>
      </Link>

      <div className='hidden items-center gap-6 overflow-x-auto md:flex'>
        {PRIMARY.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'wc-display whitespace-nowrap text-[15px] tracking-[0.1em] transition-colors',
                active
                  ? 'text-[var(--wc-mint,#91edd0)]'
                  : 'text-[#cfd6e4] hover:text-[var(--wc-mint,#91edd0)]'
              )}
              aria-current={active ? 'page' : undefined}
            >
              {item.label}
            </Link>
          );
        })}

        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(
              'wc-display flex items-center gap-1 whitespace-nowrap text-[15px] tracking-[0.1em] transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-[var(--wc-mint,#91edd0)]',
              moreActive
                ? 'text-[var(--wc-mint,#91edd0)]'
                : 'text-[#cfd6e4] hover:text-[var(--wc-mint,#91edd0)]'
            )}
          >
            More
            <Icons.chevronDown className='h-3.5 w-3.5' />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align='start'
            className='border-white/10 bg-[var(--wc-bar,#05070d)]'
          >
            {MORE.map((item) => (
              <DropdownMenuItem key={item.href} asChild>
                <Link
                  href={item.href}
                  className='wc-display cursor-pointer text-[14px] tracking-[0.08em] text-[#cfd6e4] focus:bg-[rgba(145,237,208,0.1)] focus:text-[var(--wc-mint,#91edd0)]'
                >
                  {item.label}
                </Link>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <span className='flex-1' />
      <NavAuth />
      <AlertsBell />
      <SearchButton />
    </nav>
  );
}
