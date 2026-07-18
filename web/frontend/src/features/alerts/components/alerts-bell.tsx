'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger
} from '@/components/ui/sheet';
import { Icons } from '@/components/icons';
import { countUnread, type RosterAlert } from '@/lib/alerts/assemble';
import { loadAlertsLastSeen, saveAlertsLastSeen } from '@/lib/alerts/storage';
import { useAlertsBundle } from '../api/queries';
import type { Alert } from '@/lib/nfl/types';

/**
 * Nav bell + roster-scoped alerts sheet.
 *
 * Alerts affecting the user's rostered players (connected Sleeper leagues)
 * surface first, tagged with league names; the rest of the week's alert feed
 * follows as "League news". Unread = alerts with a signal newer than the
 * localStorage last-seen timestamp, cleared when the sheet opens.
 */

const ALERT_TYPE_META: Record<
  Alert['alert_type'],
  { label: string; color: string }
> = {
  ruled_out: { label: 'OUT', color: '#ff7a7a' },
  inactive: { label: 'INACTIVE', color: '#ff7a7a' },
  suspended: { label: 'SUSPENDED', color: '#ffb45e' },
  questionable: { label: 'QUESTIONABLE', color: 'var(--wc-yellow, #ffd84d)' },
  major_negative: { label: 'TRENDING DOWN', color: '#ffb45e' },
  major_positive: { label: 'TRENDING UP', color: 'var(--wc-mint, #91edd0)' }
};

function AlertRow({
  alert,
  leagues,
  badges
}: {
  alert: Alert;
  leagues?: RosterAlert['leagues'];
  badges?: string[];
}) {
  const meta = ALERT_TYPE_META[alert.alert_type] ?? {
    label: alert.alert_type.toUpperCase(),
    color: '#cfd6e4'
  };
  return (
    <li className='border-b border-white/10 px-1 py-3 last:border-b-0'>
      <div className='flex items-baseline justify-between gap-3'>
        <span className='wc-display text-[15px] font-bold tracking-[0.04em] text-white'>
          {alert.player_name}
          {(alert.position || alert.team) && (
            <span className='ml-2 text-[12px] font-semibold tracking-[0.08em] text-[#8b93a7]'>
              {[alert.position, alert.team].filter(Boolean).join(' · ')}
            </span>
          )}
        </span>
        <span
          className='wc-display shrink-0 text-[11px] font-bold tracking-[0.14em]'
          style={{ color: meta.color }}
        >
          {meta.label}
        </span>
      </div>
      {((leagues?.length ?? 0) > 0 || (badges?.length ?? 0) > 0) && (
        <div className='mt-1.5 flex flex-wrap items-center gap-1.5'>
          {leagues?.map((league) => (
            <span
              key={league.leagueId}
              className='rounded-full border border-[rgba(145,237,208,0.35)] px-2 py-0.5 text-[10px] tracking-[0.08em] text-[var(--wc-mint,#91edd0)]'
            >
              {league.leagueName}
            </span>
          ))}
          {badges?.slice(0, 4).map((badge) => (
            <span
              key={badge}
              className='rounded-full border border-white/15 px-2 py-0.5 text-[10px] tracking-[0.08em] text-[#cfd6e4]'
            >
              {badge}
            </span>
          ))}
        </div>
      )}
    </li>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className='wc-display mt-5 mb-1 text-[12px] font-bold tracking-[0.18em] text-[var(--wc-yellow,#ffd84d)] uppercase'>
      {children}
    </h3>
  );
}

export function AlertsBell() {
  const [open, setOpen] = useState(false);
  const [lastSeen, setLastSeen] = useState<string | null>(null);
  // localStorage is read post-mount so SSR and first client render agree.
  const [hydrated, setHydrated] = useState(false);
  const { data, isPending, isError } = useAlertsBundle();

  useEffect(() => {
    setLastSeen(loadAlertsLastSeen());
    setHydrated(true);
  }, []);

  const unread = useMemo(() => {
    if (!hydrated || !data) return 0;
    return countUnread([...data.yourPlayers, ...data.leagueNews], lastSeen);
  }, [hydrated, data, lastSeen]);

  const handleOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) setLastSeen(saveAlertsLastSeen());
  };

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetTrigger
        aria-label={unread > 0 ? `Alerts (${unread} unread)` : 'Alerts'}
        className='relative flex h-9 w-9 items-center justify-center rounded-full text-[#cfd6e4] transition-colors hover:text-[var(--wc-mint,#91edd0)] focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-[var(--wc-mint,#91edd0)]'
      >
        <Icons.notification className='h-[18px] w-[18px]' />
        {unread > 0 && (
          <span
            aria-hidden
            className='wc-display absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--wc-mint,#91edd0)] px-1 text-[10px] font-bold text-[var(--wc-mint-ink,#04140e)]'
          >
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </SheetTrigger>
      <SheetContent
        side='right'
        className='w-full overflow-y-auto border-white/10 bg-[var(--wc-bar,#05070d)] sm:max-w-md'
      >
        <SheetHeader className='border-b-2 border-[var(--wc-mint,#91edd0)]'>
          <SheetTitle className='wc-display tracking-[0.1em] text-white'>
            ALERTS
          </SheetTitle>
          <SheetDescription className='text-[#8b93a7]'>
            {data
              ? `Week ${data.week} · ${data.season} — injury and news signals for your leagues.`
              : 'Injury and news signals for your leagues.'}
          </SheetDescription>
        </SheetHeader>

        <div className='px-4 pb-6'>
          {isPending && (
            <p className='py-6 text-sm text-[#8b93a7]'>Loading alerts…</p>
          )}
          {isError && (
            <p className='py-6 text-sm text-[#8b93a7]'>
              Alerts are unavailable right now. Try again in a bit.
            </p>
          )}

          {data && (
            <>
              <SectionHeading>Your players</SectionHeading>
              {data.leagueCount === 0 ? (
                <p className='py-2 text-sm text-[#8b93a7]'>
                  <Link
                    href='/dashboard/leagues'
                    className='text-[var(--wc-mint,#91edd0)] underline-offset-2 hover:underline'
                    onClick={() => setOpen(false)}
                  >
                    Connect a Sleeper league
                  </Link>{' '}
                  to see alerts scoped to your roster.
                </p>
              ) : data.yourPlayers.length === 0 ? (
                <p className='py-2 text-sm text-[#8b93a7]'>
                  No active alerts for your {data.rosteredCount} rostered players.
                </p>
              ) : (
                <ul>
                  {data.yourPlayers.map((alert) => (
                    <AlertRow
                      key={alert.player_id}
                      alert={alert}
                      leagues={alert.leagues}
                      badges={data.badges[alert.player_id]}
                    />
                  ))}
                </ul>
              )}

              <SectionHeading>League news</SectionHeading>
              {data.leagueNews.length === 0 ? (
                <p className='py-2 text-sm text-[#8b93a7]'>
                  No league-wide alerts this week.
                </p>
              ) : (
                <ul>
                  {data.leagueNews.map((alert) => (
                    <AlertRow key={alert.player_id} alert={alert} />
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
