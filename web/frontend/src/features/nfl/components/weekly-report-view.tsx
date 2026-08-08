'use client';

import { useQuery } from '@tanstack/react-query';
import { currentWeekQueryOptions } from '../api/queries';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { FadeIn } from '@/lib/motion-primitives';

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

function PlayerRow({
  player,
  right
}: {
  player: { player_name: string; team: string | null; position: string };
  right: React.ReactNode;
}) {
  return (
    <div className='flex items-center justify-between border-b py-1.5 text-sm last:border-0'>
      <span>
        <Badge variant='outline' className='mr-2'>
          {player.position}
        </Badge>
        {player.player_name}
        <span className='text-muted-foreground ml-1 text-xs'>{player.team}</span>
      </span>
      {right}
    </div>
  );
}

export function WeeklyReportView() {
  const { data: cw } = useQuery(currentWeekQueryOptions());
  const season = cw?.season ?? new Date().getFullYear();
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
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Weekly report</CardTitle>
          </CardHeader>
          <CardContent>
            <p className='text-muted-foreground text-sm'>
              {data.message ?? 'The weekly report goes live once the season starts.'}
            </p>
          </CardContent>
        </Card>
      </FadeIn>
    );
  }

  return (
    <FadeIn>
      <div className='space-y-4'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>
              Week {data.headline.week} weekly report{' '}
              <span className='text-muted-foreground text-xs font-normal'>
                {data.headline.season} season
              </span>
            </CardTitle>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Top projected</CardTitle>
          </CardHeader>
          <CardContent>
            <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-4'>
              {POSITIONS.map((pos) => (
                <div key={pos}>
                  <h4 className='text-muted-foreground mb-2 text-xs font-semibold'>
                    {pos}
                  </h4>
                  {(data.top_projected[pos] ?? []).map((p) => (
                    <PlayerRow
                      key={p.player_id}
                      player={p}
                      right={
                        <span className='font-mono'>
                          {p.projected_points.toFixed(1)}
                          {p.projected_floor != null && p.projected_ceiling != null && (
                            <span className='text-muted-foreground ml-1 text-xs'>
                              ({p.projected_floor.toFixed(1)}-
                              {p.projected_ceiling.toFixed(1)})
                            </span>
                          )}
                        </span>
                      }
                    />
                  ))}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Injury watch</CardTitle>
          </CardHeader>
          <CardContent>
            {data.injury_watch.length === 0 ? (
              <p className='text-muted-foreground text-sm'>No notable injuries this week.</p>
            ) : (
              data.injury_watch.map((p) => (
                <PlayerRow
                  key={p.player_id}
                  player={p}
                  right={
                    <span>
                      <Badge variant='destructive' className='mr-2'>
                        {p.injury_status}
                      </Badge>
                      <span className='font-mono'>{p.projected_points.toFixed(1)}</span>
                    </span>
                  }
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Matchup spotlight</CardTitle>
          </CardHeader>
          <CardContent>
            <div className='grid gap-4 md:grid-cols-2'>
              <div>
                <h4 className='text-muted-foreground mb-2 text-xs font-semibold'>
                  Best matchups
                </h4>
                {data.matchup_spotlight.best.map((c, i) => (
                  <div
                    key={`${c.team}-${c.position}-${i}`}
                    className='flex items-center justify-between border-b py-1.5 text-sm last:border-0'
                  >
                    <span>
                      <Badge variant='outline' className='mr-2'>
                        {c.position}
                      </Badge>
                      {c.team} vs {c.opponent}
                    </span>
                    <span className='font-mono'>rank {c.opp_rank}</span>
                  </div>
                ))}
              </div>
              <div>
                <h4 className='text-muted-foreground mb-2 text-xs font-semibold'>
                  Toughest matchups
                </h4>
                {data.matchup_spotlight.worst.map((c, i) => (
                  <div
                    key={`${c.team}-${c.position}-${i}`}
                    className='flex items-center justify-between border-b py-1.5 text-sm last:border-0'
                  >
                    <span>
                      <Badge variant='outline' className='mr-2'>
                        {c.position}
                      </Badge>
                      {c.team} vs {c.opponent}
                    </span>
                    <span className='font-mono'>rank {c.opp_rank}</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Boom / bust</CardTitle>
          </CardHeader>
          <CardContent>
            <div className='grid gap-4 md:grid-cols-2'>
              <div>
                <h4 className='text-muted-foreground mb-2 text-xs font-semibold'>
                  Upside plays
                </h4>
                {data.boom_bust.upside.map((p) => (
                  <PlayerRow
                    key={p.player_id}
                    player={p}
                    right={
                      <span className='font-mono'>
                        +{p.ceiling_minus_floor?.toFixed(1) ?? '—'}
                      </span>
                    }
                  />
                ))}
              </div>
              <div>
                <h4 className='text-muted-foreground mb-2 text-xs font-semibold'>
                  Safe plays
                </h4>
                {data.boom_bust.safe.map((p) => (
                  <PlayerRow
                    key={p.player_id}
                    player={p}
                    right={
                      <span className='font-mono'>
                        {p.floor_ratio != null ? `${(p.floor_ratio * 100).toFixed(0)}%` : '—'}
                      </span>
                    }
                  />
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </FadeIn>
  );
}
