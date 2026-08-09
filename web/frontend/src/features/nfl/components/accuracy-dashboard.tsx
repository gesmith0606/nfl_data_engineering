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
import { Icons } from '@/components/icons';
import { WeeklyAccuracyChart } from './accuracy-chart';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';
import { getPositionBadgeClass } from '@/lib/nfl/position-colors';
import { SUCCESS_TEXT, DANGER_TEXT, SUCCESS_BADGE, DANGER_BADGE } from '@/lib/nfl/semantic-colors';
import { formatGap } from '@/lib/nfl/consensus';
import { gradeGap, gradeMae } from '@/lib/nfl/accuracy-grade';
import { cn } from '@/lib/utils';
import { SectionOverline } from './section-heading';
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

type PositionMetricRow = (typeof POSITION_METRICS)[number];

/** Grade chip — letter grade rendered next to (never instead of) the raw
 *  number it summarizes, so rows scan at a glance without hiding the math. */
function GradeChip({ grade, className, title }: { grade: string; className: string; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        'wc-display inline-flex min-w-[26px] items-center justify-center rounded-full border border-current/30 px-[6px] py-[1px] text-[11px] leading-none font-extrabold tracking-[0.02em]',
        className
      )}
    >
      {grade}
    </span>
  );
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

const positionColumns: BroadcastColumn<PositionMetricRow>[] = [
  {
    key: 'position',
    header: 'Position',
    sticky: true,
    accessor: (row) => (
      <Badge variant='outline' className={getPositionBadgeClass(row.position)}>
        {row.position}
      </Badge>
    )
  },
  {
    key: 'model',
    header: 'Model',
    accessor: (row) => row.model,
    cellClassName: 'text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'
  },
  {
    key: 'mae',
    header: 'MAE',
    align: 'right',
    accessor: (row) => <span className='wc-num-hero'>{row.mae.toFixed(2)}</span>
  },
  {
    key: 'rmse',
    header: 'RMSE',
    align: 'right',
    accessor: (row) => row.rmse.toFixed(2),
    cellClassName: 'text-muted-foreground tabular-nums'
  },
  {
    key: 'bias',
    header: 'Bias',
    align: 'right',
    accessor: (row) => row.bias.toFixed(2),
    cellClassName: 'text-muted-foreground tabular-nums'
  },
  {
    key: 'grade',
    header: 'Grade',
    headerClassName: 'hidden sm:table-cell',
    cellClassName: 'hidden sm:table-cell',
    accessor: (row) => {
      const grade = gradeMae(row.mae);
      return (
        <span className='inline-flex items-center gap-[var(--space-2)]'>
          <GradeChip grade={grade.grade} className={grade.className} />
          <span
            className={cn('text-[length:var(--fs-sm)] leading-[var(--lh-sm)] font-medium', grade.className)}
          >
            {grade.label}
          </span>
        </span>
      );
    }
  },
  {
    key: 'notes',
    header: 'Notes',
    headerClassName: 'hidden md:table-cell',
    cellClassName:
      'hidden text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground md:table-cell',
    accessor: (row) => row.notes
  }
];

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

type LeaderboardRow = (typeof CONSENSUS.positions)[number] & { isOverall?: boolean };

/** Per-position rows + a visually distinct Overall summary row. */
const LEADERBOARD_ROWS: LeaderboardRow[] = [
  ...CONSENSUS.positions,
  { ...CONSENSUS.overall, position: 'Overall', isOverall: true }
];

const leaderboardColumns: BroadcastColumn<LeaderboardRow>[] = [
  {
    key: 'position',
    header: 'Position',
    sticky: true,
    accessor: (row) =>
      row.isOverall ? (
        <span className='wc-display text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          Overall
        </span>
      ) : (
        <Badge variant='outline' className={getPositionBadgeClass(row.position)}>
          {row.position}
        </Badge>
      )
  },
  {
    key: 'ourMae',
    header: 'Our MAE',
    align: 'right',
    accessor: (row) => <span className='wc-num-hero'>{row.ourMae.toFixed(3)}</span>
  },
  {
    key: 'consensusMae',
    header: 'Consensus MAE',
    align: 'right',
    accessor: (row) => row.consensusMae.toFixed(3),
    cellClassName: 'text-muted-foreground tabular-nums'
  },
  {
    key: 'gap',
    header: 'Gap',
    align: 'right',
    accessor: (row) => (
      <span className={cn('font-bold tabular-nums', row.win ? SUCCESS_TEXT : DANGER_TEXT)}>
        {formatGap(row.gap)}
      </span>
    )
  },
  {
    key: 'grade',
    header: 'Grade',
    align: 'right',
    accessor: (row) => {
      const grade = gradeGap(row.gap);
      return <GradeChip grade={grade.grade} className={grade.className} title={grade.description} />;
    }
  },
  {
    key: 'verdict',
    header: 'Verdict',
    accessor: (row) => <VerdictBadge win={row.win} />
  },
  {
    key: 'playerWeeks',
    header: 'Player-Weeks',
    align: 'right',
    headerClassName: 'hidden sm:table-cell',
    cellClassName: 'hidden text-muted-foreground tabular-nums sm:table-cell',
    accessor: (row) => row.playerWeeks.toLocaleString()
  }
];

/** Lead section: headline claim + head-to-head consensus leaderboard. */
function ConsensusLeaderboard() {
  const { overall, positions, benchmark, seasons } = CONSENSUS;

  return (
    <div className='space-y-[var(--gap-stack)]'>
      {/* Headline — fixed-dark broadcast panel so the mint win reads in both modes. */}
      <section className='relative flex flex-col gap-[var(--space-2)] overflow-hidden rounded-[var(--radius-lg)] border border-white/10 bg-[var(--surface-scoreboard)] px-[var(--space-5)] py-[var(--space-5)] shadow-sm md:px-[var(--space-6)] md:py-[var(--space-6)]'>
        <div className='text-[var(--wc-yellow,#ffd84d)] relative inline-flex w-fit items-center gap-[var(--space-1)] text-[length:var(--fs-xs)] leading-none font-semibold tracking-[0.14em] uppercase'>
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
        <a
          href='#methodology'
          className='relative inline-flex w-fit items-center gap-[var(--space-1)] text-[length:var(--fs-xs)] leading-none tracking-[0.06em] text-white/60 underline decoration-white/30 underline-offset-4 transition-colors hover:text-white'
        >
          How we grade this
          <Icons.arrowRight className='size-[var(--space-3)] rotate-90' />
        </a>
      </section>

      {/* Leaderboard table — BroadcastTable renders its own Card, so the
          header lives in a separate Card above it (dynasty-view pattern). */}
      <Card>
        <CardHeader>
          <SectionOverline>Head to Head</SectionOverline>
          <CardTitle className='wc-display'>Consensus Leaderboard</CardTitle>
          <CardDescription>
            Lower MAE is better. A negative gap means we beat the consensus. Grade reflects the
            size of that gap — A+/A win decisively, B is a statistical tie, C/D trail.
          </CardDescription>
        </CardHeader>
      </Card>
      <BroadcastTable
        columns={leaderboardColumns}
        rows={LEADERBOARD_ROWS}
        getRowId={(row) => (row.isOverall ? 'overall' : row.position)}
        rowClassName={(row) =>
          row.isOverall ? 'bg-muted/40 border-t-2 border-t-[var(--wc-yellow,#ffd84d)]' : ''
        }
        emptyMessage='No consensus benchmark data available.'
        minWidth='min-w-[560px]'
      />
    </div>
  );
}

/** Honest matched-pairs methodology — the FantasyPros credibility pattern. */
function ConsensusMethodology() {
  return (
    <Card id='methodology' className='scroll-mt-[var(--space-6)]'>
      <CardHeader>
        <SectionOverline>Methodology</SectionOverline>
        <CardTitle className='wc-display'>How this is measured</CardTitle>
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
        <SectionOverline>Live In-Season</SectionOverline>
        <CardTitle className='wc-display flex items-center gap-[var(--space-2)]'>
          <Icons.clock className='text-[var(--wc-yellow,#ffd84d)] size-[var(--space-4)]' />
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

      {/* Per-position breakdown — header Card + standalone BroadcastTable,
          same reasoning as the leaderboard above. */}
      <Card>
        <CardHeader>
          <CardTitle>Per-Position Breakdown</CardTitle>
          <CardDescription>
            MAE, RMSE, and bias split by position and model type. Grade is the absolute-error
            band (A = under 4.0 MAE) — separate from the head-to-head gap grade above.
          </CardDescription>
        </CardHeader>
      </Card>
      <BroadcastTable
        columns={positionColumns}
        rows={POSITION_METRICS}
        getRowId={(row) => row.position}
        emptyMessage='No per-position backtest data available.'
        minWidth='min-w-[640px]'
      />

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
