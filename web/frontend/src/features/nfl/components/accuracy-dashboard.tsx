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
import {
  SUCCESS_TEXT,
  WARN_TEXT,
  DANGER_TEXT,
  SUCCESS_BADGE,
  DANGER_BADGE
} from '@/lib/nfl/semantic-colors';
import { formatGap } from '@/lib/nfl/consensus';
import { cn } from '@/lib/utils';
import modelMetrics from '../config/model-metrics.json';

/** Overall backtest metrics generated from the v4.2 production backtest artifact. */
const OVERALL_METRICS = modelMetrics.overall;

/** Matched-pairs benchmark vs the Sleeper expert consensus. */
const CONSENSUS = modelMetrics.consensus;
const CONSENSUS_WINS = CONSENSUS.positions.filter((p) => p.win).length;

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

function MetricCard({
  title,
  value,
  description,
  trend,
  trendDirection = 'neutral'
}: MetricCardProps) {
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

/** Verdict pill: BEAT CONSENSUS (win) / TRAILING (loss). */
function VerdictBadge({ win }: { win: boolean }) {
  return (
    <span
      className={cn(
        'wc-display inline-flex items-center gap-[var(--space-1)] rounded-full px-[var(--space-2)] py-[var(--space-1)] text-[length:var(--fs-xs)] leading-none tracking-[0.04em]',
        win ? SUCCESS_BADGE : DANGER_BADGE
      )}
    >
      {win ? (
        <Icons.check className='size-[var(--space-3)]' />
      ) : (
        <Icons.close className='size-[var(--space-3)]' />
      )}
      {win ? 'Beat Consensus' : 'Trailing'}
    </span>
  );
}

/** Lead section: headline claim + head-to-head consensus leaderboard. */
function ConsensusLeaderboard() {
  const { overall, positions, benchmark, seasons } = CONSENSUS;

  return (
    <div className='space-y-[var(--gap-stack)]'>
      {/* Headline — fixed-dark broadcast panel so the gold win reads in both modes. */}
      <section className='relative flex flex-col gap-[var(--space-2)] overflow-hidden rounded-[var(--radius-lg)] border border-white/10 bg-[var(--surface-scoreboard)] px-[var(--space-5)] py-[var(--space-5)] shadow-sm md:px-[var(--space-6)] md:py-[var(--space-6)]'>
        <div className='text-[var(--wc-gold,var(--chart-4))] relative inline-flex w-fit items-center gap-[var(--space-1)] text-[length:var(--fs-xs)] leading-none font-semibold tracking-[0.14em] uppercase'>
          <Icons.sparkles className='size-[var(--space-3)]' />
          {CONSENSUS_WINS} of {positions.length} positions + overall
        </div>
        <h2 className='wc-display relative text-[length:var(--fs-h1)] leading-[var(--lh-h1)] text-white'>
          We beat the expert consensus
        </h2>
        <p className='relative max-w-3xl text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/70'>
          Measured head-to-head vs {benchmark}, {seasons} &middot;{' '}
          <span className='font-semibold text-white'>
            {overall.playerWeeks.toLocaleString()} matched player-weeks
          </span>
          . Overall MAE{' '}
          <span className='font-semibold text-white tabular-nums'>{overall.ourMae.toFixed(3)}</span>{' '}
          vs their <span className='tabular-nums'>{overall.consensusMae.toFixed(3)}</span> (gap{' '}
          <span className={cn('font-bold tabular-nums', overall.win ? SUCCESS_TEXT : DANGER_TEXT)}>
            {formatGap(overall.gap)}
          </span>
          ).
        </p>
      </section>

      {/* Leaderboard table */}
      <Card>
        <CardHeader>
          <CardTitle>Consensus Leaderboard</CardTitle>
          <CardDescription>
            Lower MAE is better. A negative gap means we beat the consensus.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Position</TableHead>
                <TableHead className='text-right'>Our MAE</TableHead>
                <TableHead className='text-right'>Consensus MAE</TableHead>
                <TableHead className='text-right'>Gap</TableHead>
                <TableHead>Verdict</TableHead>
                <TableHead className='hidden text-right sm:table-cell'>Player-Weeks</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((row) => (
                <TableRow key={row.position}>
                  <TableCell>
                    <Badge variant='outline' className={getPositionBadgeClass(row.position)}>
                      {row.position}
                    </Badge>
                  </TableCell>
                  <TableCell className='text-right font-bold tabular-nums'>
                    {row.ourMae.toFixed(3)}
                  </TableCell>
                  <TableCell className='text-muted-foreground text-right tabular-nums'>
                    {row.consensusMae.toFixed(3)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      'text-right font-semibold tabular-nums',
                      row.win ? SUCCESS_TEXT : DANGER_TEXT
                    )}
                  >
                    {formatGap(row.gap)}
                  </TableCell>
                  <TableCell>
                    <VerdictBadge win={row.win} />
                  </TableCell>
                  <TableCell className='text-muted-foreground hidden text-right tabular-nums sm:table-cell'>
                    {row.playerWeeks.toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
              {/* Overall — visually distinct summary row. */}
              <TableRow className='bg-muted/40 border-t-2 border-t-[var(--wc-gold,var(--primary))]'>
                <TableCell className='wc-display text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                  Overall
                </TableCell>
                <TableCell className='text-right font-bold tabular-nums'>
                  {overall.ourMae.toFixed(3)}
                </TableCell>
                <TableCell className='text-muted-foreground text-right tabular-nums'>
                  {overall.consensusMae.toFixed(3)}
                </TableCell>
                <TableCell
                  className={cn(
                    'text-right font-bold tabular-nums',
                    overall.win ? SUCCESS_TEXT : DANGER_TEXT
                  )}
                >
                  {formatGap(overall.gap)}
                </TableCell>
                <TableCell>
                  <VerdictBadge win={overall.win} />
                </TableCell>
                <TableCell className='text-muted-foreground hidden text-right tabular-nums sm:table-cell'>
                  {overall.playerWeeks.toLocaleString()}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

/** Honest matched-pairs methodology — the FantasyPros credibility pattern. */
function ConsensusMethodology() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>How this is measured</CardTitle>
        <CardDescription>Matched-pairs evaluation — no cherry-picking</CardDescription>
      </CardHeader>
      <CardContent className='grid gap-[var(--gap-stack)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] sm:grid-cols-2'>
        <ul className='text-muted-foreground space-y-[var(--space-2)]'>
          <li className='flex gap-[var(--space-2)]'>
            <Icons.check className={cn('mt-[2px] size-[var(--space-4)] shrink-0', SUCCESS_TEXT)} />
            <span>
              <span className='text-foreground font-medium'>Matched pairs only.</span> We score a
              player-week only when both our model and the expert consensus published a projection —
              same players, same slate.
            </span>
          </li>
          <li className='flex gap-[var(--space-2)]'>
            <Icons.check className={cn('mt-[2px] size-[var(--space-4)] shrink-0', SUCCESS_TEXT)} />
            <span>
              <span className='text-foreground font-medium'>Identical actuals.</span> Both sources
              are graded against the same realised {CONSENSUS.scoringFormat} fantasy points.
            </span>
          </li>
          <li className='flex gap-[var(--space-2)]'>
            <Icons.check className={cn('mt-[2px] size-[var(--space-4)] shrink-0', SUCCESS_TEXT)} />
            <span>
              <span className='text-foreground font-medium'>Injury-aware.</span> Inactive and
              ruled-out players are handled consistently on both sides before scoring.
            </span>
          </li>
        </ul>
        <div className='grid grid-cols-2 gap-[var(--gap-stack)] self-start'>
          {[
            { label: 'Benchmark', value: CONSENSUS.benchmark },
            { label: 'Seasons', value: `${CONSENSUS.seasons} · Wk 3-18` },
            { label: 'Scoring', value: CONSENSUS.scoringFormat },
            { label: 'Player-Weeks', value: CONSENSUS.overall.playerWeeks.toLocaleString() }
          ].map((item) => (
            <div key={item.label} className='space-y-[var(--space-1)]'>
              <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium tracking-wider uppercase'>
                {item.label}
              </p>
              <p className='font-semibold'>{item.value}</p>
            </div>
          ))}
          <div className='col-span-2 space-y-[var(--space-1)]'>
            <p className='text-muted-foreground text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-medium tracking-wider uppercase'>
              Source artifact
            </p>
            <p className='font-mono text-[length:var(--fs-xs)] leading-[var(--lh-xs)] break-all'>
              {CONSENSUS.generatedFrom}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** In-season live-grading teaser — makes the models site feel alive. */
function WeeklyGradingTeaser() {
  return (
    <Card className='relative overflow-hidden'>
      <div className='wc-rail absolute inset-y-[var(--space-4)] left-0 w-[3px] rounded-full' />
      <CardHeader>
        <CardTitle className='flex items-center gap-[var(--space-2)]'>
          <Icons.clock className='text-[var(--wc-gold,var(--chart-4))] size-[var(--space-4)]' />
          Graded every Tuesday in-season
        </CardTitle>
        <CardDescription>Live accountability once the games start</CardDescription>
      </CardHeader>
      <CardContent className='space-y-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
        <p>
          Every Tuesday during the season we grade the previous week&apos;s projections against the
          expert consensus, and our game lines against the closing Vegas market — then publish the
          scorecard here. No hindsight, no edits: the numbers land the day after the games.
        </p>
        <p className='text-foreground font-medium'>The first 2026 report lands after Week 1.</p>
      </CardContent>
    </Card>
  );
}

export function AccuracyDashboard() {
  return (
    <div className='space-y-[var(--gap-section)]'>
      {/* LEAD — model vs. consensus proof */}
      <ConsensusLeaderboard />
      <ConsensusMethodology />
      <WeeklyGradingTeaser />

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
          <CardDescription>Backtest conditions for the v4.2 production model</CardDescription>
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
          <CardDescription>MAE, RMSE, and bias split by position and model type</CardDescription>
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
