// Tests for the home page wording.

import { describe, expect, it } from 'vitest';

import { chartDays, firstName, greeting, interviewTime, plural } from './homeFormat';

describe('home page wording', () => {
  it('greets by the time of day', () => {
    expect(greeting(8)).toBe('Good morning');
    expect(greeting(13)).toBe('Good afternoon');
    expect(greeting(20)).toBe('Good evening');
  });

  it('uses the first name', () => {
    expect(firstName('Interviewer A')).toBe('Interviewer');
    expect(firstName('  ')).toBe('');
    expect(firstName(undefined)).toBe('');
  });

  it('says today and tomorrow for near interviews', () => {
    const now = new Date(2026, 9, 23, 9, 0);
    expect(interviewTime(new Date(2026, 9, 23, 10, 30).toISOString(), now)).toBe('Today, 10:30');
    expect(interviewTime(new Date(2026, 9, 24, 9, 0).toISOString(), now)).toBe('Tomorrow, 09:00');
    expect(interviewTime(new Date(2026, 9, 27, 14, 0).toISOString(), now)).toBe('Tue 27 Oct, 14:00');
  });

  it('labels the chart days', () => {
    expect(chartDays([{ day: '2026-10-23', count: 3 }])).toEqual([{ day: 'Fri 23', Applications: 3 }]);
  });

  it('writes counts in words', () => {
    expect(plural(1, 'application')).toBe('1 application');
    expect(plural(3, 'application')).toBe('3 applications');
  });
});
