import PageContainer from '@/components/layout/page-container';
import { OverviewStatCards } from '@/features/nfl/components/stat-cards';
import { MAEByPositionChart } from '@/features/nfl/components/mae-chart';
import { WeeklyAccuracyChart } from '@/features/nfl/components/accuracy-chart';

export const metadata = {
  title: 'NFL Analytics Dashboard'
};

export default function Dashboard() {
  return (
    <PageContainer>
      <div className='flex flex-1 flex-col space-y-4'>
        <div className='flex items-center justify-between'>
          <h2 className='text-2xl font-bold tracking-tight'>NFL Analytics Dashboard</h2>
        </div>

        <OverviewStatCards />

        <div className='grid grid-cols-1 gap-4 md:grid-cols-2'>
          <MAEByPositionChart />
          <WeeklyAccuracyChart />
        </div>
      </div>
    </PageContainer>
  );
}
