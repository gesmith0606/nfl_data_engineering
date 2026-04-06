import PageContainer from '@/components/layout/page-container';
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
      <Suspense>
        <LineupView />
      </Suspense>
    </PageContainer>
  );
}
