import PageContainer from '@/components/layout/page-container';
import { SleeperLeagueView } from '@/features/nfl/components/sleeper-league-view';
import { FadeIn } from '@/lib/motion-primitives';

export const metadata = {
  title: 'Your Leagues',
  description:
    'Connect your Sleeper account to import rosters and get personalized AI advisor recommendations.'
};

export default function LeaguesPage() {
  return (
    <PageContainer
      scrollable={true}
      stickyHeader={false}
      pageTitle='Your Leagues'
      pageDescription='Connect your Sleeper account for personalized roster + advisor context.'
    >
      <FadeIn>
        <SleeperLeagueView />
      </FadeIn>
    </PageContainer>
  );
}
