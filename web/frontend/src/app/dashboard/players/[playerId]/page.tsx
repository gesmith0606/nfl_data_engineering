import PageContainer from '@/components/layout/page-container';
import { PlayerProfile } from '@/features/nfl/components/player-profile';
import { Suspense } from 'react';

export const metadata = {
  title: 'Player Profile',
  description:
    'NFL player profile: bottom-line verdict, decorrelated percentile bars vs the position pool, and full game log.'
};

type Props = {
  params: Promise<{ playerId: string }>;
};

export default async function PlayerProfilePage(props: Props) {
  const { playerId } = await props.params;

  return (
    <PageContainer scrollable pageTitle='Player Profile'>
      <Suspense>
        <PlayerProfile playerId={playerId} />
      </Suspense>
    </PageContainer>
  );
}
