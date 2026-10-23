// Tests for the pipeline board columns and the score bands.

import { describe, expect, it } from 'vitest';

import { countTicks, pipelineColumns, scoreBands } from './pipelineFormat';

const ranked = [
  { candidate_id: 1, rank: 2, overall: 81, pipeline: 'shortlisted' },
  { candidate_id: 2, rank: 1, overall: 90, pipeline: 'invited' },
  { candidate_id: 3, rank: 3, overall: 64, pipeline: 'new' },
  { candidate_id: 4, rank: 4, overall: 55, pipeline: 'invitation_failed' },
  { candidate_id: 5, rank: 5, overall: 100, pipeline: 'selected' },
  { candidate_id: 6, rank: 6, overall: 70, pipeline: 'in_interview' },
];
const excluded = [
  { candidate_id: 7, rank: null, overall: null, pipeline: 'new' },
  { candidate_id: 8, rank: null, overall: null, pipeline: 'shortlisted' },
];

describe('pipeline board', () => {
  it('puts each candidate in the column of their step, best rank first', () => {
    const { columns } = pipelineColumns(ranked, excluded);
    const ids = Object.fromEntries(columns.map((c) => [c.key, c.cards.map((r) => r.candidate_id)]));

    expect(ids).toEqual({
      new: [3],
      shortlisted: [1, 8],
      invited: [2, 4],
      interviewed: [6],
      selected: [5],
    });
  });

  it('keeps excluded candidates apart unless they were moved on', () => {
    expect(pipelineColumns(ranked, excluded).excluded.map((r) => r.candidate_id)).toEqual([7]);
  });
});

describe('score bands', () => {
  it('counts ranked candidates per 10-point band', () => {
    const bands = scoreBands(ranked);

    expect(bands).toHaveLength(10);
    expect(bands[9]).toEqual({ band: '90–100', Candidates: 2 }); // 90 and 100
    expect(bands[8].Candidates).toBe(1); // 81
    expect(bands[5].Candidates).toBe(1); // 55
    expect(bands.reduce((sum, b) => sum + b.Candidates, 0)).toBe(6);
  });

  it('skips candidates without a score', () => {
    expect(scoreBands(excluded).every((b) => b.Candidates === 0)).toBe(true);
  });

  it('gives whole-number ticks for small counts only', () => {
    expect(countTicks(scoreBands(ranked))).toEqual([0, 1, 2]);
    expect(countTicks(scoreBands(excluded))).toEqual([0]);
    expect(countTicks([{ band: 'x', Candidates: 7 }])).toBeUndefined();
  });
});
