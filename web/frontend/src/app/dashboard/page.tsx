import PageContainer from '@/components/layout/page-container';
import { OverviewStatCards } from '@/features/nfl/components/stat-cards';
import { MAEByPositionChart } from '@/features/nfl/components/mae-chart';
import { WeeklyAccuracyChart } from '@/features/nfl/components/accuracy-chart';
import { ProofStrip, PhaseModule } from '@/features/nfl/components/home-modules';
import { ModelsPicks } from '@/features/nfl/components/models-picks';
import { Icons } from '@/components/icons';
import { FadeIn } from '@/lib/motion-primitives';

export const metadata = {
  title: 'NFL Analytics Dashboard'
};

export default function Dashboard() {
  return (
    <PageContainer
      scrollable={false}
      pageTitle='NFL Analytics Dashboard'
      pageDescription='Model accuracy, tests passing, ATS performance, and player coverage at a glance'
    >
      <FadeIn className='flex flex-1 flex-col gap-[var(--gap-stack)]'>
        {/* Fixed-dark broadcast panel (--surface-scoreboard): stays ink in light mode
            so the gold eyebrow keeps its contrast. */}
        <section className='relative flex items-center overflow-hidden rounded-[var(--radius-lg)] border border-white/10 bg-[var(--surface-scoreboard)] px-[var(--space-5)] py-[var(--space-5)] shadow-sm md:px-[var(--space-6)] md:py-[var(--space-6)]'>
          <div className='relative flex items-center gap-[var(--space-4)]'>
            <div className='wc-rail h-[var(--space-12)] w-[var(--space-1)] shrink-0 rounded-full' />
            <div className='flex flex-col gap-[var(--space-2)]'>
              <div className='text-[var(--wc-gold,var(--chart-1))] inline-flex w-fit items-center gap-[var(--space-1)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] font-semibold tracking-[0.14em] uppercase'>
                <Icons.sparkles className='size-[var(--space-3)]' />
                Premium Models
              </div>
              <h2 className='wc-display text-[length:var(--fs-h1)] leading-[var(--lh-h1)] text-white'>
                State-of-the-art NFL projections &amp; predictions
              </h2>
              <p className='max-w-2xl text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-white/70'>
                Ensemble models, market edges, and player projections — measured against the
                consensus every week.
              </p>
            </div>
          </div>
        </section>

        {/* Proof strip — real model-vs-consensus credibility, links to the
            full track record. */}
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

        {/* Demoted: at-a-glance metrics + trend charts. */}
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
