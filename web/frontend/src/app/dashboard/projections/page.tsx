import PageContainer from '@/components/layout/page-container';
import { ProjectionsTable } from '@/features/nfl/components/projections-table';
import { FadeIn } from '@/lib/motion-primitives';
import { Suspense } from 'react';

export const metadata = {
  title: '2026 NFL Fantasy Projections',
  description:
    'Weekly fantasy football projections with PPR, Half-PPR, and Standard scoring. Floor/ceiling ranges for all skill positions.',
  openGraph: {
    title: '2026 NFL Fantasy Projections | NFL Analytics',
    description:
      'Weekly fantasy football projections with PPR, Half-PPR, and Standard scoring. Floor/ceiling ranges for all skill positions.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/projections'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: '2026 NFL Fantasy Projections',
    description: 'Weekly fantasy football projections with PPR, Half-PPR, and Standard scoring.'
  }
};

export default function ProjectionsPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Fantasy Projections'
      pageDescription='Weekly fantasy point projections with floor/ceiling ranges'
    >
      <Suspense>
        <FadeIn>
          <ProjectionsTable />
        </FadeIn>
      </Suspense>
    </PageContainer>
  );
}
