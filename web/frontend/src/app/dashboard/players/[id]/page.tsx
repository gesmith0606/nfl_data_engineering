import PageContainer from '@/components/layout/page-container';
import { PlayerDetail } from '@/features/nfl/components/player-detail';
import { Suspense } from 'react';

export const metadata = {
  title: 'Player Detail',
  description:
    'NFL player fantasy projection detail: projected points, floor/ceiling range, stat breakdown, and injury status.'
};

type Props = {
  params: Promise<{ id: string }>;
};

export default async function PlayerDetailPage(props: Props) {
  const { id } = await props.params;

  return (
    <PageContainer scrollable={false} pageTitle='Player Detail'>
      <Suspense>
        <PlayerDetail playerId={id} />
      </Suspense>
    </PageContainer>
  );
}
