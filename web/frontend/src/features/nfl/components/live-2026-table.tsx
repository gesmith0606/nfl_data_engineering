import { Badge } from '@/components/ui/badge';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { SUCCESS_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';
import { formatGap } from '@/lib/nfl/consensus';
import { cn } from '@/lib/utils';
import { SectionOverline } from './section-heading';

export interface LiveRow {
  n: number;
  ourMae: number;
  sleeperMae: number;
  trailing3Mae: number;
  gap: number;
  rhoOurs: number;
  rhoSleeper: number;
  bandCoverage: number;
}

export interface LiveMetrics {
  weeks: string;
  updated: string;
  overall: LiveRow;
  positions: Array<LiveRow & { position: string }>;
}

type Row = LiveRow & { position: string; isOverall?: boolean };

const columns: BroadcastColumn<Row>[] = [
  {
    key: 'position',
    header: 'Position',
    sticky: true,
    accessor: (row) =>
      row.isOverall ? (
        <span className='wc-display text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>Overall</span>
      ) : (
        <Badge variant='outline' className={getPositionBadgeClass(row.position)}>
          {row.position}
        </Badge>
      )
  },
  {
    key: 'n',
    header: 'Player-weeks',
    align: 'right',
    accessor: (row) => row.n.toLocaleString(),
    cellClassName: 'text-muted-foreground tabular-nums'
  },
  {
    key: 'ourMae',
    header: 'Ours MAE',
    align: 'right',
    accessor: (row) => <span className='wc-num-hero'>{row.ourMae.toFixed(2)}</span>
  },
  {
    key: 'sleeperMae',
    header: 'Sleeper MAE',
    align: 'right',
    accessor: (row) => row.sleeperMae.toFixed(2),
    cellClassName: 'text-muted-foreground tabular-nums'
  },
  {
    key: 'gap',
    header: 'Gap',
    align: 'right',
    accessor: (row) => (
      <span
        data-testid={`gap-${row.position}`}
        className={cn('font-bold tabular-nums', row.gap > 0 ? DANGER_TEXT : SUCCESS_TEXT)}
      >
        {formatGap(row.gap)}
      </span>
    )
  },
  {
    key: 'trailing3Mae',
    header: 'Trailing-3 MAE',
    align: 'right',
    accessor: (row) => row.trailing3Mae.toFixed(2),
    cellClassName: 'text-muted-foreground tabular-nums'
  }
];

/** 2026 live per-position table (from the season scorecard). Gap = ours minus
 *  Sleeper, so positive = behind. */
export function Live2026Table({ live }: { live: LiveMetrics }) {
  const rows: Row[] = [
    ...live.positions,
    { ...live.overall, position: 'Overall', isOverall: true }
  ];
  const o = live.overall;
  return (
    <div className='space-y-[var(--gap-stack)]'>
      <Card>
        <CardHeader>
          <SectionOverline>2026 live</SectionOverline>
          <CardTitle className='wc-display'>2026 live vs Sleeper</CardTitle>
          <CardDescription>
            Mean absolute error in fantasy points per player-week. Gap is ours minus Sleeper: positive means we were
            further from the actual score.
          </CardDescription>
        </CardHeader>
      </Card>
      <BroadcastTable
        columns={columns}
        rows={rows}
        getRowId={(row) => (row.isOverall ? 'overall' : row.position)}
        rowClassName={(row) =>
          row.isOverall ? 'bg-muted/40 border-t-2 border-t-[var(--wc-yellow,#ffd84d)]' : ''
        }
        emptyMessage='No 2026 scorecard data available.'
        minWidth='min-w-[560px]'
      />
      <p
        data-testid='live-summary'
        className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'
      >
        Rank correlation, ours vs Sleeper: {o.rhoOurs.toFixed(3)} vs {o.rhoSleeper.toFixed(3)}.
        Band coverage: {o.bandCoverage.toFixed(2)} (share of outcomes inside our floor–ceiling
        band; target ~80%). Weeks covered: {live.weeks}. Updated {live.updated}.
      </p>
    </div>
  );
}
