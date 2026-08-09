/**
 * Unit tests for the shared <BroadcastPanel /> / <StatPill /> primitives —
 * extracted from three near-identical inline implementations (StatCard,
 * ProofStrip, PhaseModule tiles). Covers polymorphism (`as`), rail
 * rendering/color, and the StatPill label/value/sublabel/trend composition.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BroadcastPanel, StatPill } from '@/components/nfl/broadcast-panel';

describe('BroadcastPanel', () => {
  it('renders as a div by default', () => {
    const { container } = render(<BroadcastPanel>content</BroadcastPanel>);
    expect(container.querySelector('div.relative')).toBeInTheDocument();
  });

  it('renders as a different element via `as`', () => {
    const { container } = render(<BroadcastPanel as='section'>content</BroadcastPanel>);
    expect(container.querySelector('section')).toBeInTheDocument();
  });

  it('renders the accent rail by default and hides it when rail=false', () => {
    const { container, rerender } = render(<BroadcastPanel>x</BroadcastPanel>);
    expect(container.querySelector('[aria-hidden]')).toBeInTheDocument();

    rerender(<BroadcastPanel rail={false}>x</BroadcastPanel>);
    expect(container.querySelector('[aria-hidden]')).not.toBeInTheDocument();
  });

  it('applies a custom rail color', () => {
    const { container } = render(<BroadcastPanel railColor='#ffd84d'>x</BroadcastPanel>);
    const rail = container.querySelector('[aria-hidden]') as HTMLElement;
    expect(rail.style.background).toBe('rgb(255, 216, 77)');
  });
});

describe('StatPill', () => {
  it('renders label, value and sublabel', () => {
    render(<StatPill label='Players Tracked' value='569' sublabel='Across all NFL positions' />);
    expect(screen.getByText('Players Tracked')).toBeInTheDocument();
    expect(screen.getByText('569')).toBeInTheDocument();
    expect(screen.getByText('Across all NFL positions')).toBeInTheDocument();
  });

  it('omits the trend badge when trend is not provided', () => {
    render(<StatPill label='Tests Passing' value='100' />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('renders the trend badge when provided', () => {
    render(<StatPill label='ATS Accuracy' value='55.0%' trend='+3.0%' />);
    expect(screen.getByText('+3.0%')).toBeInTheDocument();
  });
});
