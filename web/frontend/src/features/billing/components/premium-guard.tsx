import { getSubscriptionStatus } from '@/lib/billing/subscription';
import { PremiumUpsell, type PremiumSurface } from './premium-upsell';

/**
 * Server-side premium gate for whole routes. Drop into a route-group
 * `layout.tsx`:
 *
 *   export default function Layout({ children }) {
 *     return <PremiumGuard surface='advisor'>{children}</PremiumGuard>;
 *   }
 *
 * With auth keys absent everything passes through (feature flag). With keys
 * present, non-premium sessions get the blurred upsell — the premium children
 * are never rendered, so no premium markup/data reaches the client.
 */
export async function PremiumGuard({
  surface,
  children
}: {
  surface: PremiumSurface;
  children: React.ReactNode;
}) {
  const status = await getSubscriptionStatus();
  if (status.hasAccess) return <>{children}</>;

  return (
    <div className='mx-auto w-full max-w-3xl px-4 py-10 md:py-16'>
      <PremiumUpsell surface={surface} signedIn={status.signedIn} />
    </div>
  );
}
