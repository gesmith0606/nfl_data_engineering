'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

/**
 * Client buttons that call the billing route handlers and redirect the
 * browser to Stripe. Both degrade gracefully: 503 (billing unconfigured)
 * and 401 (signed out) are handled without crashing.
 */
async function redirectToBillingUrl(
  endpoint: string,
  onUnauthenticated: () => void
): Promise<void> {
  const res = await fetch(endpoint, { method: 'POST' });
  if (res.status === 401) {
    onUnauthenticated();
    return;
  }
  const data = (await res.json().catch(() => ({}))) as { url?: string; error?: string };
  if (res.ok && data.url) {
    window.location.href = data.url;
    return;
  }
  toast.error(data.error ?? 'Billing is not available right now');
}

const CTA_CLASSES =
  'wc-display inline-flex items-center justify-center rounded-full px-6 py-2.5 text-[14px] tracking-[0.1em] transition-colors disabled:cursor-not-allowed disabled:opacity-60';

export function CheckoutButton({
  className,
  children = 'Start 7-day free trial'
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  return (
    <button
      type='button'
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await redirectToBillingUrl('/api/billing/checkout', () =>
            router.push('/auth/sign-up?redirect_url=/pricing')
          );
        } finally {
          setBusy(false);
        }
      }}
      className={cn(
        CTA_CLASSES,
        'bg-[var(--wc-peri,#5b67c7)] text-white hover:bg-[var(--wc-peri-bright,#6e7ce0)]',
        className
      )}
    >
      {busy ? 'Opening checkout…' : children}
    </button>
  );
}

export function ManageSubscriptionButton({ className }: { className?: string }) {
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  return (
    <button
      type='button'
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await redirectToBillingUrl('/api/billing/portal', () =>
            router.push('/auth/sign-in?redirect_url=/pricing')
          );
        } finally {
          setBusy(false);
        }
      }}
      className={cn(
        CTA_CLASSES,
        'border border-white/20 text-[#cfd6e4] hover:border-[var(--wc-mint,#91edd0)] hover:text-[var(--wc-mint,#91edd0)]',
        className
      )}
    >
      {busy ? 'Opening portal…' : 'Manage subscription'}
    </button>
  );
}
