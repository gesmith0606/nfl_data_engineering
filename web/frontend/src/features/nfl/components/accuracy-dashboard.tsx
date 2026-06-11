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
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { SUCCESS_TEXT, WARN_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';
import modelMetrics from '../config/model-metrics.json';

/** Overall backtest metrics generated from the v4.2 production backtest artifact. */
const OVERALL_METRICS = modelMetrics.overall;

const MODEL_NOTES: Record<string, string> = {
  Heuristic: 'Weighted rolling averages + usage/matchup/Vegas multipliers',
  'Hybrid Residual': 'Heuristic + ML correction',
  XGBoost: 'Direct XGBoost'
};

/** Per-position breakdown from the v4.2 production backtest. */
const POSITION_METRICS = modelMetrics.positions.map((p) => ({
  ...p,
  notes: MODEL_NOTES[p.model] ?? p.model
}));

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
        <CardTitle className='text-[length:var(--fs-h2)] leading-[var(--lh-h2)] font-semibold tabular-nums @[250px]/card:text-[length:var(--fs-h1)] @[250px]/card:leading-[var(--lh-h1)]'>
          {value}
        </CardTitle>
        {trend && TrendIcon && (
          <CardAction>
            <Badge variant='outline'>
              <TrendIcon className='mr-[var(--space-1)] h-[var(--space-3)] w-[var(--space-3)]' />
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

/** MAE interpretation helper — lower is better for fantasy point error. */
function getMaeRating(mae: number): { label: string; className: string } {
  if (mae < 4.0) return { label: 'Excellent', className: SUCCESS_TEXT };
  if (mae < 5.0) return { label: 'Good', className: 'text-blue-600 dark:text-blue-400' };
  if (mae < 6.0) return { label: 'Fair', className: WARN_TEXT };
  return { label: 'High', className: DANGER_TEXT };
}

export function AccuracyDashboard() {
  return (
    <div className='space-y-[var(--gap-section)]'>
      {/* Overall metrics cards */}
      <div className='*:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card dark:*:data-[slot=card]:bg-card grid grid-cols-1 gap-[var(--gap-stack)] *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:shadow-[var(--elevation-flat)] sm:grid-cols-2 lg:grid-cols-4'>
        <MetricCard
          title='Mean Absolute Error'
          value={OVERALL_METRICS.mae.toFixed(2)}
          description='Fantasy points average error per player-week'
          trend='-3.0% in v4.2'
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
            Backtest conditions for the v4.2 production model
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className='grid grid-cols-2 gap-[var(--gap-stack)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] sm:grid-cols-4'>
            <div className='space-y-[var(--space-1)]'>
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium uppercase tracking-wider'>
                Seasons
              </p>
              <p className='font-semibold'>{OVERALL_METRICS.seasons}</p>
            </div>
            <div className='space-y-[var(--space-1)]'>
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium uppercase tracking-wider'>
                Weeks
              </p>
              <p className='font-semibold'>{OVERALL_METRICS.weeks}</p>
            </div>
            <div className='space-y-[var(--space-1)]'>
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium uppercase tracking-wider'>
                Scoring
              </p>
              <p className='font-semibold'>{OVERALL_METRICS.scoringFormat}</p>
            </div>
            <div className='space-y-[var(--space-1)]'>
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium uppercase tracking-wider'>
                Player-Weeks
              </p>
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
                      <Badge variant='outline' className={getPositionBadgeClass(row.position)}>
                        {row.position}
                      </Badge>
                    </TableCell>
                    <TableCell className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                      {row.model}
                    </TableCell>
                    <TableCell className='text-right tabular-nums font-bold'>
                      {row.mae.toFixed(2)}
                    </TableCell>
                    <TableCell className='text-right tabular-nums text-muted-foreground'>
                      {row.rmse.toFixed(2)}
                    </TableCell>
                    <TableCell className='text-right tabular-nums text-muted-foreground'>
                      {row.bias.toFixed(2)}
                    </TableCell>
                    <TableCell
                      className={`hidden sm:table-cell text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium ${rating.className}`}
                    >
                      {rating.label}
                    </TableCell>
                    <TableCell className='hidden md:table-cell text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
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
        <CardContent className='space-y-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
          <p>
            Projections are generated from a heuristic base model: weighted rolling averages
            combined with usage, matchup, and Vegas implied-total multipliers, with TD regression
            and per-position recency weighting (v4.2).
          </p>
          <p>
            QB, RB, and WR projections use the tuned heuristic directly. TE projections add an ML
            residual correction layer trained on 2016-2025 data. All models are evaluated on
            held-out seasons, and ship decisions are confirmed on a sealed 2025 holdout.
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
