import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { GameResultsGrid } from '@/features/nfl/components/game-results';
import { FadeIn } from '@/lib/motion-primitives';
import { Suspense } from 'react';

export default function ProbeFGameResults() {
  return (
    <div>
      <p>PROBE F — exact current /dashboard/games setup, to confirm cross-route reproduction</p>
      <Suspense fallback={<RouteSkeleton rows={4} />}>
        <FadeIn>
          <GameResultsGrid />
        </FadeIn>
      </Suspense>
    </div>
  );
}
