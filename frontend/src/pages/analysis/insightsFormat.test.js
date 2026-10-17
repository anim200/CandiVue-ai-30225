import { describe, expect, it } from 'vitest';

import { claimCounts, rescheduleRequest, scoreTone } from './insightsFormat';

describe('CV claims (F8)', () => {
  it('counts each result, most important first, leaving out empty ones', () => {
    const claims = [{ result: 'supported' }, { result: 'contradiction' }, { result: 'supported' }];
    expect(claimCounts(claims)).toEqual([
      ['contradiction', 1],
      ['supported', 2],
    ]);
  });
});

describe('interview score (F9)', () => {
  it('colours a score by its band, and a missing one as neutral', () => {
    expect([scoreTone(85), scoreTone(70), scoreTone(55), scoreTone(20), scoreTone(null)]).toEqual([
      'success',
      'success',
      'warning',
      'danger',
      'neutral',
    ]);
  });
});

describe('interview quality (F10)', () => {
  it('prepares a re-invitation request with the reasons', () => {
    const interview = { candidate_name: 'Alex Strong', started_at: '2026-10-14T04:01:00Z' };
    const quality = { reasons: ['Only 2 job-related questions were answered.'] };
    expect(rescheduleRequest(interview, quality)).toBe(
      'Please invite Alex Strong to a new interview (invite again): the interview on 14 Oct was rated ' +
        'poor quality (Only 2 job-related questions were answered).',
    );
  });
});
