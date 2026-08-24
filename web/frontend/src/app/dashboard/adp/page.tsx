import PageContainer from '@/components/layout/page-container';
import { AdpRankingsView } from '@/features/draft/components/adp-rankings-view';

export const metadata = {
  title: 'ADP Rankings',
  description:
    'Average draft position from real drafts (FFC, Sleeper, ESPN) side by side with our model rank — see where the market and the model disagree.'
};

export default function AdpPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='ADP Rankings'
      pageDescription='Where the market drafts every player — and where we disagree'
    >
      <AdpRankingsView />
    </PageContainer>
  );
}
