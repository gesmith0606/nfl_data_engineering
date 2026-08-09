import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { playerCorrelationsQueryOptions } from '../../api/queries';
import type { PlayerCorrelation } from '@/lib/nfl/types';

/** Human labels for the structural correlation relation types (UC3). */
const RELATION_LABELS: Record<string, string> = {
  qb_stack: 'QB Stack',
  same_backfield: 'Same Backfield',
  wr_teammates: 'WR Teammates',
  game_stack: 'Game Stack'
};

export interface CorrelationsPanelProps {
  playerId: string;
}

/**
 * Correlated players (UC3) — ported from the retired PlayerDetail page.
 * Stability-gated fantasy-point correlation edges over shared games,
 * stable 2016-2025. Positive rho = the pair's big games coincide (stack
 * value); negative = they trade off. Rendered as a BroadcastTable — the
 * yellow condensed headers over the 2px mint rule (`.wc-broadcast-table`,
 * src/styles/broadcast.css) is the "mint rail" treatment for this section,
 * matching GameLogTable immediately below it on the same page.
 *
 * Empty/loading policy matches PercentileBars: skeleton rows while loading
 * (via BroadcastTable's own `isLoading`), a quiet inline note when the
 * player has no served edges (most deep-roster players, rookies, and
 * preseason players won't) rather than disappearing outright.
 */
export function CorrelationsPanel({ playerId }: CorrelationsPanelProps) {
  const { data, isLoading } = useQuery(playerCorrelationsQueryOptions(playerId));
  const correlations = data?.correlations ?? [];

  const columns: BroadcastColumn<PlayerCorrelation>[] = [
    {
      key: 'player',
      header: 'Player',
      sticky: true,
      accessor: (r) => r.other_player_name,
      renderCell: (r) => (
        <Link
          href={`/dashboard/players/${r.other_player_id}`}
          className='font-medium hover:underline'
        >
          {r.other_player_name}
        </Link>
      )
    },
    {
      key: 'relation',
      header: 'Relation',
      accessor: (r) => RELATION_LABELS[r.relation] ?? r.relation
    },
    {
      key: 'rho',
      header: 'Correlation',
      align: 'right',
      accessor: (r) => `${r.rho >= 0 ? '+' : ''}${r.rho.toFixed(2)}`,
      renderCell: (r) => (
        <span
          className='wc-num-hero'
          style={{ color: r.rho >= 0 ? 'var(--success)' : 'var(--warn)' }}
        >
          {r.rho >= 0 ? '+' : ''}
          {r.rho.toFixed(2)}
        </span>
      )
    },
    {
      key: 'n_games',
      header: 'Games',
      align: 'right',
      accessor: (r) => r.n_games,
      cellClassName: 'text-muted-foreground'
    }
  ];

  return (
    <div>
      <h2 className='wc-display mb-[var(--space-2)] text-[length:var(--fs-sm)] tracking-[0.1em] text-muted-foreground'>
        Correlated Players
      </h2>
      <BroadcastTable
        columns={columns}
        rows={correlations}
        getRowId={(r) => r.other_player_id}
        isLoading={isLoading}
        skeletonRows={3}
        emptyMessage='No correlated players tracked yet for this player — stack edges are rebuilt a few times a season and thin out for backups and rookies.'
        minWidth='min-w-[520px]'
      />
    </div>
  );
}
