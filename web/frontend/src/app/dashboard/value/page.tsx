import PageContainer from '@/components/layout/page-container';
import { RosValueView } from '@/features/nfl/components/ros-value-view';

export const metadata = {
  title: 'Player Value',
  description:
    'Rest-of-season value rankings and VORP-based auction dollar values from the projection model.'
};

export default function ValuePage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Player Value'
      pageDescription='Rest-of-season rankings and auction dollar values'
    >
      <RosValueView />
    </PageContainer>
  );
}
