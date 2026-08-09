'use client';

import { useQuery } from '@tanstack/react-query';
import { currentWeekQueryOptions } from '../api/queries';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { FadeIn } from '@/lib/motion-primitives';
import { toolSeason } from '@/lib/nfl/season';

// ---------------------------------------------------------------------------
// Types -- mirror web/api/routers/weekly_report.py response models.
// ---------------------------------------------------------------------------

type SkillPlayer = {
  player_id: string;
  player_name: string;
  team: string | null;
  position: string;
  projected_points: number;
  projected_floor: number | null;
  projected_ceiling: number | null;
};

type InjuryWatchPlayer = {
  player_id: string;
  player_name: string;
  team: string | null;
  position: string;
  injury_status: string;
  projected_points: number;
};

type MatchupCell = {
  team: string;
  position: string;
  opponent: string;
  opp_rank: number;
};

type BoomBustPlayer = SkillPlayer & {
  ceiling_minus_floor: number | null;
  floor_ratio: number | null;
};

type WeeklyReportResponse = {
  headline: { season: number; week: number | null; generated_from: string | null };
  mode: 'weekly' | 'preseason';
  message: string | null;
  top_projected: Record<string, SkillPlayer[]>;
  injury_watch: InjuryWatchPlayer[];
  matchup_spotlight: { best: MatchupCell[]; worst: MatchupCell[] };
  boom_bust: { upside: BoomBustPlayer[]; safe: BoomBustPlayer[] };
};

// ---------------------------------------------------------------------------
// Inline request logic (same BASE_URL / X-API-Key pattern as lib/nfl/api.ts,
// copied minimally here per this component's isolation requirement).
// ---------------------------------------------------------------------------

const BASE_URL =
  typeof window !== 'undefined'
    ? ''
    : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? '';

async function fetchWeeklyReport(
  season: number,
  week: number | undefined,
  scoring: string
): Promise<WeeklyReportResponse> {
  const params = new URLSearchParams({ season: String(season), scoring });
  if (week != null) params.set('week', String(week));
  const url = `${BASE_URL}/api/report/weekly?${params}`;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_KEY) headers['X-API-Key'] = API_KEY;
  const res = await fetch(url, { headers });
  if (!res.ok) {
    throw new Error(`Weekly report request failed: ${res.status}`);
  }
  return res.json() as Promise<WeeklyReportResponse>;
}

const POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;

function Spinner() {
  return (
    <div className='flex justify-center py-8'>
      <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
    </div>
  );
}

/** Section shell — broadcast panel with a condensed-caps title, wrapping
 *  whatever table(s) the section renders. */
function ReportSection({
  title,
  children
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <BroadcastPanel className='p-[var(--space-4)]'>
      <h2 className='wc-display mb-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tracking-[0.12em] text-white'>
        {title}
      </h2>
      {children}
    </BroadcastPanel>
  );
}

const nameCell = (p: { player_name: string; team: string | null; position: string }) => (
  <>
    <Badge variant='outline' className='mr-2'>
      {p.position}
    </Badge>
    {p.player_name}
    <span className='text-muted-foreground ml-1 text-xs'>{p.team}</span>
  </>
);

export function WeeklyReportView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = toolSeason(cw?.season);
  const week = cw?.week ?? undefined;

  const report = useQuery({
    queryKey: ['nfl', 'weekly-report', season, week],
    queryFn: () => fetchWeeklyReport(season, week, 'half_ppr'),
    staleTime: 15 * 60 * 1000,
    retry: false
  });

  if (report.isLoading) {
    return (
      <FadeIn>
        <Spinner />
      </FadeIn>
    );
  }

  const data = report.data;
  if (!data) {
    return (
      <FadeIn>
        <p className='text-muted-foreground text-sm'>
          Weekly report is unavailable right now.
        </p>
      </FadeIn>
    );
  }

  if (data.mode === 'preseason') {
    return (
      <FadeIn>
        <BroadcastPanel className='p-[var(--space-4)]'>
          <h2 className='wc-display text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tracking-[0.12em] text-white'>
            Weekly report
          </h2>
          <p className='mt-[var(--space-2)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/50'>
            {data.message ?? 'The weekly report goes live once the season starts.'}
          </p>
        </BroadcastPanel>
      </FadeIn>
    );
  }

  const topProjectedColumns: BroadcastColumn<SkillPlayer>[] = [
    {
      key: 'player',
      header: 'Player',
      sticky: true,
      accessor: (p) => (
        <>
          {p.player_name}
          <span className='text-muted-foreground ml-1 text-xs'>{p.team}</span>
        </>
      )
    },
    {
      key: 'proj',
      header: 'Proj',
      align: 'right',
      accessor: (p) => p.projected_points.toFixed(1),
      renderCell: (p) => <span className='wc-num-hero'>{p.projected_points.toFixed(1)}</span>
    },
    {
      key: 'range',
      header: 'Floor – Ceiling',
      align: 'right',
      accessor: (p) =>
        p.projected_floor != null && p.projected_ceiling != null
          ? `${p.projected_floor.toFixed(1)}–${p.projected_ceiling.toFixed(1)}`
          : '—',
      cellClassName: 'text-muted-foreground font-mono text-xs'
    }
  ];

  const injuryColumns: BroadcastColumn<InjuryWatchPlayer>[] = [
    { key: 'player', header: 'Player', sticky: true, accessor: nameCell },
    {
      key: 'status',
      header: 'Status',
      accessor: (p) => <Badge variant='destructive'>{p.injury_status}</Badge>
    },
    {
      key: 'proj',
      header: 'Proj',
      align: 'right',
      accessor: (p) => p.projected_points.toFixed(1),
      renderCell: (p) => <span className='wc-num-hero'>{p.projected_points.toFixed(1)}</span>
    }
  ];

  const matchupColumns: BroadcastColumn<MatchupCell>[] = [
    {
      key: 'matchup',
      header: 'Matchup',
      sticky: true,
      accessor: (c) => (
        <>
          <Badge variant='outline' className='mr-2'>
            {c.position}
          </Badge>
          {c.team} vs {c.opponent}
        </>
      )
    },
    {
      key: 'rank',
      header: 'Opp rank',
      align: 'right',
      accessor: (c) => `#${c.opp_rank}`,
      renderCell: (c) => <span className='wc-num-hero'>#{c.opp_rank}</span>
    }
  ];

  const boomColumns: BroadcastColumn<BoomBustPlayer>[] = [
    { key: 'player', header: 'Player', sticky: true, accessor: nameCell },
    {
      key: 'range',
      header: 'Ceiling edge',
      align: 'right',
      accessor: (p) => `+${p.ceiling_minus_floor?.toFixed(1) ?? '—'}`,
      renderCell: (p) => (
        <span className='wc-num-hero'>+{p.ceiling_minus_floor?.toFixed(1) ?? '—'}</span>
      )
    }
  ];

  const bustColumns: BroadcastColumn<BoomBustPlayer>[] = [
    { key: 'player', header: 'Player', sticky: true, accessor: nameCell },
    {
      key: 'floor_ratio',
      header: 'Floor ratio',
      align: 'right',
      accessor: (p) => (p.floor_ratio != null ? `${(p.floor_ratio * 100).toFixed(0)}%` : '—'),
      renderCell: (p) => (
        <span className='wc-num-hero'>
          {p.floor_ratio != null ? `${(p.floor_ratio * 100).toFixed(0)}%` : '—'}
        </span>
      )
    }
  ];

  return (
    <FadeIn>
      <div className='space-y-[var(--gap-section)]'>
        <BroadcastPanel className='p-[var(--space-4)]'>
          <h1 className='wc-display text-[length:var(--fs-lg)] leading-[var(--lh-lg)] text-white'>
            Week {data.headline.week} weekly report
          </h1>
          <p className='mt-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.1em] text-white/40 uppercase'>
            {data.headline.season} season
          </p>
        </BroadcastPanel>

        <ReportSection title='Top projected'>
          <BroadcastTable
            columns={topProjectedColumns}
            tiers={POSITIONS.map((pos) => ({
              key: pos,
              label: pos,
              rows: data.top_projected[pos] ?? []
            }))}
            getRowId={(p) => p.player_id}
            emptyMessage='No projections available.'
            minWidth='min-w-[480px]'
          />
        </ReportSection>

        <ReportSection title='Injury watch'>
          <BroadcastTable
            columns={injuryColumns}
            rows={data.injury_watch}
            getRowId={(p) => p.player_id}
            emptyMessage='No notable injuries this week.'
          />
        </ReportSection>

        <ReportSection title='Matchup spotlight'>
          <div className='grid gap-[var(--gap-stack)] md:grid-cols-2'>
            <div>
              <div className='text-muted-foreground mb-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.08em] uppercase'>
                Best matchups
              </div>
              <BroadcastTable
                columns={matchupColumns}
                rows={data.matchup_spotlight.best}
                getRowId={(c, i) => `${c.team}-${c.position}-${i}`}
                emptyMessage='No matchup data available.'
                minWidth='min-w-[360px]'
              />
            </div>
            <div>
              <div className='text-muted-foreground mb-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.08em] uppercase'>
                Toughest matchups
              </div>
              <BroadcastTable
                columns={matchupColumns}
                rows={data.matchup_spotlight.worst}
                getRowId={(c, i) => `${c.team}-${c.position}-${i}`}
                emptyMessage='No matchup data available.'
                minWidth='min-w-[360px]'
              />
            </div>
          </div>
        </ReportSection>

        <ReportSection title='Boom / bust'>
          <div className='grid gap-[var(--gap-stack)] md:grid-cols-2'>
            <div>
              <div className='text-muted-foreground mb-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.08em] uppercase'>
                Upside plays
              </div>
              <BroadcastTable
                columns={boomColumns}
                rows={data.boom_bust.upside}
                getRowId={(p) => p.player_id}
                emptyMessage='No upside plays this week.'
                minWidth='min-w-[280px]'
              />
            </div>
            <div>
              <div className='text-muted-foreground mb-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.08em] uppercase'>
                Safe plays
              </div>
              <BroadcastTable
                columns={bustColumns}
                rows={data.boom_bust.safe}
                getRowId={(p) => p.player_id}
                emptyMessage='No safe plays this week.'
                minWidth='min-w-[280px]'
              />
            </div>
          </div>
        </ReportSection>
      </div>
    </FadeIn>
  );
}
