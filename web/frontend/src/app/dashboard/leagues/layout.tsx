import { PremiumGuard } from '@/features/billing/components/premium-guard';

/** League sync is a premium surface (PLAN 2 tier split). */
export default function LeaguesGateLayout({ children }: { children: React.ReactNode }) {
  return <PremiumGuard surface='leagues'>{children}</PremiumGuard>;
}
