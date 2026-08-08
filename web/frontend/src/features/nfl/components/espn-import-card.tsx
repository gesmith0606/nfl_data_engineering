'use client';

import { useState } from 'react';
import { importEspnLeague } from '@/lib/nfl/api';
import type { EspnImportResponse } from '@/lib/nfl/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

/** ESPN league import — public leagues need only the league ID.
 *  Cookies are sent straight to the one ESPN call and never stored. */
export function EspnImportCard() {
  const [leagueId, setLeagueId] = useState('');
  const [season, setSeason] = useState(String(new Date().getFullYear()));
  const [espnS2, setEspnS2] = useState('');
  const [swid, setSwid] = useState('');
  const [showPrivate, setShowPrivate] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<EspnImportResponse | null>(null);

  async function onImport() {
    setLoading(true);
    setError(null);
    try {
      const res = await importEspnLeague({
        league_id: Number(leagueId),
        season: Number(season),
        espn_s2: espnS2 || undefined,
        swid: swid || undefined
      });
      setData(res);
    } catch (e) {
      const status =
        e != null && typeof e === 'object' && 'status' in e
          ? (e as { status: number }).status
          : 0;
      setError(
        status === 401
          ? 'Private league — expand "Private league cookies" and paste espn_s2 + SWID from fantasy.espn.com.'
          : status === 404
            ? 'League not found for that season — double-check the league ID.'
            : 'Import failed — ESPN may be unreachable. Try again shortly.'
      );
    } finally {
      setLoading(false);
    }
  }

  const myTeam = data?.teams.find((t) => t.is_my_team);

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>Import an ESPN league</CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='flex flex-wrap gap-2'>
          <Input
            placeholder='ESPN league ID (from the league URL)'
            value={leagueId}
            onChange={(e) => setLeagueId(e.target.value.replace(/\D/g, ''))}
            className='h-9 w-64'
          />
          <Input
            placeholder='Season'
            value={season}
            onChange={(e) => setSeason(e.target.value.replace(/\D/g, ''))}
            className='h-9 w-24'
          />
          <Button
            onClick={onImport}
            disabled={!leagueId || !season || loading}
          >
            {loading ? 'Importing...' : 'Import'}
          </Button>
        </div>
        <button
          type='button'
          className='text-muted-foreground text-xs underline'
          onClick={() => setShowPrivate((s) => !s)}
        >
          Private league cookies {showPrivate ? '▴' : '▾'}
        </button>
        {showPrivate && (
          <div className='space-y-2'>
            <Input
              placeholder='espn_s2 cookie'
              value={espnS2}
              onChange={(e) => setEspnS2(e.target.value)}
              className='h-9'
            />
            <Input
              placeholder='SWID cookie (with or without braces)'
              value={swid}
              onChange={(e) => setSwid(e.target.value)}
              className='h-9'
            />
            <p className='text-muted-foreground text-xs'>
              DevTools → Application → Cookies → fantasy.espn.com. Used only
              for this request; never stored.
            </p>
          </div>
        )}
        {error && <p className='text-sm text-red-500'>{error}</p>}

        {data && (
          <div className='space-y-3'>
            <p className='text-sm font-medium'>
              {data.league_name ?? `League ${data.league_id}`}{' '}
              <span className='text-muted-foreground text-xs font-normal'>
                {data.team_count ?? data.teams.length} teams ·{' '}
                {data.scoring_type ?? 'unknown scoring'} · {data.season}
              </span>
            </p>
            <div className='grid gap-2 md:grid-cols-2 lg:grid-cols-3'>
              {data.teams.map((t) => (
                <div
                  key={t.team_id}
                  className={`rounded-md border px-3 py-2 text-sm ${t.is_my_team ? 'border-emerald-500' : ''}`}
                >
                  <div className='flex items-center justify-between'>
                    <span className='font-medium'>{t.team_name}</span>
                    <span className='text-muted-foreground text-xs'>
                      {t.wins}-{t.losses}
                    </span>
                  </div>
                  {t.owner_name && (
                    <p className='text-muted-foreground text-xs'>
                      {t.owner_name}
                    </p>
                  )}
                  {t.is_my_team && <Badge className='mt-1'>Your team</Badge>}
                </div>
              ))}
            </div>
            {myTeam && myTeam.roster.length > 0 && (
              <div>
                <h4 className='mb-1 text-sm font-medium'>Your roster</h4>
                <div className='flex flex-wrap gap-1'>
                  {myTeam.roster.map((p, i) => (
                    <Badge
                      key={`${p.player_name}-${i}`}
                      variant={p.is_starter ? 'default' : 'secondary'}
                    >
                      {p.position} {p.player_name}
                      {p.injury_status && p.injury_status !== 'ACTIVE'
                        ? ` (${p.injury_status})`
                        : ''}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
