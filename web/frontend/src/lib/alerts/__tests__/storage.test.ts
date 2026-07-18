import { beforeEach, describe, expect, it } from 'vitest';

import {
  ALERTS_LAST_SEEN_KEY,
  loadAlertsLastSeen,
  saveAlertsLastSeen
} from '@/lib/alerts/storage';

describe('alerts last-seen storage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns null when nothing is stored', () => {
    expect(loadAlertsLastSeen()).toBeNull();
  });

  it('round-trips a saved timestamp', () => {
    const saved = saveAlertsLastSeen('2026-07-16T12:00:00.000Z');
    expect(saved).toBe('2026-07-16T12:00:00.000Z');
    expect(loadAlertsLastSeen()).toBe('2026-07-16T12:00:00.000Z');
  });

  it('defaults to now when called without a value', () => {
    const before = Date.now();
    const saved = saveAlertsLastSeen();
    expect(Date.parse(saved)).toBeGreaterThanOrEqual(before);
    expect(loadAlertsLastSeen()).toBe(saved);
  });

  it('returns null for corrupted stored values', () => {
    localStorage.setItem(ALERTS_LAST_SEEN_KEY, 'garbage');
    expect(loadAlertsLastSeen()).toBeNull();
  });
});
