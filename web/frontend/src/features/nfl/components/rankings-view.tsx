'use client';

import PageContainer from '@/components/layout/page-container';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PremiumUpsell } from '@/features/billing/components/premium-upsell';
import { MultiCompareTable } from '@/features/nfl/components/multi-compare-table';
import { RankingsTable } from '@/features/nfl/components/rankings-table';
import { FadeIn } from '@/lib/motion-primitives';
import { Suspense } from 'react';

/**
 * Rankings view. "Our Rankings" is free (marketing surface); the multi-source
 * compare tab is premium (PLAN 2 tier split) — the server page decides
 * `compareLocked` from Clerk metadata, so the client never fetches compare
 * data for locked sessions.
 */
export function RankingsView({
  compareLocked,
  signedIn
}: {
  compareLocked: boolean;
  signedIn: boolean;
}) {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Season Rankings'
      pageDescription='Our season-long rankings — and how we compare to ESPN, Sleeper, Yahoo, Draft Sharks, and FTN'
    >
      <Suspense>
        <FadeIn>
          <Tabs defaultValue='ours' className='w-full'>
            <TabsList>
              <TabsTrigger value='ours'>Our Rankings</TabsTrigger>
              <TabsTrigger value='compare'>Compare Sources</TabsTrigger>
            </TabsList>
            <TabsContent value='ours' className='mt-4'>
              <RankingsTable />
            </TabsContent>
            <TabsContent value='compare' className='mt-4'>
              {compareLocked ? (
                <PremiumUpsell surface='multi-compare' signedIn={signedIn} />
              ) : (
                <MultiCompareTable />
              )}
            </TabsContent>
          </Tabs>
        </FadeIn>
      </Suspense>
    </PageContainer>
  );
}
