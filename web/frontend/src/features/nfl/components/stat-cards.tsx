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
    <Card className='@container/card'>
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
  );
}

export function OverviewStatCards() {
  return (
    <div className='*:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card dark:*:data-[slot=card]:bg-card grid grid-cols-1 gap-[var(--gap-stack)] *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:shadow-[var(--elevation-flat)] md:grid-cols-2 lg:grid-cols-4'>
      <StatCard
        title='Projection MAE'
        value='4.77'
        description='Fantasy points mean absolute error'
        trend='-3.2%'
        trendDirection='down'
      />
      <StatCard
        title='Tests Passing'
        value='571'
        description='Full test suite coverage'
        trend='100%'
        trendDirection='up'
      />
      <StatCard
        title='ATS Accuracy'
        value='53.0%'
        description='Against the spread (2024 holdout)'
        trend='+3.0%'
        trendDirection='up'
      />
      <StatCard
        title='Players Tracked'
        value='500+'
        description='Across all NFL positions'
      />
    </div>
  );
}
