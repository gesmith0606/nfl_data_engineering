import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { RankingsTable } from '@/features/nfl/components/rankings-table';
import { FadeIn } from '@/lib/motion-primitives';
import { Suspense } from 'react';

export default function ProbeEFadeInWrapped() {
  return (
    <div>
      <p>PROBE E — FadeIn + RankingsTable, no Tabs/PremiumUpsell/MultiCompareTable</p>
      <Suspense fallback={<RouteSkeleton rows={5} />}>
        <FadeIn>
          <RankingsTable />
        </FadeIn>
      </Suspense>
    </div>
  );
}
