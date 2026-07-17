import { PremiumGuard } from '@/features/billing/components/premium-guard';

/** Lineup builder is a premium surface (PLAN 2 tier split). */
export default function LineupsGateLayout({ children }: { children: React.ReactNode }) {
  return <PremiumGuard surface='lineups'>{children}</PremiumGuard>;
}
