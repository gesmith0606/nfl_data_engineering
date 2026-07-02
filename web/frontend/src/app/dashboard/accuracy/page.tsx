import PageContainer from '@/components/layout/page-container';
import { AccuracyDashboard } from '@/features/nfl/components/accuracy-dashboard';
import { FadeIn } from '@/lib/motion-primitives';

export const metadata = {
  title: 'Model vs. Consensus',
  description:
    'Our fantasy projections vs the Sleeper expert consensus: matched-pairs MAE by position across 2022-2024 (10,417 player-weeks, Half-PPR). We beat the consensus overall.',
  openGraph: {
    title: 'Model vs. Consensus | NFL Analytics',
    description:
      'Our fantasy projections benchmarked against the expert consensus — matched-pairs MAE by position (2022-2024). We beat the consensus overall.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/accuracy'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: 'Model vs. Consensus',
    description:
      'Our projections vs the expert consensus — matched-pairs MAE by position (2022-2024).'
  }
};

export default function AccuracyPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Model vs. Consensus'
      pageDescription='Our projections benchmarked head-to-head against the expert consensus, graded weekly in-season'
    >
      <FadeIn>
        <AccuracyDashboard />
      </FadeIn>
    </PageContainer>
  );
}
