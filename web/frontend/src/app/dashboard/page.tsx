import PageContainer from '@/components/layout/page-container';
import { OverviewStatCards } from '@/features/nfl/components/stat-cards';
import { MAEByPositionChart } from '@/features/nfl/components/mae-chart';
import { WeeklyAccuracyChart } from '@/features/nfl/components/accuracy-chart';
import { ProofStrip, PhaseModule } from '@/features/nfl/components/home-modules';
import { ModelsPicks } from '@/features/nfl/components/models-picks';
import { FadeIn } from '@/lib/motion-primitives';
import { getSeasonPhase } from '@/lib/nfl/season-phase';

export const metadata = {
  title: 'GIQ — Home Hub'
};

/** Derive the context segment label from the current season phase. */
function hubContextLabel(): string {
  const phase = getSeasonPhase();
  if (phase === 'draft-prep') return '2026 PRESEASON';
  if (phase === 'in-season') return '2026 SEASON';
  return 'OFFSEASON';
}

/**
 * Broadcast page header — condensed-caps display title + yellow context
 * segment (matches the "RANKINGS · 2026 PRESEASON" pattern used on interior
 * data pages). Replaces the generic PageContainer title for the hub only.
 *
 * The 2px mint bottom rule echoes the broadcast nav bar signature, binding
 * the header to the broadcast identity without duplicating the nav.
 */
function HubPageHeader() {
  return (
    <header className='relative overflow-hidden rounded-[var(--radius-lg)] border border-white/10 bg-[var(--wc-bar,#05070d)] px-[var(--space-5)] py-[var(--space-5)] md:px-[var(--space-6)]'>
      {/* 2px mint bottom rule — broadcast nav signature */}
      <div
        aria-hidden
        className='absolute right-0 bottom-0 left-0 h-[2px] rounded-b-[var(--radius-lg)]'
        style={{ background: 'var(--wc-mint,#91edd0)' }}
      />
      <div className='flex flex-col gap-[var(--space-1)]'>
        {/* Yellow condensed eyebrow — e.g. "HOME HUB · 2026 PRESEASON" */}
        <div
          className='wc-display text-[length:var(--fs-xs)] font-semibold tracking-[0.18em] uppercase'
          style={{ color: 'var(--wc-yellow,#ffd84d)' }}
        >
          HOME HUB · {hubContextLabel()}
        </div>
        {/* Condensed-caps display title */}
        <h1 className='wc-display text-[length:var(--fs-h1)] font-extrabold leading-[var(--lh-h1)] tracking-[0.04em] text-white'>
          NFL Analytics
        </h1>
        <p className='text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/60'>
          Ensemble models, market edges, and player projections — measured against the
          consensus every week.
        </p>
      </div>
    </header>
  );
}

export default function Dashboard() {
  return (
    <PageContainer scrollable={false}>
      <FadeIn className='flex flex-1 flex-col gap-[var(--gap-stack)]'>
        {/* Broadcast page header: condensed-caps title + yellow context segment. */}
        <HubPageHeader />

        {/* Proof strip — real model-vs-consensus credibility, links to the
            full track record. Broadcast stat-pill treatment. */}
        <FadeIn delay={0.08} rise={6}>
          <ProofStrip />
        </FadeIn>

        {/* Model's Picks — top edges from the latest predictions week. Self-
            collapses (offseason / backend down) so it never breaks the page,
            and renders its own skeleton while loading. */}
        <ModelsPicks />

        {/* Phase-aware "what to do now" tiles (draft-prep in July). */}
        <FadeIn delay={0.12} rise={6}>
          <PhaseModule />
        </FadeIn>

        {/* At-a-glance model metrics — broadcast stat-pill cards. */}
        <OverviewStatCards />

        <div className='grid grid-cols-1 gap-[var(--gap-stack)] md:grid-cols-2'>
          <FadeIn delay={0.18} rise={6}>
            <MAEByPositionChart />
          </FadeIn>
          <FadeIn delay={0.24} rise={6}>
            <WeeklyAccuracyChart />
          </FadeIn>
        </div>
      </FadeIn>
    </PageContainer>
  );
}
