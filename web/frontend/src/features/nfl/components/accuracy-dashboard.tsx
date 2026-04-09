'use client';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardFooter,
  CardAction
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table';
import { Icons } from '@/components/icons';
import { WeeklyAccuracyChart } from './accuracy-chart';

/** Overall backtest metrics from Phase 54 (2022-2024, Weeks 3-18, Half-PPR). */
const OVERALL_METRICS = {
  mae: 4.77,
  rmse: 6.72,
  correlation: 0.510,
  bias: -0.60,
  playerWeeks: 11183,
  seasons: '2022-2024',
  weeks: '3-18',
  scoringFormat: 'Half-PPR'
};

/** Per-position breakdown from Phase 54 backtest. */
const POSITION_METRICS = [
  { position: 'QB', model: 'XGBoost', mae: 6.58, rmse: 8.94, bias: -0.42, notes: 'Direct XGBoost' },
  { position: 'RB', model: 'Hybrid Residual', mae: 5.00, rmse: 6.88, bias: -0.71, notes: 'Heuristic + ML correction' },
  { position: 'WR', model: 'Hybrid Residual', mae: 4.63, rmse: 6.41, bias: -0.58, notes: 'Heuristic + ML correction' },
  { position: 'TE', model: 'Hybrid Residual', mae: 3.58, rmse: 4.89, bias: -0.44, notes: 'Heuristic + ML correction' }
];

const POSITION_COLORS: Record<string, string> = {
  QB: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  RB: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
  WR: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400',
  TE: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
};

interface MetricCardProps {
  title: string;
  value: string;
  description: string;
  trend?: string;
  trendDirection?: 'up' | 'down' | 'neutral';
}

function MetricCard({ title, value, description, trend, trendDirection = 'neutral' }: MetricCardProps) {
  const TrendIcon =
    trendDirection === 'up'
      ? Icons.trendingUp
      : trendDirection === 'down'
        ? Icons.trendingDown
        : null;

  return (
    <Card className='@container/card'>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className='text-2xl font-semibold tabular-nums @[250px]/card:text-3xl'>
          {value}
        </CardTitle>
        {trend && TrendIcon && (
          <CardAction>
            <Badge variant='outline'>
              <TrendIcon className='mr-1 h-3 w-3' />
              {trend}
            </Badge>
          </CardAction>
        )}
      </CardHeader>
      <CardFooter className='flex-col items-start gap-1.5 text-sm'>
        <div className='text-muted-foreground'>{description}</div>
      </CardFooter>
    </Card>
  );
}

/** MAE interpretation helper — lower is better for fantasy point error. */
function getMaeRating(mae: number): { label: string; className: string } {
  if (mae < 4.0) return { label: 'Excellent', className: 'text-green-600 dark:text-green-400' };
  if (mae < 5.0) return { label: 'Good', className: 'text-blue-600 dark:text-blue-400' };
  if (mae < 6.0) return { label: 'Fair', className: 'text-amber-600 dark:text-amber-400' };
  return { label: 'High', className: 'text-red-600 dark:text-red-400' };
}

export function AccuracyDashboard() {
  return (
    <div className='space-y-6'>
      {/* Overall metrics cards */}
      <div className='*:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card dark:*:data-[slot=card]:bg-card grid grid-cols-1 gap-4 *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:shadow-xs sm:grid-cols-2 lg:grid-cols-4'>
        <MetricCard
          title='Mean Absolute Error'
          value={OVERALL_METRICS.mae.toFixed(2)}
          description='Fantasy points average error per player-week'
          trend='-3.2% vs baseline'
          trendDirection='down'
        />
        <MetricCard
          title='RMSE'
          value={OVERALL_METRICS.rmse.toFixed(2)}
          description='Root mean squared error (penalises outliers more)'
        />
        <MetricCard
          title='Correlation'
          value={OVERALL_METRICS.correlation.toFixed(3)}
          description='Projected vs actual fantasy points (Pearson r)'
          trend='+0.051 vs baseline'
          trendDirection='up'
        />
        <MetricCard
          title='Bias'
          value={OVERALL_METRICS.bias.toFixed(2)}
          description='Mean signed error — negative means slight under-projection'
        />
      </div>

      {/* Evaluation context */}
      <Card>
        <CardHeader>
          <CardTitle>Evaluation Context</CardTitle>
          <CardDescription>
            Backtest conditions for the Phase 54 tuned model
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className='grid grid-cols-2 gap-4 text-sm sm:grid-cols-4'>
            <div className='space-y-1'>
              <p className='text-muted-foreground text-xs font-medium uppercase tracking-wider'>Seasons</p>
              <p className='font-semibold'>{OVERALL_METRICS.seasons}</p>
            </div>
            <div className='space-y-1'>
              <p className='text-muted-foreground text-xs font-medium uppercase tracking-wider'>Weeks</p>
              <p className='font-semibold'>{OVERALL_METRICS.weeks}</p>
            </div>
            <div className='space-y-1'>
              <p className='text-muted-foreground text-xs font-medium uppercase tracking-wider'>Scoring</p>
              <p className='font-semibold'>{OVERALL_METRICS.scoringFormat}</p>
            </div>
            <div className='space-y-1'>
              <p className='text-muted-foreground text-xs font-medium uppercase tracking-wider'>Player-Weeks</p>
              <p className='font-semibold'>{OVERALL_METRICS.playerWeeks.toLocaleString()}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Per-position breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Per-Position Breakdown</CardTitle>
          <CardDescription>
            MAE, RMSE, and bias split by position and model type
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Position</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className='text-right'>MAE</TableHead>
                <TableHead className='text-right'>RMSE</TableHead>
                <TableHead className='text-right'>Bias</TableHead>
                <TableHead className='hidden sm:table-cell'>Rating</TableHead>
                <TableHead className='hidden md:table-cell'>Notes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {POSITION_METRICS.map((row) => {
                const rating = getMaeRating(row.mae);
                return (
                  <TableRow key={row.position}>
                    <TableCell>
                      <Badge variant='outline' className={POSITION_COLORS[row.position] ?? ''}>
                        {row.position}
                      </Badge>
                    </TableCell>
                    <TableCell className='text-sm'>{row.model}</TableCell>
                    <TableCell className='text-right tabular-nums font-bold'>
                      {row.mae.toFixed(2)}
                    </TableCell>
                    <TableCell className='text-right tabular-nums text-muted-foreground'>
                      {row.rmse.toFixed(2)}
                    </TableCell>
                    <TableCell className='text-right tabular-nums text-muted-foreground'>
                      {row.bias.toFixed(2)}
                    </TableCell>
                    <TableCell className={`hidden sm:table-cell text-sm font-medium ${rating.className}`}>
                      {rating.label}
                    </TableCell>
                    <TableCell className='hidden md:table-cell text-sm text-muted-foreground'>
                      {row.notes}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Weekly trend chart */}
      <WeeklyAccuracyChart />

      {/* Methodology note */}
      <Card>
        <CardHeader>
          <CardTitle>Methodology</CardTitle>
        </CardHeader>
        <CardContent className='space-y-3 text-sm text-muted-foreground'>
          <p>
            Projections are generated using a hybrid approach: a heuristic base model (weighted
            rolling averages, usage multipliers, Vegas implied totals) corrected by an ML residual
            layer trained on 2016-2025 data.
          </p>
          <p>
            QB projections use XGBoost directly. RB, WR, and TE projections use the hybrid
            heuristic + residual model. All models are evaluated on held-out seasons using
            walk-forward cross-validation to prevent data leakage.
          </p>
          <p>
            <span className='font-medium text-foreground'>Lower MAE is better.</span> A bias near
            zero indicates well-calibrated projections. Negative bias means the model slightly
            under-projects on average.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
