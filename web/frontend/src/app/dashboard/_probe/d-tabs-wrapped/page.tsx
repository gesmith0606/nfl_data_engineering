import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RankingsTable } from '@/features/nfl/components/rankings-table';
import { Suspense } from 'react';

export default function ProbeDTabsWrapped() {
  return (
    <div>
      <p>PROBE D — Tabs + RankingsTable, no FadeIn/PremiumUpsell/MultiCompareTable</p>
      <Suspense fallback={<RouteSkeleton rows={5} />}>
        <Tabs defaultValue='ours' className='w-full'>
          <TabsList>
            <TabsTrigger value='ours'>Our Rankings</TabsTrigger>
            <TabsTrigger value='compare'>Compare Sources</TabsTrigger>
          </TabsList>
          <TabsContent value='ours' className='mt-4'>
            <RankingsTable />
          </TabsContent>
          <TabsContent value='compare' className='mt-4'>
            <div>compare stub</div>
          </TabsContent>
        </Tabs>
      </Suspense>
    </div>
  );
}
