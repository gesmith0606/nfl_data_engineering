import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { MultiCompareTable } from '@/features/nfl/components/multi-compare-table';
import { Suspense } from 'react';

export default function ProbeCMultiCompareOnly() {
  return (
    <div>
      <p>PROBE C — MultiCompareTable alone</p>
      <Suspense fallback={<RouteSkeleton rows={5} />}>
        <MultiCompareTable />
      </Suspense>
    </div>
  );
}
