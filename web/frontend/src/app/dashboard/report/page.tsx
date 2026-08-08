import PageContainer from '@/components/layout/page-container';
import { WeeklyReportView } from '@/features/nfl/components/weekly-report-view';

export const metadata = {
  title: 'Weekly Report',
  description:
    'Auto-generated weekly digest: top projected players, injury watch, matchup spotlight, and boom/bust plays.'
};

export default function WeeklyReportPage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Weekly Report'
      pageDescription='Top projections, injury watch, matchup spotlight, and boom/bust plays for the current week'
    >
      <WeeklyReportView />
    </PageContainer>
  );
}
