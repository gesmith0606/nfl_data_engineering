import PageContainer from '@/components/layout/page-container';
import { OverviewStatCards } from '@/features/nfl/components/stat-cards';
import { MAEByPositionChart } from '@/features/nfl/components/mae-chart';
import { WeeklyAccuracyChart } from '@/features/nfl/components/accuracy-chart';
import { FadeIn } from '@/lib/motion-primitives';

export const metadata = {
  title: 'NFL Analytics Dashboard'
};

export default function Dashboard() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='NFL Analytics Dashboard'
      pageDescription='Model accuracy, tests passing, ATS performance, and player coverage at a glance'
    >
      <FadeIn className='flex flex-1 flex-col gap-[var(--gap-stack)]'>
        <OverviewStatCards />

        <div className='grid grid-cols-1 gap-[var(--gap-stack)] md:grid-cols-2'>
          <FadeIn delay={0.18} rise={6}>
            <MAEByPositionChart />
          </FadeIn>
          <FadeIn delay={0.24} rise={6}>
            <WeeklyAccuracyChart />
          </FadeIn>
        </div>
      </FadeIn>
    </PageContainer>
  );
}
