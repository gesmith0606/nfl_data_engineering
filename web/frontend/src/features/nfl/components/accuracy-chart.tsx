'use client';

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent
} from '@/components/ui/chart';

const weeklyAccuracy = [
  { week: 'W1', mae: 5.8, correlation: 0.42 },
  { week: 'W2', mae: 5.3, correlation: 0.45 },
  { week: 'W3', mae: 5.1, correlation: 0.48 },
  { week: 'W4', mae: 4.9, correlation: 0.50 },
  { week: 'W5', mae: 4.7, correlation: 0.52 },
  { week: 'W6', mae: 4.6, correlation: 0.51 },
  { week: 'W7', mae: 4.8, correlation: 0.49 },
  { week: 'W8', mae: 4.5, correlation: 0.53 },
  { week: 'W9', mae: 4.7, correlation: 0.51 },
  { week: 'W10', mae: 4.4, correlation: 0.55 },
  { week: 'W11', mae: 4.6, correlation: 0.52 },
  { week: 'W12', mae: 4.3, correlation: 0.54 },
  { week: 'W13', mae: 4.5, correlation: 0.53 },
  { week: 'W14', mae: 4.2, correlation: 0.56 },
  { week: 'W15', mae: 4.4, correlation: 0.54 },
  { week: 'W16', mae: 4.1, correlation: 0.57 },
  { week: 'W17', mae: 4.3, correlation: 0.55 },
  { week: 'W18', mae: 4.5, correlation: 0.52 }
];

const chartConfig = {
  mae: {
    label: 'MAE',
    color: 'var(--chart-1)'
  },
  correlation: {
    label: 'Correlation',
    color: 'var(--chart-2)'
  }
} satisfies ChartConfig;

export function WeeklyAccuracyChart() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Weekly Projection Accuracy</CardTitle>
        <CardDescription>MAE trend over the season (lower is better)</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig}>
          <AreaChart accessibilityLayer data={weeklyAccuracy}>
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
