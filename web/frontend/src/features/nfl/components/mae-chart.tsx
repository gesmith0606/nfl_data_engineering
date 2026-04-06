'use client';

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent
} from '@/components/ui/chart';

const maeData = [
  { position: 'QB', mae: 6.58, fill: 'var(--chart-1)' },
  { position: 'RB', mae: 5.06, fill: 'var(--chart-2)' },
  { position: 'WR', mae: 4.85, fill: 'var(--chart-3)' },
  { position: 'TE', mae: 3.77, fill: 'var(--chart-4)' },
  { position: 'Overall', mae: 4.91, fill: 'var(--chart-5)' }
];

const chartConfig = {
  mae: {
    label: 'MAE',
    color: 'var(--chart-1)'
  }
} satisfies ChartConfig;

export function MAEByPositionChart() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>MAE by Position</CardTitle>
        <CardDescription>Fantasy projection accuracy (lower is better)</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig}>
          <BarChart accessibilityLayer data={maeData}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey='position' tickLine={false} axisLine={false} tickMargin={8} />
            <YAxis tickLine={false} axisLine={false} tickMargin={8} domain={[0, 8]} />
            <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
            <Bar dataKey='mae' radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
