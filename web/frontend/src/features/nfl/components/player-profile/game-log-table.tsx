import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import type { PlayerGameLogEntry } from '@/lib/nfl/types';

type NumericStatKey = Extract<
  keyof PlayerGameLogEntry,
  | 'passing_yards'
  | 'passing_tds'
  | 'rushing_yards'
  | 'rushing_tds'
  | 'receptions'
  | 'receiving_yards'
  | 'receiving_tds'
  | 'targets'
  | 'carries'
>;

function statCol(
  key: NumericStatKey,
  header: string,
  decimals = 0
): BroadcastColumn<PlayerGameLogEntry> {
  return {
    key,
    header,
    align: 'right',
    cellClassName: 'font-mono',
    accessor: (r) => {
      const v = r[key];
      return v == null ? '—' : v.toFixed(decimals);
    }
  };
}

/** Position-conditional stat columns — every column only appears when the position's game log entries actually carry that stat. */
function positionStatColumns(position: string): BroadcastColumn<PlayerGameLogEntry>[] {
  switch (position) {
    case 'QB':
      return [
        statCol('passing_yards', 'Pass Yds'),
        statCol('passing_tds', 'Pass TD'),
        statCol('rushing_yards', 'Rush Yds')
      ];
    case 'RB':
      return [
        statCol('rushing_yards', 'Rush Yds'),
        statCol('rushing_tds', 'Rush TD'),
        statCol('receptions', 'Rec'),
        statCol('receiving_yards', 'Rec Yds')
      ];
    case 'WR':
    case 'TE':
      return [
        statCol('targets', 'Tgt'),
        statCol('receptions', 'Rec'),
        statCol('receiving_yards', 'Rec Yds'),
        statCol('receiving_tds', 'Rec TD')
      ];
    default:
      return [];
  }
}

export interface GameLogTableProps {
  position: string;
  rows: PlayerGameLogEntry[];
  isLoading: boolean;
  emptyMessage: string;
}

/**
 * Weekly game log rendered as a BroadcastTable. `GET /api/games/player-log`
 * returns ACTUAL fantasy production only — `PlayerGameLogEntry` has no
 * per-week projected field — so there is no projected column here. The
 * profile's one real "projected vs actual" data point is THIS week's single
 * projection, shown in the header/bottom line above, not a per-past-week
 * series (the API doesn't retain a historical weekly-projection snapshot).
 */
export function GameLogTable({ position, rows, isLoading, emptyMessage }: GameLogTableProps) {
  const columns: BroadcastColumn<PlayerGameLogEntry>[] = [
    {
      key: 'week',
      header: 'Wk',
      sticky: true,
      width: 'w-12',
      accessor: (r) => r.week
    },
    {
      key: 'opponent',
      header: 'Opp',
      accessor: (r) => (r.opponent ? `${r.home_away === 'away' ? '@' : 'vs'} ${r.opponent}` : '—')
    },
    {
      key: 'result',
      header: 'Result',
      accessor: (r) => r.game_result || '—'
    },
    {
      key: 'fantasy_points',
      header: 'Fantasy Pts',
      align: 'right',
      accessor: (r) => r.fantasy_points.toFixed(1),
      renderCell: (r) => <span className='wc-num-hero'>{r.fantasy_points.toFixed(1)}</span>
    },
    ...positionStatColumns(position)
  ];

  return (
    <BroadcastTable
      columns={columns}
      rows={rows}
      getRowId={(r) => r.week}
      isLoading={isLoading}
      skeletonRows={5}
      emptyMessage={emptyMessage}
      minWidth='min-w-[640px]'
    />
  );
}
