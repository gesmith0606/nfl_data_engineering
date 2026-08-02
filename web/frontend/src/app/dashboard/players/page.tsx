import PageContainer from '@/components/layout/page-container';
import { PlayerSearch } from '@/features/nfl/components/player-search';

export const metadata = {
  title: 'Players - NFL Analytics'
};

export default function PlayersPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Player Search'
      pageDescription='Search and view detailed player projections'
    >
      <PlayerSearch />
    </PageContainer>
  );
}
