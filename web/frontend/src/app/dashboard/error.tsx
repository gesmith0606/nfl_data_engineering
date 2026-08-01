'use client';

import { useEffect } from 'react';

import { EmptyState } from '@/components/EmptyState';
import { Button } from '@/components/ui/button';
import { Icons } from '@/components/icons';

/**
 * Route-segment error boundary for every /dashboard page.
 *
 * Added 2026-08-01 after a client-side exception in the draft room
 * (presets envelope mismatch) replaced the ENTIRE page — nav included —
 * with Next's default "Application error" screen. With this boundary the
 * shell stays up and the failing segment renders a recoverable error card
 * instead.
 */
export default function DashboardError({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <EmptyState
      icon={Icons.warning}
      title='Something went wrong'
      description='This page hit an unexpected error. Your data is fine — try again in a moment.'
      action={
        <Button variant='outline' onClick={() => reset()}>
          Try again
        </Button>
      }
    />
  );
}
