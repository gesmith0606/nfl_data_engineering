import PageContainer from '@/components/layout/page-container';
import { GameResultsGrid } from '@/features/nfl/components/game-results';
import { FadeIn } from '@/lib/motion-primitives';
import { Suspense } from 'react';

export const metadata = {
  title: 'NFL Scores',
  description:
    'NFL game results with final scores by season and week. Archive view of completed games.',
  openGraph: {
    title: 'NFL Scores | NFL Analytics',
    description:
      'NFL game results with final scores by season and week. Archive view of completed games.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/games'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: 'NFL Scores',
    description: 'NFL final scores and game results by week.'
  }
};

export default function GamesPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Scores'
      pageDescription='Final scores and game results by week'
    >
      <Suspense>
        <FadeIn>
          <GameResultsGrid />
        </FadeIn>
      </Suspense>
    </PageContainer>
  );
}
