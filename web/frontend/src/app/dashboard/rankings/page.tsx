'use client';

import PageContainer from '@/components/layout/page-container';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { MultiCompareTable } from '@/features/nfl/components/multi-compare-table';
import { RankingsTable } from '@/features/nfl/components/rankings-table';
import { FadeIn } from '@/lib/motion-primitives';
import { Suspense } from 'react';

export default function RankingsPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Season Rankings'
      pageDescription='Our season-long rankings — and how we compare to ESPN, Sleeper, and Yahoo'
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
              <MultiCompareTable />
            </TabsContent>
          </Tabs>
        </FadeIn>
      </Suspense>
    </PageContainer>
  );
}
