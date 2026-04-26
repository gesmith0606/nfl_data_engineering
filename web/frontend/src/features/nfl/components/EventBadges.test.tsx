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

  it('Drafted gets bullish color class', () => {
    render(<EventBadges badges={['Drafted']} />);
    const badge = screen.getByText('Drafted');
    expect(badge.className).toMatch(/green/);
  });

  it('Cap Cut gets bearish color class', () => {
    render(<EventBadges badges={['Cap Cut']} />);
    const badge = screen.getByText('Cap Cut');
    expect(badge.className).toMatch(/red/);
  });

  it('Coaching Change gets neutral color class', () => {
    render(<EventBadges badges={['Coaching Change']} />);
    const badge = screen.getByText('Coaching Change');
    expect(badge.className).toMatch(/yellow/);
  });

  it('mixed badges render distinctly with their own bucket colors', () => {
    render(<EventBadges badges={['Drafted', 'Cap Cut', 'Trade Buzz']} />);
    expect(screen.getByText('Drafted').className).toMatch(/green/);
    expect(screen.getByText('Cap Cut').className).toMatch(/red/);
    expect(screen.getByText('Trade Buzz').className).toMatch(/yellow/);
  });
});
