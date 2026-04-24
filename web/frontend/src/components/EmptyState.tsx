'use client';

import * as React from 'react';

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { type Icon } from '@/components/icons';
import { formatRelativeTime } from '@/lib/format-relative-time';
import { cn } from '@/lib/utils';

/**
 * Props for the shared EmptyState card.
 *
 * - `icon`: An icon component from `@/components/icons` (Tabler icon). Rendered
 *   centered above the title when provided.
 * - `title`: The primary empty-state heading (required).
 * - `description`: Optional secondary line — context or call-to-action.
 * - `dataAsOf`: Optional ISO timestamp (or Date). When present, a muted
 *   "Updated <relative time>" badge is appended below the description. When
 *   null/undefined, the badge is suppressed cleanly (no "unknown" garbage).
 * - `className`: Optional extra classes for the outer Card.
 */
export interface EmptyStateProps {
  icon?: Icon;
  title: string;
  description?: string;
  dataAsOf?: string | Date | null;
  className?: string;
}

/**
 * Shared minimal-card empty state.
 *
 * Phase 70-01 (v7.0 Production Stabilization): added to replace four
 * near-duplicate inline empty states across the predictions, lineups,
 * matchups, and news pages. The single source of truth keeps copy, spacing,
 * and accessibility consistent when offseason / partial-data conditions are
 * hit.
 *
 * Accessibility:
 * - `aria-live="polite"` so screen readers announce the empty state when it
 *   replaces a loading skeleton.
 * - `data-testid="empty-state"` for integration tests.
 *
 * See `.planning/phases/70-frontend-empty-states/70-01-empty-states-and-freshness-PLAN.md`.
 */
export function EmptyState({
  icon: IconCmp,
  title,
  description,
  dataAsOf,
  className
}: EmptyStateProps) {
  return (
    <Card
      className={cn('mx-auto my-[var(--space-8)] max-w-md', className)}
      data-testid='empty-state'
      aria-live='polite'
    >
      <CardContent className='flex flex-col items-center gap-[var(--space-3)] py-[var(--space-12)] text-center'>
        {IconCmp ? (
          <IconCmp
            className='h-[var(--space-10)] w-[var(--space-10)] text-muted-foreground'
            aria-hidden
          />
        ) : null}
        <h2 className='text-[length:var(--fs-lg)] leading-[var(--lh-lg)] font-semibold'>
          {title}
        </h2>
        {description ? (
          <p className='max-w-sm text-[length:var(--fs-sm)] leading-[var(--lh-sm)] text-muted-foreground'>
            {description}
          </p>
        ) : null}
        {dataAsOf ? (
          <Badge
            variant='outline'
            className='mt-[var(--space-2)] text-[length:var(--fs-xs)] leading-[var(--lh-xs)] text-muted-foreground'
          >
            Updated {formatRelativeTime(dataAsOf)}
          </Badge>
        ) : null}
      </CardContent>
    </Card>
  );
}
