import { PremiumGuard } from '@/features/billing/components/premium-guard';

/** Draft tools are a premium surface (PLAN 2 tier split). */
export default function DraftGateLayout({ children }: { children: React.ReactNode }) {
  return <PremiumGuard surface='draft'>{children}</PremiumGuard>;
}
