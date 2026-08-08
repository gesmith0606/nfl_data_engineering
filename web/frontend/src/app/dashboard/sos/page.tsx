import PageContainer from '@/components/layout/page-container';
import { SosGridView } from '@/features/nfl/components/sos-grid-view';

export const metadata = {
  title: 'Matchup Grid',
  description:
    'League-wide defense-vs-position grid: fantasy points allowed and rank for all 32 defenses against QB, RB, WR, and TE.'
};

export default function SosPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Matchup Grid'
      pageDescription='All 32 defenses ranked by fantasy points allowed to each position'
    >
      <SosGridView />
    </PageContainer>
  );
}
