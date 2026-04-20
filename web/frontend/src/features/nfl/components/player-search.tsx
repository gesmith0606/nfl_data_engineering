'use client';

import { useQuery } from '@tanstack/react-query';
import { playerSearchQueryOptions } from '../api/queries';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import Link from 'next/link';
import { useState } from 'react';
import { FadeIn, HoverLift, Stagger, DataLoadReveal } from '@/lib/motion-primitives';

export function PlayerSearch() {
  const [query, setQuery] = useState('');

  const { data: results, isLoading } = useQuery(playerSearchQueryOptions(query));
  const showResults = query.length >= 2 && (isLoading || (results !== undefined));

  return (
    <FadeIn className='space-y-[var(--gap-stack)]'>
      <div className='relative'>
        <Icons.search className='text-muted-foreground absolute left-[var(--space-3)] top-1/2 h-[var(--space-4)] w-[var(--space-4)] -translate-y-1/2' />
        <Input
          placeholder='Search players by name...'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className='pl-[var(--space-10)] h-9'
        />
      </div>

      {showResults && (
        <DataLoadReveal
          loading={isLoading}
          skeleton={
            <div className='flex items-center justify-center py-[var(--space-8)]'>
              <Icons.spinner className='text-muted-foreground h-[var(--space-6)] w-[var(--space-6)] animate-spin' />
            </div>
          }
        >
          {results && results.length > 0 ? (
            <Stagger className='grid grid-cols-1 gap-[var(--space-2)] md:grid-cols-2 lg:grid-cols-3'>
              {results.map((player) => (
                <Link key={player.player_id} href={`/dashboard/players/${player.player_id}`}>
                  <HoverLift>
                    <Card className='transition-colors hover:bg-accent cursor-pointer'>
                      <CardContent className='flex items-center justify-between p-[var(--pad-card)]'>
                        <div className='flex items-center gap-[var(--space-3)]'>
                          <Badge variant='outline'>{player.position}</Badge>
                          <div>
                            <div className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium'>
                              {player.player_name}
                            </div>
                            <div className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                              {player.team}
                            </div>
                          </div>
                        </div>
                        <Icons.chevronRight className='text-muted-foreground h-[var(--space-4)] w-[var(--space-4)]' />
                      </CardContent>
                    </Card>
                  </HoverLift>
                </Link>
              ))}
            </Stagger>
          ) : (
            <div className='flex flex-col items-center justify-center py-[var(--space-12)]'>
              <Icons.info className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
              <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                No players found matching &ldquo;{query}&rdquo;
              </p>
            </div>
          )}
        </DataLoadReveal>
      )}

      {query.length < 2 && (
        <div className='flex flex-col items-center justify-center py-[var(--space-12)]'>
          <Icons.search className='text-muted-foreground mb-[var(--space-2)] h-[var(--space-8)] w-[var(--space-8)]' />
          <p className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
            Type at least 2 characters to search for players
          </p>
        </div>
      )}
    </FadeIn>
  );
}
