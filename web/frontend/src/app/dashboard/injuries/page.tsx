import PageContainer from '@/components/layout/page-container';
import { InjuryDepthView } from '@/features/nfl/components/injury-depth-view';

export const metadata = {
  title: 'Injuries & Depth',
  description:
    'Weekly fantasy-relevant injury report and current team depth charts for all 32 teams.'
};

export default function InjuriesPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Injuries & Depth Charts'
      pageDescription='Weekly injury designations and current depth charts'
    >
      <InjuryDepthView />
    </PageContainer>
  );
}
