import PageContainer from '@/components/layout/page-container';
import { AccuracyDashboard } from '@/features/nfl/components/accuracy-dashboard';

export const metadata = {
  title: 'Model Accuracy - NFL Analytics'
};

export default function AccuracyPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Model Accuracy'
      pageDescription='Backtest results for fantasy projection models (2022-2024, Weeks 3-18, Half-PPR)'
    >
      <AccuracyDashboard />
    </PageContainer>
  );
}
