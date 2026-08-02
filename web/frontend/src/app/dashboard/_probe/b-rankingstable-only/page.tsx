import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { RankingsTable } from '@/features/nfl/components/rankings-table';
import { Suspense } from 'react';

export default function ProbeBRankingsTableOnly() {
  return (
    <div>
      <p>PROBE B — RankingsTable alone, no FadeIn/Tabs/PremiumUpsell/MultiCompareTable</p>
      <Suspense fallback={<RouteSkeleton rows={5} />}>
        <RankingsTable />
      </Suspense>
    </div>
  );
}
