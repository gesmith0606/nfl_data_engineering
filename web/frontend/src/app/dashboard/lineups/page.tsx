import PageContainer from '@/components/layout/page-container';
import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { LineupView } from '@/features/nfl/components/lineup-view';
import { Suspense } from 'react';

export const metadata = {
  title: 'Lineups - NFL Analytics'
};

export default function LineupsPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Team Lineups'
      pageDescription='Field view visualization with projected fantasy points'
    >
      <Suspense fallback={<RouteSkeleton rows={2} />}>
        <LineupView />
      </Suspense>
    </PageContainer>
  );
}
