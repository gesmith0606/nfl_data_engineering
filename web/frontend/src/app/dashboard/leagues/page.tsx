import PageContainer from '@/components/layout/page-container';
import { SleeperLeagueView } from '@/features/nfl/components/sleeper-league-view';
import { FadeIn } from '@/lib/motion-primitives';

export const metadata = {
  title: 'Your Sleeper Leagues',
  description:
    'Connect your Sleeper account to import rosters and get personalized AI advisor recommendations.'
};

export default function LeaguesPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Your Leagues'
      pageDescription='Connect your Sleeper account for personalized roster + advisor context.'
    >
      <FadeIn>
        <SleeperLeagueView />
      </FadeIn>
    </PageContainer>
  );
}
