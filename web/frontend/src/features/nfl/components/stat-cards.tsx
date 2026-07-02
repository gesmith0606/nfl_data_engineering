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
  /**
   * CSS color expression for the left rail. Pass a wc accent with a chart
   * fallback (e.g. 'var(--wc-magenta, var(--chart-1))') so the card stays
   * on-brand in worldcup26 and themed everywhere else.
   */
  accent: string;
}

function StatCard({
  title,
  value,
  description,
  trend,
  trendDirection = 'up',
  accent
}: StatCardProps) {
  const TrendIcon = trendDirection === 'up' ? Icons.trendingUp : Icons.trendingDown;

  return (
    <HoverLift lift={3} className='h-full'>
      <Card className='@container/card relative h-full overflow-hidden'>
        <div
          aria-hidden
          className='absolute inset-y-[var(--space-2)] left-0 w-[3px] rounded-full'
          style={{ background: accent }}
        />
        <CardHeader>
          <CardDescription className='tracking-[0.06em] uppercase'>{title}</CardDescription>
          <CardTitle className='wc-display text-[length:var(--fs-h1)] leading-[var(--lh-h1)] tabular-nums @[250px]/card:text-[calc(var(--fs-h1)*1.35)] @[250px]/card:leading-[1.05]'>
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
        accent='var(--wc-magenta, var(--chart-1))'
      />
      <StatCard
        title='Tests Passing'
        value={modelMetrics.testsPassing.toLocaleString()}
        description='Full test suite coverage'
        trend='100%'
        trendDirection='up'
        accent='var(--wc-lime, var(--chart-3))'
      />
      <StatCard
        title='ATS Accuracy'
        value={`${modelMetrics.atsAccuracy.value.toFixed(1)}%`}
        description='Against the spread (sealed 2024 holdout)'
        trend='+3.0%'
        trendDirection='up'
        accent='var(--wc-cyan, var(--chart-2))'
      />
      <StatCard
        title='Players Tracked'
        value='569'
        description='Across all NFL positions'
        accent='var(--wc-gold, var(--chart-4))'
      />
    </Stagger>
  );
}
