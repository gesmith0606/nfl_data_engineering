import { describe, it, expect } from 'vitest';
import { gradeGap, gradeMae } from '../accuracy-grade';

describe('gradeGap', () => {
  it('grades a dominant win (large negative gap) as A+', () => {
    expect(gradeGap(-0.325).grade).toBe('A+');
  });

  it('grades a clear loss (large positive gap) as D — the RB deficit stays visible', () => {
    expect(gradeGap(0.261).grade).toBe('D');
  });

  it('treats a near-zero gap as a statistical tie (B), not a false win/loss', () => {
    expect(gradeGap(-0.006).grade).toBe('B');
    expect(gradeGap(0.006).grade).toBe('B');
  });

  it('is boundary-inclusive at the -0.20 and -0.05 tie thresholds', () => {
    expect(gradeGap(-0.2).grade).toBe('A+');
    expect(gradeGap(-0.05).grade).toBe('A');
    expect(gradeGap(0.05).grade).toBe('B');
  });
});

describe('gradeMae', () => {
  it('grades sub-4.0 MAE as A (Excellent)', () => {
    expect(gradeMae(3.28)).toMatchObject({ grade: 'A', label: 'Excellent' });
  });

  it('grades 6.0+ MAE as D (High)', () => {
    expect(gradeMae(6.28)).toMatchObject({ grade: 'D', label: 'High' });
  });
});
