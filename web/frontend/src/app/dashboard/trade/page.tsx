import PageContainer from '@/components/layout/page-container';
import { TradeAnalyzerView } from '@/features/nfl/components/trade-analyzer-view';

export const metadata = {
  title: 'Trade Analyzer',
  description:
    'Evaluate fantasy football trades with rest-of-season model projections: per-player ROS value, side totals, and a fairness verdict.'
};

export default function TradePage() {
  return (
    <PageContainer
      scrollable={true}
      pageTitle='Trade Analyzer'
      pageDescription='Rest-of-season model value for each side of a trade, with a verdict'
    >
      <TradeAnalyzerView />
    </PageContainer>
  );
}
