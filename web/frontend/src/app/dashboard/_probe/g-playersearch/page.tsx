import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { PlayerSearch } from '@/features/nfl/components/player-search';
import { Suspense } from 'react';

export default function ProbeGPlayerSearch() {
  return (
    <div>
      <p>PROBE G — PlayerSearch alone (simplest broken component, no nuqs at all)</p>
      <Suspense fallback={<RouteSkeleton rows={2} />}>
        <PlayerSearch />
      </Suspense>
    </div>
  );
}
