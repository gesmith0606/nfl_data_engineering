import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Live2026Table, type LiveMetrics } from '../live-2026-table';
import { SUCCESS_TEXT, DANGER_TEXT } from '@/lib/nfl/semantic-colors';

const mk = (gap: number) => ({
  n: 100,
  ourMae: 5 + gap,
  sleeperMae: 5,
  trailing3Mae: 6,
  gap,
  rhoOurs: 0.3,
  rhoSleeper: 0.4,
  bandCoverage: 0.5
});

const live: LiveMetrics = {
  weeks: '1–2, 4',
  updated: '2026-11-16',
  overall: mk(0.2),
  positions: [
    { position: 'QB', ...mk(0.5) },
    { position: 'RB', ...mk(-0.3) },
    { position: 'WR', ...mk(0.1) },
    { position: 'TE', ...mk(0.4) }
  ]
};

describe('Live2026Table', () => {
  it('renders the five position rows', () => {
    render(<Live2026Table live={live} />);
    for (const p of ['QB', 'RB', 'WR', 'TE', 'Overall']) {
      expect(screen.getByText(p)).toBeTruthy();
    }
  });

  it('colours gap by sign: positive = losing style, negative = winning style', () => {
    render(<Live2026Table live={live} />);
    expect(screen.getByTestId('gap-QB').className).toContain(DANGER_TEXT.split(' ')[0]);
    expect(screen.getByTestId('gap-RB').className).toContain(SUCCESS_TEXT.split(' ')[0]);
    expect(screen.getByTestId('gap-RB').className).not.toContain(DANGER_TEXT.split(' ')[0]);
  });

  it('takes the weeks label and date from data and makes no claim words', () => {
    render(<Live2026Table live={live} />);
    const text = screen.getByTestId('live-summary').textContent ?? '';
    expect(text).toContain('Weeks covered: 1–2, 4');
    expect(text).toContain('Updated 2026-11-16');
    expect(text).toContain('target ~80%');
    expect(document.body.textContent?.toLowerCase()).not.toMatch(/\b(beat|better)\b/);
  });
});
