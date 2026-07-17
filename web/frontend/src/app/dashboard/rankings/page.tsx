import { RankingsView } from '@/features/nfl/components/rankings-view';
import { getSubscriptionStatus } from '@/lib/billing/subscription';

export const metadata = { title: 'Season Rankings' };

/**
 * Server wrapper: resolves premium access (Clerk publicMetadata) and hands
 * the verdict to the client view. Keys absent → hasAccess is always true and
 * the page renders exactly as before.
 */
export default async function RankingsPage() {
  const status = await getSubscriptionStatus();

  return <RankingsView compareLocked={!status.hasAccess} signedIn={status.signedIn} />;
}
