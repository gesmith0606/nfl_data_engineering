import PageContainer from '@/components/layout/page-container';
import { StartSitView } from '@/features/nfl/components/start-sit-view';

export const metadata = {
  title: 'Start/Sit',
  description:
    'Who should I start? Head-to-head weekly comparison: projections, floor/ceiling bands, opponent rank vs position, and injury status.'
};

export default function StartSitPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Start/Sit'
      pageDescription='Head-to-head weekly comparison with floor/ceiling bands and matchup context'
    >
      <StartSitView />
    </PageContainer>
  );
}
