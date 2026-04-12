import PageContainer from '@/components/layout/page-container';
import { PredictionCardGrid } from '@/features/nfl/components/prediction-cards';
import { Suspense } from 'react';

export const metadata = {
  title: 'NFL Game Predictions',
  description:
    'NFL game predictions with spread and total edges. Model-vs-Vegas comparison with confidence tiers and ATS picks.'
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
