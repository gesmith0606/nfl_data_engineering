'use client';

import { useQuery } from '@tanstack/react-query';
import { playerSearchQueryOptions } from '../api/queries';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import Link from 'next/link';
import { useState } from 'react';

export function PlayerSearch() {
  const [query, setQuery] = useState('');

  const { data: results, isLoading } = useQuery(playerSearchQueryOptions(query));

  return (
    <div className='space-y-4'>
      <div className='relative'>
        <Icons.search className='text-muted-foreground absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2' />
        <Input
          placeholder='Search players by name...'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className='pl-10'
        />
      </div>

      {isLoading && query.length >= 2 && (
        <div className='flex items-center justify-center py-8'>
          <Icons.spinner className='text-muted-foreground h-6 w-6 animate-spin' />
        </div>
      )}

      {results && results.length > 0 && (
        <div className='grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3'>
          {results.map((player) => (
            <Link key={player.player_id} href={`/dashboard/players/${player.player_id}`}>
              <Card className='transition-colors hover:bg-accent cursor-pointer'>
                <CardContent className='flex items-center justify-between p-4'>
                  <div className='flex items-center gap-3'>
                    <Badge variant='outline'>{player.position}</Badge>
                    <div>
                      <div className='font-medium'>{player.player_name}</div>
                      <div className='text-muted-foreground text-xs'>{player.team}</div>
                    </div>
                  </div>
                  <Icons.chevronRight className='text-muted-foreground h-4 w-4' />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {results && results.length === 0 && query.length >= 2 && (
        <div className='flex flex-col items-center justify-center py-12'>
          <Icons.info className='text-muted-foreground mb-2 h-8 w-8' />
          <p className='text-muted-foreground text-sm'>No players found matching "{query}"</p>
        </div>
      )}

      {query.length < 2 && (
        <div className='flex flex-col items-center justify-center py-12'>
          <Icons.search className='text-muted-foreground mb-2 h-8 w-8' />
          <p className='text-muted-foreground text-sm'>
            Type at least 2 characters to search for players
          </p>
        </div>
      )}
    </div>
  );
}
