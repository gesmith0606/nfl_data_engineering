import PageContainer from '@/components/layout/page-container';
import { DynastyView } from '@/features/nfl/components/dynasty-view';

export const metadata = {
  title: 'Dynasty & Rookies',
  description:
    'Dynasty-value rankings (age-adjusted) and rookie-class rankings from the projection model.'
};

export default function DynastyPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Dynasty & Rookies'
      pageDescription='Age-adjusted dynasty value and rookie-class rankings'
    >
      <DynastyView />
    </PageContainer>
  );
}
