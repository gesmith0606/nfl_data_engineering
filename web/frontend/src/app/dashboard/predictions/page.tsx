import PageContainer from '@/components/layout/page-container';
import { PredictionCardGrid } from '@/features/nfl/components/prediction-cards';
import { Suspense } from 'react';

export const metadata = {
  title: 'NFL Game Predictions',
  description:
    'NFL game predictions with spread and total edges. Model-vs-Vegas comparison with confidence tiers and ATS picks.',
  openGraph: {
    title: 'NFL Game Predictions | NFL Analytics',
    description:
      'NFL game predictions with spread and total edges. Model-vs-Vegas comparison with confidence tiers and ATS picks.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/predictions'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: 'NFL Game Predictions',
    description: 'NFL game predictions vs. Vegas lines with confidence tiers and ATS picks.'
  }
};

export default function PredictionsPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Game Predictions'
      pageDescription='Model predictions with spread/total edges and confidence tiers'
    >
      <Suspense>
        <PredictionCardGrid />
      </Suspense>
    </PageContainer>
  );
}
