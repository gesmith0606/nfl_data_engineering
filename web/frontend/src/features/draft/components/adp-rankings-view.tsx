'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { adpBoardQueryOptions } from '@/features/nfl/api/queries';
import { DraftBoardTable } from './draft-board-table';
import { WC_TABS_LIST, WC_TAB_TRIGGER } from '../utils/broadcast-ui';
import type { AdpSource, Position, ScoringFormat } from '@/lib/nfl/types';

const POSITIONS: Position[] = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K', 'DST'];
const SCORING_OPTIONS: { value: ScoringFormat; label: string }[] = [
  { value: 'ppr', label: 'PPR' },
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'standard', label: 'Standard' }
];
const SOURCE_OPTIONS: { value: AdpSource; label: string; title: string }[] = [
  { value: 'ffc', label: 'FFC', title: 'FantasyFootballCalculator — real mock-draft ADP' },
  { value: 'sleeper', label: 'Sleeper', title: 'Sleeper crowd ADP' },
  { value: 'espn', label: 'ESPN', title: 'ESPN live-draft ADP' }
];

const TAB = `${WC_TAB_TRIGGER} text-[length:var(--fs-xs)] leading-[var(--lh-xs)]`;

/**
 * Public ADP rankings page: where the market drafts every player (real ADP)
 * next to where our model ranks him. Reuses the draft-room board in read-only
 * mode against the stateless `/api/draft/adp-board` endpoint — no draft
 * session is created just by looking.
 */
export function AdpRankingsView() {
  const [scoring, setScoring] = useState<ScoringFormat>('half_ppr');
  const [source, setSource] = useState<AdpSource>('ffc');
  const [positionFilter, setPositionFilter] = useState<Position>('ALL');

  const { data, isLoading, isError, error } = useQuery(adpBoardQueryOptions(scoring, 2026, source));
  const sourceLabel = SOURCE_OPTIONS.find((o) => o.value === source)?.label;
  const scoringLabel = SCORING_OPTIONS.find((o) => o.value === scoring)?.label;

  return (
    <div className='space-y-[var(--space-4)]'>
      <div className='flex flex-wrap items-center gap-[var(--space-3)]'>
        <Tabs value={scoring} onValueChange={(v) => setScoring(v as ScoringFormat)}>
          <TabsList className={WC_TABS_LIST} aria-label='Scoring format'>
            {SCORING_OPTIONS.map((o) => (
              <TabsTrigger key={o.value} value={o.value} className={TAB}>
                {o.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Tabs value={source} onValueChange={(v) => setSource(v as AdpSource)}>
          <TabsList className={WC_TABS_LIST} aria-label='ADP source'>
            {SOURCE_OPTIONS.map((o) => (
              <TabsTrigger key={o.value} value={o.value} className={TAB} title={o.title}>
                {o.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Tabs value={positionFilter} onValueChange={(v) => setPositionFilter(v as Position)}>
          <TabsList className={WC_TABS_LIST} aria-label='Position'>
            {POSITIONS.map((pos) => (
              <TabsTrigger key={pos} value={pos} className={TAB}>
                {pos}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
        ADP = where the market actually drafts a player ({sourceLabel}, {scoringLabel}). Rank = our
        model. Value = ADP − our rank: positive means the market lets him fall past where we&apos;d
        take him. Click any column to re-sort.
      </p>

      {isLoading ? (
        <div className='space-y-[var(--space-2)]' data-testid='adp-loading'>
          <Skeleton className='h-9 w-full' />
          <Skeleton className='h-64 w-full' />
        </div>
      ) : isError || !data ? (
        <Alert variant='destructive'>
          <AlertDescription>
            ADP board unavailable{error instanceof Error ? `: ${error.message}` : ''}. Run{' '}
            <code>python scripts/refresh_adp.py --season 2026</code> to refresh the ADP feed.
          </AlertDescription>
        </Alert>
      ) : (
        <DraftBoardTable
          players={data.players}
          positionFilter={positionFilter}
          readOnly
          defaultSort='adp_rank'
        />
      )}
    </div>
  );
}
