import { PremiumGuard } from '@/features/billing/components/premium-guard';

/** AI advisor is a premium surface (PLAN 2 tier split). */
export default function AdvisorGateLayout({ children }: { children: React.ReactNode }) {
  return <PremiumGuard surface='advisor'>{children}</PremiumGuard>;
}
