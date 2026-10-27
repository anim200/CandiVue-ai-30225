// Tests for the call timer helpers.

import { describe, expect, it } from 'vitest';

import { formatElapsed, overText, startsIn } from './callTime';

describe('formatElapsed', () => {
  it('shows minutes and seconds under an hour', () => {
    expect(formatElapsed(65)).toBe('01:05');
  });

  it('shows hours instead of hundreds of minutes', () => {
    // The old timer showed "269:44" here.
    expect(formatElapsed(4 * 3600 + 29 * 60 + 44)).toBe('4:29:44');
  });

  it('never goes below zero', () => {
    expect(formatElapsed(-5)).toBe('00:00');
  });
});

describe('startsIn', () => {
  const now = Date.parse('2026-10-13T10:00:00Z');

  it('says how long until the interview', () => {
    expect(startsIn('2026-10-13T10:04:00Z', now)).toBe('in 4 min');
    expect(startsIn('2026-10-13T13:05:00Z', now)).toBe('in 3 h 05 min');
    expect(startsIn('2026-10-16T10:00:00Z', now)).toBe('in 3 days');
  });

  it('is empty once the time has come', () => {
    expect(startsIn('2026-10-13T09:00:00Z', now)).toBeNull();
  });
});

describe('overText', () => {
  it('uses minutes, then hours and minutes', () => {
    expect(overText(12)).toBe('+12 min over');
    // The old page showed "+1617 min over" here.
    expect(overText(1617)).toBe('+26 h 57 min over');
  });
});
