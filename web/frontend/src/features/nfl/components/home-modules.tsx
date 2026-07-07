import Link from 'next/link';

import { Icons } from '@/components/icons';
import { SUCCESS_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';
import { formatGap } from '@/lib/nfl/consensus';
import { getSeasonPhase, getInSeasonCadence } from '@/lib/nfl/season-phase';
import { SectionHeading } from './section-heading';
import modelMetrics from '../config/model-metrics.json';

const CONSENSUS = modelMetrics.consensus;

/* -------------------------------------------------------------------------- */
/* Proof strip — "we beat the consensus" credibility band under the hero.     */
/* Whole strip links to the full track record on /dashboard/accuracy.         */
/* -------------------------------------------------------------------------- */

export function ProofStrip() {
  const { overall, positions } = CONSENSUS;

  return (
    <Link
      href='/dashboard/accuracy'
      aria-label={`We beat the expert consensus overall by ${formatGap(
        overall.gap
      )} MAE — open the full track record`}
      className='group focus-visible:ring-ring/50 block rounded-[var(--radius-lg)] focus-visible:ring-[3px] focus-visible:outline-none'
    >
      <section className='bg-card hover:border-primary/50 relative flex flex-wrap items-center gap-x-[var(--space-4)] gap-y-[var(--space-2)] overflow-hidden rounded-[var(--radius-lg)] border py-[var(--space-3)] pr-[var(--space-4)] pl-[var(--space-4)] shadow-sm transition-colors duration-[var(--motion-base)] md:pr-[var(--space-5)]'>
        <div className='wc-rail absolute inset-y-[var(--space-2)] left-0 w-[3px] rounded-full' />

        <div className='flex items-center gap-[var(--space-2)]'>
          <Icons.sparkles className='size-[var(--space-4)] text-[var(--wc-gold,var(--chart-1))]' />
          <span className='wc-display text-[length:var(--fs-lg)] leading-none'>
            Beat the Consensus
          </span>
        </div>

        <span className='text-muted-foreground text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          Overall MAE gap{' '}
          <span className={`font-bold tabular-nums ${overall.win ? SUCCESS_TEXT : DANGER_TEXT}`}>
            {formatGap(overall.gap)}
          </span>{' '}
          vs experts
        </span>

        <div className='flex flex-wrap items-center gap-[var(--space-2)]'>
          {positions.map((p) => (
            <span
              key={p.position}
              className='border-border bg-background/60 inline-flex items-center gap-[var(--space-1)] rounded-full border py-[var(--space-1)] pr-[var(--space-2)] pl-[var(--space-2)] text-[length:var(--fs-xs)] leading-none'
            >
              <span className='wc-display'>{p.position}</span>
              <span className={`tabular-nums font-semibold ${p.win ? SUCCESS_TEXT : DANGER_TEXT}`}>
                {formatGap(p.gap)}
              </span>
              {p.win ? (
                <Icons.check className={`size-[var(--space-3)] ${SUCCESS_TEXT}`} />
              ) : (
                <Icons.close className={`size-[var(--space-3)] ${DANGER_TEXT}`} />
              )}
            </span>
          ))}
        </div>

        <span className='text-muted-foreground ml-auto hidden items-center gap-[var(--space-1)] text-[length:var(--fs-xs)] leading-none tracking-[0.08em] uppercase md:inline-flex'>
          Track record
          <Icons.arrowRight className='size-[var(--space-3)] transition-transform duration-[var(--motion-base)] group-hover:translate-x-[var(--space-1)]' />
        </span>
      </section>
    </Link>
  );
}

/* -------------------------------------------------------------------------- */
/* Phase-aware module — date-driven "what to do now" tile row.                */
/* -------------------------------------------------------------------------- */

interface HubTile {
  title: string;
  description: string;
  href: string;
  icon: keyof typeof Icons;
  badge?: string;
}

interface PhaseContent {
  eyebrow: string;
  heading: string;
  tiles: HubTile[];
}

function draftPrepContent(): PhaseContent {
  return {
    eyebrow: 'Draft Season',
    heading: 'Draft Prep HQ',
    tiles: [
      {
        title: 'Preseason Projections',
        description: 'Full-season point projections across all scoring formats',
        href: '/dashboard/projections',
        icon: 'target'
      },
      {
        title: 'Rankings Compare',
        description: 'Our board vs Sleeper, ESPN & FantasyPros — side by side',
        href: '/dashboard/rankings',
        icon: 'chartBar'
      },
      {
        title: 'Draft Room',
        description: 'Live VORP board, tiers and mock-draft simulator',
        href: '/dashboard/draft',
        icon: 'football'
      },
      {
        title: 'League Sync',
        description: 'Connect your Sleeper league for keeper decisions, custom scoring & rookie board',
        href: '/dashboard/leagues',
        icon: 'teams',
        badge: 'NEW'
      }
    ]
  };
}

function inSeasonContent(): PhaseContent {
  const cadence = getInSeasonCadence();
  const projectionsDesc =
    cadence === 'refresh'
      ? 'Fresh weekly projections just published — set your lineup'
      : cadence === 'gameday'
        ? 'Final start/sit calls before kickoff'
        : 'Mid-week projections to plan your matchup';
  const edgesDesc =
    cadence === 'gameday'
      ? 'Live model-vs-Vegas edges for today’s slate'
      : 'Spread & total edges vs the Vegas market';
  return {
    eyebrow: cadence === 'refresh' ? 'Tuesday · Waivers Open' : 'This Week',
    heading: cadence === 'gameday' ? 'Game Day' : 'This Week',
    tiles: [
      {
        title: 'Weekly Projections',
        description: projectionsDesc,
        href: '/dashboard/projections',
        icon: 'target'
      },
      {
        title: 'Game Edges',
        description: edgesDesc,
        href: '/dashboard/predictions',
        icon: 'trendingUp'
      },
      {
        title: 'Lineup Builder',
        description: 'Optimal lineup from your roster and this week’s projections',
        href: '/dashboard/lineups',
        icon: 'shield'
      }
    ]
  };
}

function offseasonContent(): PhaseContent {
  return {
    eyebrow: 'Offseason',
    heading: 'While You Wait',
    tiles: [
      {
        title: 'Track Record',
        description: 'How our models graded out vs the expert consensus',
        href: '/dashboard/accuracy',
        icon: 'chartBar'
      },
      {
        title: 'Projections',
        description: 'Latest available player projections',
        href: '/dashboard/projections',
        icon: 'target'
      },
      {
        title: 'News & Signals',
        description: 'Offseason moves, depth-chart shifts and sentiment',
        href: '/dashboard/news',
        icon: 'news'
      }
    ]
  };
}

export function PhaseModule() {
  const phase = getSeasonPhase();
  const content =
    phase === 'draft-prep'
      ? draftPrepContent()
      : phase === 'in-season'
        ? inSeasonContent()
        : offseasonContent();

  return (
    <section className='space-y-[var(--space-3)]'>
      <SectionHeading overline={content.eyebrow} title={content.heading} />

      <div className='grid grid-cols-1 gap-[var(--gap-stack)] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'>
        {content.tiles.map((tile) => {
          const Icon = Icons[tile.icon];
          return (
            <Link
              key={tile.href}
              href={tile.href}
              className='group bg-card hover:border-primary/50 focus-visible:ring-ring/50 relative flex items-start gap-[var(--space-3)] overflow-hidden rounded-[var(--radius-lg)] border py-[var(--space-4)] pr-[var(--space-3)] pl-[var(--space-4)] shadow-sm transition-colors duration-[var(--motion-base)] focus-visible:ring-[3px] focus-visible:outline-none'
            >
              <div className='wc-rail absolute inset-y-[var(--space-3)] left-0 w-[3px] rounded-full' />
              {tile.badge && (
                <div className='absolute top-[var(--space-3)] right-[var(--space-3)] inline-flex items-center rounded-full bg-amber-500/20 px-[var(--space-2)] py-[var(--space-1)] text-[length:var(--fs-xs)] font-semibold leading-none text-amber-600 dark:text-amber-400'>
                  {tile.badge}
                </div>
              )}
              <div className='bg-primary/10 text-primary flex size-[var(--space-8)] shrink-0 items-center justify-center rounded-[var(--radius-md)]'>
                <Icon className='size-[var(--space-4)]' />
              </div>
              <div className='min-w-0 flex-1'>
                <div className='flex items-center gap-[var(--space-1)]'>
                  <span className='wc-display text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                    {tile.title}
                  </span>
                  <Icons.arrowRight className='text-muted-foreground size-[var(--space-3)] transition-transform duration-[var(--motion-base)] group-hover:translate-x-[var(--space-1)]' />
                </div>
                <p className='text-muted-foreground mt-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  {tile.description}
                </p>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
