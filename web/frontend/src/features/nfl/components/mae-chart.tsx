'use client';

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent
} from '@/components/ui/chart';
import modelMetrics from '../config/model-metrics.json';

const maeData = [
  ...modelMetrics.positions.map((p, i) => ({
    position: p.position,
    mae: p.mae,
    fill: `var(--chart-${i + 1})`
  })),
  { position: 'Overall', mae: modelMetrics.overall.mae, fill: 'var(--chart-5)' }
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
