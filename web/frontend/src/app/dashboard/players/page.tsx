import PageContainer from '@/components/layout/page-container';
import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { PlayerSearch } from '@/features/nfl/components/player-search';
import { Suspense } from 'react';

export const metadata = {
  title: 'Players - NFL Analytics'
};

export default function PlayersPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Player Search'
      pageDescription='Search and view detailed player projections'
    >
      <Suspense fallback={<RouteSkeleton rows={2} />}>
        <PlayerSearch />
      </Suspense>
    </PageContainer>
  );
}
