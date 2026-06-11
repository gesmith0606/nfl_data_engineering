'use client';

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent
} from '@/components/ui/chart';
import modelMetrics from '../config/model-metrics.json';

const chartConfig = {
  mae: {
    label: 'MAE',
    color: 'var(--chart-1)'
  }
} satisfies ChartConfig;

export function WeeklyAccuracyChart() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Weekly Projection Accuracy</CardTitle>
        <CardDescription>
          MAE by week, {modelMetrics.overall.seasons} backtest (lower is better)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig}>
          <AreaChart accessibilityLayer data={modelMetrics.weeklyMae}>
            <CartesianGrid vertical={false} strokeDasharray='3 3' />
            <XAxis dataKey='week' tickLine={false} axisLine={false} tickMargin={8} />
            <YAxis tickLine={false} axisLine={false} tickMargin={8} domain={[3, 7]} />
            <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
            <Area
              dataKey='mae'
              type='monotone'
              fill='var(--color-mae)'
              fillOpacity={0.2}
              stroke='var(--color-mae)'
              strokeWidth={2}
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
