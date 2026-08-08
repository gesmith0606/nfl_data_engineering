import PageContainer from '@/components/layout/page-container';
import { PlayerSearch } from '@/features/nfl/components/player-search';
import { WatchlistPanel } from '@/features/nfl/components/watchlist-panel';

export const metadata = {
  title: 'Players - NFL Analytics'
};

export default function PlayersPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Player Search'
      pageDescription='Search and view detailed player projections'
    >
      <div className='space-y-4'>
        <PlayerSearch />
        <WatchlistPanel />
      </div>
    </PageContainer>
  );
}
