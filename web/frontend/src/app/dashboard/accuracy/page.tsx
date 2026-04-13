import PageContainer from '@/components/layout/page-container';
import { AccuracyDashboard } from '@/features/nfl/components/accuracy-dashboard';

export const metadata = {
  title: 'Model Accuracy',
  description:
    'Fantasy projection model accuracy: MAE, RMSE, and bias by position. Backtest results across 2022-2024 seasons (Weeks 3-18, Half-PPR).',
  openGraph: {
    title: 'Model Accuracy | NFL Analytics',
    description:
      'Fantasy projection model accuracy: MAE, RMSE, and bias by position. Backtest results across 2022-2024 seasons.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/accuracy'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: 'Model Accuracy',
    description: 'Fantasy projection model accuracy: MAE, RMSE, bias by position (2022-2024).'
  }
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
