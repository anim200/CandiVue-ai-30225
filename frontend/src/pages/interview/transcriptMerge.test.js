// Tests for merging transcript turns.

import { describe, expect, it } from 'vitest';

import { mergeTurns } from './transcriptMerge';

const turn = (id, text, end = 1000) => ({ id, speaker: 'candidate', text, start_ms: 0, end_ms: end });

describe('mergeTurns', () => {
  it('adds new turns and updates a growing one', () => {
    const first = mergeTurns(new Map(), [turn(1, 'I have')]);
    const grown = mergeTurns(first, [turn(1, 'I have five years', 2000), turn(2, 'Next')]);

    expect(grown.get(1).text).toBe('I have five years');
    expect(grown.size).toBe(2);
  });

  it('keeps the same Map when nothing changed (no re-render)', () => {
    const turns = mergeTurns(new Map(), [turn(1, 'Hello')]);

    expect(mergeTurns(turns, [turn(1, 'Hello')])).toBe(turns);
    expect(mergeTurns(turns, [])).toBe(turns);
  });
});
