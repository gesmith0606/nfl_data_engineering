import { RouteSkeleton } from '@/components/layout/route-skeleton';
import { PremiumUpsell } from '@/features/billing/components/premium-upsell';
import { Suspense } from 'react';

export default function ProbeHPremiumUpsell() {
  return (
    <div>
      <p>PROBE H — PremiumUpsell alone (server-only static component, sanity check)</p>
      <Suspense fallback={<RouteSkeleton rows={5} />}>
        <PremiumUpsell surface='multi-compare' signedIn={false} />
      </Suspense>
    </div>
  );
}
