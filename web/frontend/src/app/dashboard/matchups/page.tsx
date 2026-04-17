import PageContainer from '@/components/layout/page-container';
import { MatchupView } from '@/features/nfl/components/matchup-view';
import { Suspense } from 'react';

export const metadata = {
  title: 'Team Matchups - NFL Analytics',
  description:
    'Madden-style team matchup view with offensive projections vs opposing defense. Player ratings, injury status, and matchup advantages.',
  openGraph: {
    title: 'Team Matchups | NFL Analytics',
    description:
      'Madden-style split-screen team matchup view with player ratings and fantasy projections.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/matchups'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: 'Team Matchups',
    description: 'NFL team matchup analysis with Madden-style player ratings and projections.'
  }
};

export default function MatchupsPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Team Matchups'
      pageDescription='Madden-style offense vs defense breakdown with player ratings and matchup advantages'
    >
      <Suspense>
        <MatchupView />
      </Suspense>
    </PageContainer>
  );
}
