'use client';

import { useState } from 'react';
import { importEspnLeague } from '@/lib/nfl/api';
import type { EspnImportResponse, EspnTeam } from '@/lib/nfl/types';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { DANGER_TEXT } from '@/lib/nfl/semantic-colors';
import {
  WC_CTA_BUTTON,
  WC_GHOST_BUTTON,
  WC_HEADING,
  WC_INPUT
} from '@/features/draft/utils/broadcast-ui';

const teamColumns: BroadcastColumn<EspnTeam>[] = [
  {
    key: 'team',
    header: 'Team',
    sticky: true,
    accessor: (t) => (
      <div className='flex items-center gap-2'>
        <span className='text-sm font-medium'>{t.team_name}</span>
        {t.is_my_team && (
          <span className='inline-flex items-center rounded-full border border-[rgba(145,237,208,0.4)] bg-[rgba(145,237,208,0.12)] px-2 py-0.5 text-[length:var(--fs-micro)] leading-[var(--lh-micro)] font-semibold text-[var(--wc-mint,#91edd0)]'>
            Your team
          </span>
        )}
      </div>
    )
  },
  {
    key: 'owner',
    header: 'Owner',
    cellClassName: 'text-muted-foreground',
    accessor: (t) => t.owner_name ?? '—'
  },
  {
    key: 'record',
    header: 'Record',
    align: 'right',
    cellClassName: 'tabular-nums',
    accessor: (t) => `${t.wins}-${t.losses}`
  }
];

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
    <BroadcastPanel className='space-y-3 p-4'>
      <h3 className={`${WC_HEADING} text-base`}>Import an ESPN League</h3>
      <div className='flex flex-wrap gap-2'>
        <Input
          placeholder='ESPN league ID (from the league URL)'
          value={leagueId}
          onChange={(e) => setLeagueId(e.target.value.replace(/\D/g, ''))}
          className={`h-9 w-64 ${WC_INPUT}`}
        />
        <Input
          placeholder='Season'
          value={season}
          onChange={(e) => setSeason(e.target.value.replace(/\D/g, ''))}
          className={`h-9 w-24 ${WC_INPUT}`}
        />
        <Button
          variant='outline'
          disabled={!leagueId || !season || loading}
          onClick={onImport}
          className={WC_CTA_BUTTON}
        >
          {loading ? 'Importing...' : 'Import'}
        </Button>
      </div>
      <Button
        type='button'
        variant='ghost'
        size='sm'
        className={`h-auto p-0 text-xs underline ${WC_GHOST_BUTTON}`}
        onClick={() => setShowPrivate((s) => !s)}
      >
        Private league cookies {showPrivate ? '▴' : '▾'}
      </Button>
      {showPrivate && (
        <div className='space-y-2'>
          <Input
            placeholder='espn_s2 cookie'
            value={espnS2}
            onChange={(e) => setEspnS2(e.target.value)}
            className={`h-9 ${WC_INPUT}`}
          />
          <Input
            placeholder='SWID cookie (with or without braces)'
            value={swid}
            onChange={(e) => setSwid(e.target.value)}
            className={`h-9 ${WC_INPUT}`}
          />
          <p className='text-xs text-muted-foreground'>
            DevTools → Application → Cookies → fantasy.espn.com. Used only for this request; never
            stored.
          </p>
        </div>
      )}
      {error && <p className={`text-sm ${DANGER_TEXT}`}>{error}</p>}

      {data && (
        <div className='space-y-3'>
          <p className='text-sm font-medium'>
            {data.league_name ?? `League ${data.league_id}`}{' '}
            <span className='text-xs font-normal text-muted-foreground'>
              {data.team_count ?? data.teams.length} teams · {data.scoring_type ?? 'unknown scoring'} ·{' '}
              {data.season}
            </span>
          </p>
          <BroadcastTable
            columns={teamColumns}
            rows={data.teams}
            getRowId={(t) => t.team_id}
            emptyMessage='No teams found.'
            minWidth='min-w-[360px]'
          />
          {myTeam && myTeam.roster.length > 0 && (
            <div>
              <h4 className={`${WC_HEADING} mb-1 text-xs text-muted-foreground`}>Your Roster</h4>
              <div className='flex flex-wrap gap-1'>
                {myTeam.roster.map((p, i) => (
                  <Badge key={`${p.player_name}-${i}`} variant={p.is_starter ? 'default' : 'secondary'}>
                    {p.position} {p.player_name}
                    {p.injury_status && p.injury_status !== 'ACTIVE' ? ` (${p.injury_status})` : ''}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </BroadcastPanel>
  );
}
