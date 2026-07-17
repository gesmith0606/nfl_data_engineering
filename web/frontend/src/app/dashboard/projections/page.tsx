import PageContainer from '@/components/layout/page-container';
import { PremiumUpsell } from '@/features/billing/components/premium-upsell';
import { ProjectionsTable } from '@/features/nfl/components/projections-table';
import { ProjectionComparisonTable } from '@/features/nfl/components/projection-comparison-table';
import { getSubscriptionStatus } from '@/lib/billing/subscription';
import { FadeIn } from '@/lib/motion-primitives';
import { Suspense } from 'react';

export const metadata = {
  title: '2026 NFL Fantasy Projections',
  description:
    'Weekly fantasy football projections with PPR, Half-PPR, and Standard scoring. Floor/ceiling ranges for all skill positions.',
  openGraph: {
    title: '2026 NFL Fantasy Projections | NFL Analytics',
    description:
      'Weekly fantasy football projections with PPR, Half-PPR, and Standard scoring. Floor/ceiling ranges for all skill positions.',
    url: 'https://frontend-jet-seven-33.vercel.app/dashboard/projections'
  },
  twitter: {
    card: 'summary_large_image' as const,
    title: '2026 NFL Fantasy Projections',
    description: 'Weekly fantasy football projections with PPR, Half-PPR, and Standard scoring.'
  }
};

export default async function ProjectionsPage() {
  // PLAN 2 tier split: projections stay free up to the top 50 per position;
  // full lists + floor/ceiling bands + multi-source compare are premium.
  // Keys absent → hasAccess is true and the page renders exactly as before.
  const status = await getSubscriptionStatus();
  const freeTier = !status.hasAccess;

  return (
    <PageContainer
      scrollable={false}
      pageTitle='Fantasy Projections'
      pageDescription='Weekly fantasy point projections with floor/ceiling ranges'
    >
      <Suspense>
        <FadeIn>
          <ProjectionsTable freeTier={freeTier} />
        </FadeIn>
      </Suspense>

      {/* Phase 73: Multi-source comparison view (ESPN/Sleeper/Yahoo vs ours). */}
      <FadeIn>
        <section className='mt-10 space-y-3'>
          <div>
            <h2 className='text-xl font-semibold'>Multi-Source Comparison</h2>
            <p className='text-sm text-muted-foreground'>
              Side-by-side projections from ours, ESPN, Sleeper, and Yahoo (via
              FantasyPros consensus). Δ shows externals avg minus ours.
            </p>
          </div>
          {freeTier ? (
            <PremiumUpsell surface='multi-compare' signedIn={status.signedIn} />
          ) : (
            <Suspense>
              <ProjectionComparisonTable season={2025} week={1} scoring='half_ppr' />
            </Suspense>
          )}
        </section>
      </FadeIn>
    </PageContainer>
  );
}
