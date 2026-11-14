import { describe, it, expect } from 'vitest';
import {
  BREAK_EVEN_PROB,
  clearsBreakEven,
  formatCoverProb,
  formatCoverProbCompact,
  pickConfidenceLabel
} from '../pick-confidence';

describe('BREAK_EVEN_PROB', () => {
  it('is the -110 break-even rate, not a round 50%', () => {
    expect(BREAK_EVEN_PROB).toBeCloseTo(110 / 210, 4);
  });
});

describe('clearsBreakEven', () => {
  it('rejects a coin flip — 50% loses money at -110', () => {
    expect(clearsBreakEven(0.5)).toBe(false);
  });

  it('rejects the real week-7 away pick that sat just under the line', () => {
    expect(clearsBreakEven(0.5231)).toBe(false);
  });

  it('accepts the real week-7 away pick that cleared it', () => {
    // 1 - 0.4469 = 0.5531, the away side of CIN@BAL.
    expect(clearsBreakEven(0.5531)).toBe(true);
  });

  it('is inclusive exactly at break-even', () => {
    expect(clearsBreakEven(BREAK_EVEN_PROB)).toBe(true);
  });

  it('treats a missing probability as no claim of an edge', () => {
    expect(clearsBreakEven(null)).toBe(false);
  });
});

describe('formatCoverProb', () => {
  it('reads as a probability, not a points figure', () => {
    expect(formatCoverProb(0.5531)).toBe('55.3% cover');
  });
});

describe('formatCoverProbCompact', () => {
  it('shows the probability when one exists', () => {
    expect(formatCoverProbCompact(0.5243, 4.0)).toBe('52.4%');
  });

  it('falls back to the edge for uncalibrated boards', () => {
    expect(formatCoverProbCompact(null, -4.26)).toBe('4.3pt');
  });

  it('shows a dash rather than a fabricated 0', () => {
    expect(formatCoverProbCompact(null, null)).toBe('—');
  });
});

describe('pickConfidenceLabel', () => {
  it('prefers the probability over the edge when both exist', () => {
    // The edge is the misleading signal this replaced: a 3+ pt edge hit only
    // 57% ATS on sealed 2025, so edge size must never win over the calibrator.
    expect(pickConfidenceLabel(0.5531, 8.0)).toBe('55.3% cover');
  });

  it('falls back to the absolute edge when no calibrator ran', () => {
    expect(pickConfidenceLabel(null, -2.5)).toBe('2.5pt edge');
  });

  it('never renders an empty label', () => {
    expect(pickConfidenceLabel(null, null)).toBe('—');
  });
});
