import PageContainer from '@/components/layout/page-container';
import { EspnImportCard } from '@/features/nfl/components/espn-import-card';
import { YahooConnectCard } from '@/features/nfl/components/yahoo-connect-card';
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
      <FadeIn className='space-y-4'>
        <SleeperLeagueView />
        <EspnImportCard />
        <YahooConnectCard />
      </FadeIn>
    </PageContainer>
  );
}
