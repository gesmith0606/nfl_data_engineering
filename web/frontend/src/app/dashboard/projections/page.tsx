import PageContainer from '@/components/layout/page-container';
import { ProjectionsTable } from '@/features/nfl/components/projections-table';
import { Suspense } from 'react';

export const metadata = {
  title: 'Projections - NFL Analytics'
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
