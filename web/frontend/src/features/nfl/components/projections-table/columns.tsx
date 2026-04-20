'use client';

import { Badge } from '@/components/ui/badge';
import { DataTableColumnHeader } from '@/components/ui/table/data-table-column-header';
import type { PlayerProjection } from '../../api/types';
import { Column, ColumnDef } from '@tanstack/react-table';
import { getTeamColor } from '@/lib/nfl/team-colors';
import Link from 'next/link';

/**
 * Mobile adaptation strategy (Phase 62-05, DSGN-04):
 *
 * At 375px viewport this 8-column table would force horizontal scroll. Instead
 * of card-view rewrite, we hide the less-critical columns below the `sm:`
 * breakpoint (640px) and keep the essentials visible: Player, Position,
 * Projected. Everything else (Rank, Team, Floor, Ceiling, Key Stats) is
 * reached by the player-detail page. This avoids horizontal scroll without
 * sacrificing the primary task (skim projections, tap a player).
 *
 * Under the hood we set `meta.headerClassName` / `meta.cellClassName` and the
 * DataTable component reads them onto `<TableHead>` / `<TableCell>`.
 */
const HIDE_BELOW_SM = 'hidden sm:table-cell';
const HIDE_BELOW_MD = 'hidden md:table-cell';

export const columns: ColumnDef<PlayerProjection>[] = [
  {
    id: 'position_rank',
    accessorKey: 'position_rank',
    header: ({ column }: { column: Column<PlayerProjection, unknown> }) => (
      <DataTableColumnHeader column={column} title='Rank' />
    ),
    cell: ({ cell }) => (
      <span className='text-muted-foreground tabular-nums font-medium'>
        {cell.getValue<number | null>() ?? '-'}
      </span>
    ),
    meta: {
      headerClassName: HIDE_BELOW_SM,
      cellClassName: HIDE_BELOW_SM
    }
  },
  {
    id: 'player_name',
    accessorKey: 'player_name',
    header: ({ column }: { column: Column<PlayerProjection, unknown> }) => (
      <DataTableColumnHeader column={column} title='Player' />
    ),
    cell: ({ row }) => {
      const injury = row.original.injury_status;
      return (
        <div className='flex min-h-[var(--tap-min)] items-center gap-[var(--space-2)]'>
          <Link
            href={`/dashboard/players/${row.original.player_id}`}
            className='font-medium hover:underline truncate max-w-[12ch] sm:max-w-none'
          >
            {row.original.player_name}
          </Link>
          {injury && injury !== 'Active' && (
            <Badge
              variant='destructive'
              className='text-[length:var(--fs-micro)] leading-[var(--lh-micro)] px-[var(--space-1)] py-0'
            >
              {injury}
            </Badge>
          )}
        </div>
      );
    },
    enableColumnFilter: true,
    meta: {
      label: 'Player',
      placeholder: 'Search players...',
      variant: 'text' as const
    }
  },
  {
    id: 'team',
    accessorKey: 'team',
    header: 'Team',
    cell: ({ cell }) => {
      const team = cell.getValue<string>();
      const color = getTeamColor(team);
      return (
        <div className='flex items-center gap-[var(--space-2)]'>
          <span
            className='inline-block h-[var(--space-2)] w-[var(--space-2)] shrink-0 rounded-full'
            style={{ backgroundColor: color }}
          />
          <span className='font-mono text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
            {team}
          </span>
        </div>
      );
    },
    meta: {
      headerClassName: HIDE_BELOW_SM,
      cellClassName: HIDE_BELOW_SM
    }
  },
  {
    id: 'position',
    accessorKey: 'position',
    header: 'Pos',
    cell: ({ cell }) => {
      const pos = cell.getValue<string>();
      const colorMap: Record<string, string> = {
        QB: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
        RB: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
        WR: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400',
        TE: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
        K: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400'
      };
      return (
        <Badge variant='outline' className={colorMap[pos] || ''}>
          {pos}
        </Badge>
      );
    }
  },
  {
    id: 'projected_points',
    accessorKey: 'projected_points',
    header: ({ column }: { column: Column<PlayerProjection, unknown> }) => (
      <DataTableColumnHeader column={column} title='Projected' />
    ),
    cell: ({ cell }) => (
      <span className='font-bold tabular-nums text-[length:var(--fs-lg)] leading-[var(--lh-lg)]'>
        {cell.getValue<number>().toFixed(1)}
      </span>
    )
  },
  {
    id: 'projected_floor',
    accessorKey: 'projected_floor',
    header: 'Floor',
    cell: ({ cell }) => (
      <span className='text-muted-foreground tabular-nums'>
        {cell.getValue<number>().toFixed(1)}
      </span>
    ),
    meta: {
      headerClassName: HIDE_BELOW_MD,
      cellClassName: HIDE_BELOW_MD
    }
  },
  {
    id: 'projected_ceiling',
    accessorKey: 'projected_ceiling',
    header: 'Ceiling',
    cell: ({ cell }) => (
      <span className='text-muted-foreground tabular-nums'>
        {cell.getValue<number>().toFixed(1)}
      </span>
    ),
    meta: {
      headerClassName: HIDE_BELOW_MD,
      cellClassName: HIDE_BELOW_MD
    }
  },
  {
    id: 'key_stats',
    header: 'Key Stats',
    cell: ({ row }) => {
      const p = row.original;
      const stats: string[] = [];
      if (p.proj_pass_yards) stats.push(`${Math.round(p.proj_pass_yards)} pass yds`);
      if (p.proj_rush_yards) stats.push(`${Math.round(p.proj_rush_yards)} rush yds`);
      if (p.proj_rec_yards) stats.push(`${Math.round(p.proj_rec_yards)} rec yds`);
      if (p.proj_rec) stats.push(`${p.proj_rec.toFixed(1)} rec`);
      return (
        <span className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
          {stats.slice(0, 2).join(' | ') || '-'}
        </span>
      );
    },
    meta: {
      headerClassName: HIDE_BELOW_MD,
      cellClassName: HIDE_BELOW_MD
    }
  }
];
