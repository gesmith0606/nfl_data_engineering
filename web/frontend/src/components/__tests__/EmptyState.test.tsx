/**
 * Unit tests for the shared <EmptyState /> component (Phase 70-01).
 *
 * Covers:
 *   - Title renders (required prop)
 *   - Description renders when provided, absent when omitted
 *   - Icon renders when provided (Tabler icon → svg)
 *   - dataAsOf:
 *       null      → no "Updated ..." badge
 *       undefined → no "Updated ..." badge
 *       recent ISO → "Updated about 1 hour ago" (date-fns relative format)
 *       > 7 days   → absolute calendar date ("Updated Apr 14, 2026")
 *   - aria-live="polite" is present for screen readers
 *   - data-testid="empty-state" lets integration tests find the card
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Icons } from '@/components/icons';
import { EmptyState } from '@/components/EmptyState';

describe('EmptyState', () => {
  it('renders the title', () => {
    render(<EmptyState title='No predictions yet' />);
    expect(screen.getByText('No predictions yet')).toBeInTheDocument();
  });

  it('renders the description when provided', () => {
    render(
      <EmptyState title='Nothing here' description='Games start Week 1' />
    );
    expect(screen.getByText('Games start Week 1')).toBeInTheDocument();
  });

  it('omits the description paragraph when not provided', () => {
    const { container } = render(<EmptyState title='Nothing' />);
    // Only the heading <h2> should exist — no <p> underneath.
    expect(container.querySelector('p')).toBeNull();
  });

  it('renders an icon when provided', () => {
    const { container } = render(
      <EmptyState title='Empty' icon={Icons.news} />
    );
    // Tabler icons render as an inline <svg>.
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('suppresses the dataAsOf badge when null', () => {
    render(<EmptyState title='Nothing' dataAsOf={null} />);
    expect(screen.queryByText(/Updated/)).not.toBeInTheDocument();
  });

  it('suppresses the dataAsOf badge when undefined', () => {
    render(<EmptyState title='Nothing' />);
    expect(screen.queryByText(/Updated/)).not.toBeInTheDocument();
  });

  it('renders dataAsOf as relative time when recent', () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    render(<EmptyState title='Nothing' dataAsOf={oneHourAgo} />);
    // date-fns yields "about 1 hour" for this window; our helper adds " ago".
    expect(screen.getByText(/Updated .*hour.* ago/)).toBeInTheDocument();
  });

  it('renders dataAsOf as absolute date when older than 7 days', () => {
    const tenDaysAgo = new Date(
      Date.now() - 10 * 24 * 60 * 60 * 1000
    ).toISOString();
    render(<EmptyState title='Nothing' dataAsOf={tenDaysAgo} />);
    // Format: "Updated Apr 14, 2026" — month name + day + 4-digit year.
    expect(
      screen.getByText(/Updated [A-Z][a-z]+ \d{1,2}, \d{4}/)
    ).toBeInTheDocument();
  });

  it('exposes aria-live="polite" for screen readers', () => {
    render(<EmptyState title='Nothing' />);
    expect(screen.getByTestId('empty-state')).toHaveAttribute(
      'aria-live',
      'polite'
    );
  });

  it('renders the "just now" label when timestamp is within the last minute', () => {
    const twentySecAgo = new Date(Date.now() - 20 * 1000).toISOString();
    render(<EmptyState title='Nothing' dataAsOf={twentySecAgo} />);
    expect(screen.getByText('Updated just now')).toBeInTheDocument();
  });
});
