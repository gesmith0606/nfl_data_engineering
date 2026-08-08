'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  connectYahoo,
  fetchYahooAuthUrl,
  fetchYahooLeagues,
  fetchYahooStatus,
  fetchYahooTeams
} from '@/lib/nfl/api';
import type { YahooLeague } from '@/lib/nfl/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';

/** Yahoo league connect + import. One Yahoo account per deployment (the
 *  backend token store is server-global, same as the CLI draft co-pilot). */
export function YahooConnectCard() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ['nfl', 'yahoo-status'],
    queryFn: fetchYahooStatus,
    retry: false
  });

  const [code, setCode] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [league, setLeague] = useState<YahooLeague | null>(null);

  const leagues = useQuery({
    queryKey: ['nfl', 'yahoo-leagues'],
    queryFn: () => fetchYahooLeagues(),
    enabled: status.data?.connected === true,
    retry: false
  });

  const teams = useQuery({
    queryKey: ['nfl', 'yahoo-teams', league?.league_key],
    queryFn: () => fetchYahooTeams(league!.league_key),
    enabled: league != null,
    retry: false
  });

  async function onOpenAuth() {
    setError(null);
    try {
      const { url } = await fetchYahooAuthUrl();
      window.open(url, '_blank', 'noopener');
    } catch {
      setError(
        'Yahoo credentials are not configured on the backend (YAHOO_CLIENT_ID / YAHOO_CLIENT_SECRET).'
      );
    }
  }

  async function onPasteCode() {
    setConnecting(true);
    setError(null);
    try {
      await connectYahoo(code);
      setCode('');
      await qc.invalidateQueries({ queryKey: ['nfl', 'yahoo-status'] });
    } catch {
      setError('Yahoo rejected that code — reopen the authorize link and try again.');
    } finally {
      setConnecting(false);
    }
  }

  const myTeam = teams.data?.teams.find((t) => t.is_my_team);

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>Import a Yahoo league</CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        {status.isLoading && (
          <Icons.spinner className='text-muted-foreground h-5 w-5 animate-spin' />
        )}

        {status.data && !status.data.connected && (
          <div className='space-y-2'>
            <p className='text-muted-foreground text-sm'>
              Connect the Yahoo account once; leagues and rosters import from
              the Yahoo Fantasy API afterwards.
            </p>
            <div className='flex flex-wrap items-center gap-2'>
              <Button onClick={onOpenAuth}>Authorize with Yahoo</Button>
              {status.data.redirect_mode === 'oob' && (
                <>
                  <Input
                    placeholder='Paste the code Yahoo shows you'
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className='h-9 w-64'
                  />
                  <Button
                    variant='secondary'
                    disabled={!code || connecting}
                    onClick={onPasteCode}
                  >
                    {connecting ? 'Connecting...' : 'Connect'}
                  </Button>
                </>
              )}
            </div>
            {status.data.redirect_mode === 'callback' && (
              <p className='text-muted-foreground text-xs'>
                After authorizing, Yahoo redirects to the backend and stores
                the grant — refresh this page.
              </p>
            )}
          </div>
        )}

        {error && <p className='text-sm text-red-500'>{error}</p>}

        {status.data?.connected && (
          <div className='space-y-3'>
            <p className='text-sm'>
              <Badge variant='secondary' className='mr-2'>
                Connected
              </Badge>
              Pick a league to import.
            </p>
            {leagues.isLoading && (
              <Icons.spinner className='text-muted-foreground h-5 w-5 animate-spin' />
            )}
            <div className='flex flex-wrap gap-2'>
              {leagues.data?.map((l) => (
                <Button
                  key={l.league_key}
                  variant={
                    league?.league_key === l.league_key ? 'default' : 'outline'
                  }
                  size='sm'
                  onClick={() => setLeague(l)}
                >
                  {l.name || l.league_id}
                </Button>
              ))}
              {leagues.data?.length === 0 && (
                <p className='text-muted-foreground text-sm'>
                  No NFL leagues found for this season on the connected
                  account.
                </p>
              )}
            </div>

            {teams.isFetching && (
              <Icons.spinner className='text-muted-foreground h-5 w-5 animate-spin' />
            )}
            {teams.data && (
              <div className='grid gap-2 md:grid-cols-2 lg:grid-cols-3'>
                {teams.data.teams.map((t) => (
                  <div
                    key={t.team_key}
                    className={`rounded-md border px-3 py-2 text-sm ${t.is_my_team ? 'border-emerald-500' : ''}`}
                  >
                    <div className='flex items-center justify-between'>
                      <span className='font-medium'>{t.name}</span>
                      {t.is_my_team && <Badge>Your team</Badge>}
                    </div>
                    <p className='text-muted-foreground text-xs'>
                      {t.roster.length} players
                    </p>
                  </div>
                ))}
              </div>
            )}
            {myTeam && myTeam.roster.length > 0 && (
              <div>
                <h4 className='mb-1 text-sm font-medium'>Your roster</h4>
                <div className='flex flex-wrap gap-1'>
                  {myTeam.roster.map((p, i) => (
                    <Badge
                      key={`${p.player_name}-${i}`}
                      variant={
                        p.selected_position && p.selected_position !== 'BN'
                          ? 'default'
                          : 'secondary'
                      }
                    >
                      {p.position} {p.player_name}
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
