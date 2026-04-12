import PageContainer from '@/components/layout/page-container';
import { ProjectionsTable } from '@/features/nfl/components/projections-table';
import { Suspense } from 'react';

export const metadata = {
  title: '2026 NFL Fantasy Projections',
  description:
    'Weekly fantasy football projections with PPR, Half-PPR, and Standard scoring. Floor/ceiling ranges for all skill positions.'
};

export default function ProjectionsPage() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='Fantasy Projections'
      pageDescription='Weekly fantasy point projections with floor/ceiling ranges'
    >
      <Suspense>
        <ProjectionsTable />
      </Suspense>
    </PageContainer>
  );
}
