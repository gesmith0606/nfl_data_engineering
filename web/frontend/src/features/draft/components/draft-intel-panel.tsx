'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Icons } from '@/components/icons';
import { Skeleton } from '@/components/ui/skeleton';
import { draftIntelQueryOptions } from '@/features/nfl/api/queries';
import { WC_PANEL_SURFACE, WC_HEADING } from '../utils/broadcast-ui';

interface DraftIntelPanelProps {
  leagueId: string | null;
}

/**
 * "Opponent Intel" — per-manager tendencies from league history (GET
 * /api/draft/intel, a parallel backend lane that may 404). Purely additive:
 * never blocks the live-draft flow, and explains itself when there's no
 * league history to draw on.
 */
export function DraftIntelPanel({ leagueId }: DraftIntelPanelProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError } = useQuery(draftIntelQueryOptions(leagueId));

  if (!leagueId) return null;

  const managers = isError ? [] : (data?.managers ?? []);

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={`rounded-md border p-[var(--space-3)] ${WC_PANEL_SURFACE}`}
    >
      <CollapsibleTrigger asChild>
        <button type='button' className='flex w-full items-center gap-[var(--space-2)] text-left'>
          {open ? (
            <Icons.chevronDown className='h-[var(--space-4)] w-[var(--space-4)] text-[var(--wc-mint,#91edd0)]' />
          ) : (
            <Icons.chevronRight className='h-[var(--space-4)] w-[var(--space-4)] text-[var(--wc-mint,#91edd0)]' />
          )}
          <Icons.teams className='h-[var(--space-4)] w-[var(--space-4)]' />
          <h3 className={`${WC_HEADING} text-[length:var(--fs-sm)] leading-[var(--lh-sm)]`}>
            Opponent Intel
          </h3>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className='mt-[var(--space-3)]'>
        {isLoading ? (
          <div className='space-y-[var(--space-3)]'>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className='space-y-1'>
                <Skeleton className='h-[var(--space-4)] w-1/2' />
                <Skeleton className='h-[var(--space-3)] w-full' />
              </div>
            ))}
          </div>
        ) : managers.length === 0 ? (
          <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            Needs league draft history to build tendencies — check back once your connected league
            has completed at least one draft.
          </p>
        ) : (
          <div className='space-y-[var(--space-3)]'>
            {managers.map((m) => (
              <div key={m.user_id} className='space-y-1'>
                <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                  {m.display_name}
                  {m.team_name ? ` · ${m.team_name}` : ''}
                </p>
                <ul className='list-inside list-disc space-y-0.5'>
                  {m.summary.map((line, i) => (
                    <li
                      key={i}
                      className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'
                    >
                      {line}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
