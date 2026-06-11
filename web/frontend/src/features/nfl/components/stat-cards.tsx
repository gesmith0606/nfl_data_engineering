'use client';

import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardAction,
  CardFooter
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Icons } from '@/components/icons';
import { Stagger, HoverLift } from '@/lib/motion-primitives';
import modelMetrics from '../config/model-metrics.json';

interface StatCardProps {
  title: string;
  value: string;
  description: string;
  trend?: string;
  trendDirection?: 'up' | 'down';
}

function StatCard({ title, value, description, trend, trendDirection = 'up' }: StatCardProps) {
  const TrendIcon = trendDirection === 'up' ? Icons.trendingUp : Icons.trendingDown;

  return (
    <HoverLift lift={3} className='h-full'>
      <Card className='@container/card h-full'>
        <CardHeader>
          <CardDescription>{title}</CardDescription>
          <CardTitle className='text-[length:var(--fs-h2)] leading-[var(--lh-h2)] font-semibold tabular-nums @[250px]/card:text-[length:var(--fs-h1)] @[250px]/card:leading-[var(--lh-h1)]'>
            {value}
          </CardTitle>
          {trend && (
            <CardAction>
              <Badge variant='outline'>
                <TrendIcon />
                {trend}
              </Badge>
            </CardAction>
          )}
        </CardHeader>
        <CardFooter className='flex-col items-start gap-[var(--space-1)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          <div className='text-muted-foreground'>{description}</div>
        </CardFooter>
      </Card>
    </HoverLift>
  );
}

export function OverviewStatCards() {
  return (
    <Stagger
      step={0.05}
      className='*:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card dark:*:data-[slot=card]:bg-card grid grid-cols-1 gap-[var(--gap-stack)] *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:shadow-[var(--elevation-flat)] md:grid-cols-2 lg:grid-cols-4'
    >
      <StatCard
        title='Projection MAE'
        value={modelMetrics.overall.mae.toFixed(2)}
        description={`Fantasy points mean absolute error (${modelMetrics.overall.seasons} backtest)`}
        trend='-3.0% in v4.2'
        trendDirection='down'
      />
      <StatCard
        title='Tests Passing'
        value={modelMetrics.testsPassing.toLocaleString()}
        description='Full test suite coverage'
        trend='100%'
        trendDirection='up'
      />
      <StatCard
        title='ATS Accuracy'
        value={`${modelMetrics.atsAccuracy.value.toFixed(1)}%`}
        description='Against the spread (sealed 2024 holdout)'
        trend='+3.0%'
        trendDirection='up'
      />
      <StatCard
        title='Players Tracked'
        value='569'
        description='Across all NFL positions'
      />
    </Stagger>
  );
}
