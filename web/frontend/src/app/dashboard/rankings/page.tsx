import PageContainer from '@/components/layout/page-container';
import { RankingsTable } from '@/features/nfl/components/rankings-table';
import { FadeIn } from '@/lib/motion-primitives';
import { Suspense } from 'react';

export const metadata = {
  title: '2026 NFL Season Rankings',
  description:
    'Season-long fantasy football player rankings with tier groupings, floor/ceiling ranges, and multi-format scoring.',
  openGraph: {
    title: '2026 NFL Season Rankings | NFL Analytics',
    description:
      'Season-long fantasy football player rankings with tier groupings, floor/ceiling ranges, and multi-format scoring.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/rankings'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: '2026 NFL Season Rankings',
    description: 'Season-long fantasy player rankings with tier groupings and floor/ceiling ranges.'
  }
};

export default function RankingsPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Season Rankings'
      pageDescription='Full roster rankings by season-long projected fantasy points'
    >
      <Suspense>
        <FadeIn>
          <RankingsTable />
        </FadeIn>
      </Suspense>
    </PageContainer>
  );
}
