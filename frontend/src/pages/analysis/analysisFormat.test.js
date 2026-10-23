// Tests for the Interview Analysis wording and calculations.

import { describe, expect, it } from 'vitest';

import { clock, coverageSummary, filterTurns, isRunning, pairOfTurn, pairTags, transcriptText } from './analysisFormat';

const turns = [
  { id: 1, speaker: 'interviewer', text: 'How do you test Laravel?', start_ms: 4000 },
  { id: 2, speaker: 'candidate', text: 'With PHPUnit.', start_ms: 167000 },
];

describe('analysisFormat', () => {
  it('reads times like a clock', () => {
    expect(clock(167000)).toBe('02:47');
    expect(clock(3727000)).toBe('1:02:07');
  });

  it('knows when a run still works', () => {
    expect(isRunning({ status: 'pending' })).toBe(true);
    expect(isRunning({ status: 'running' })).toBe(true);
    expect(isRunning({ status: 'failed' })).toBe(false);
    expect(isRunning(null)).toBe(false);
  });

  it('tags parts, follow-ups and company questions', () => {
    expect(pairTags({ part: [1, 2], follow_up_of: null, kind: 'job' })).toEqual(['part 1 of 2']);
    expect(pairTags({ part: null, follow_up_of: 'Q2', kind: 'company' })).toEqual([
      'follow-up to Q2',
      'company question',
    ]);
  });

  it('summarises the coverage', () => {
    const results = {
      scored: 1,
      coverage: [
        { requirement: 'PHP', pair_ids: ['Q1'] },
        { requirement: 'AWS', pair_ids: [] },
      ],
    };
    expect(coverageSummary(results)).toBe(
      '1 of 2 requirements explored · 1 job-related Q&A unit scored · greetings and small talk not scored',
    );
  });

  it('links each turn to the first unit that uses it', () => {
    const ids = pairOfTurn([
      { id: 'Q1a', turn_ids: [1, 2] },
      { id: 'Q1b', turn_ids: [1, 3] },
    ]);
    expect([ids.get(1), ids.get(2), ids.get(3)]).toEqual(['Q1a', 'Q1a', 'Q1b']);
  });

  it('filters by words and speaker', () => {
    expect(filterTurns(turns, 'phpunit', 'all').map((t) => t.id)).toEqual([2]);
    expect(filterTurns(turns, '', 'interviewer').map((t) => t.id)).toEqual([1]);
    expect(filterTurns(turns, 'laravel', 'candidate')).toEqual([]);
  });

  it('writes the transcript as text', () => {
    expect(transcriptText(turns)).toBe('[00:04] Interviewer: How do you test Laravel?\n[02:47] Candidate: With PHPUnit.');
  });
});
