import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { EventBadges } from './EventBadges';

describe('EventBadges (Phase 72)', () => {
  it('returns null when badges is empty', () => {
    const { container } = render(<EventBadges badges={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders existing 12-flag labels', () => {
    render(<EventBadges badges={['Ruled Out', 'Returning']} />);
    expect(screen.getByText('Ruled Out')).toBeInTheDocument();
    expect(screen.getByText('Returning')).toBeInTheDocument();
  });

  it('renders 7 new draft-season flag labels (Phase 72 EVT-01)', () => {
    const newLabels = [
      'Drafted',
      'Rumored Destination',
      'Coaching Change',
      'Trade Buzz',
      'Holdout',
      'Cap Cut',
      'Rookie Buzz'
    ];
    render(<EventBadges badges={newLabels} />);
    for (const label of newLabels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  // Color classes now derive from the semantic design tokens
  // (--success / --danger / --warn) instead of raw Tailwind palette names.
  it('Drafted gets bullish (success) color class', () => {
    render(<EventBadges badges={['Drafted']} />);
    const badge = screen.getByText('Drafted');
    expect(badge.className).toMatch(/--success/);
  });

  it('Cap Cut gets bearish (danger) color class', () => {
    render(<EventBadges badges={['Cap Cut']} />);
    const badge = screen.getByText('Cap Cut');
    expect(badge.className).toMatch(/--danger/);
  });

  it('Coaching Change gets neutral (warn) color class', () => {
    render(<EventBadges badges={['Coaching Change']} />);
    const badge = screen.getByText('Coaching Change');
    expect(badge.className).toMatch(/--warn/);
  });

  it('mixed badges render distinctly with their own bucket colors', () => {
    render(<EventBadges badges={['Drafted', 'Cap Cut', 'Trade Buzz']} />);
    expect(screen.getByText('Drafted').className).toMatch(/--success/);
    expect(screen.getByText('Cap Cut').className).toMatch(/--danger/);
    expect(screen.getByText('Trade Buzz').className).toMatch(/--warn/);
  });
});
