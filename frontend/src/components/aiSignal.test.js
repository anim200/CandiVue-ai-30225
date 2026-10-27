import { describe, expect, it } from 'vitest';

import { CHAT_STEPS, formatElapsed, screeningStatus, stepAt } from './aiSignal';

describe('AI signal status helpers', () => {
  it('shows seconds, then minutes with two-digit seconds', () => {
    expect(formatElapsed(0)).toBe('0s');
    expect(formatElapsed(4900)).toBe('4s');
    expect(formatElapsed(59999)).toBe('59s');
    expect(formatElapsed(65000)).toBe('1m 05s');
    expect(formatElapsed(-500)).toBe('0s'); // clock differences never go negative
  });

  it('moves one step per period and stays on the last one', () => {
    const steps = ['Reading CVs…', 'Matching skills to the job…', 'Linking evidence…', 'Drafting summary…'];

    expect(stepAt(steps, 0, 2500)).toBe('Reading CVs…');
    expect(stepAt(steps, 2600, 2500)).toBe('Matching skills to the job…');
    expect(stepAt(steps, 7600, 2500)).toBe('Drafting summary…');
    expect(stepAt(steps, 600000, 2500)).toBe('Drafting summary…'); // never loops back
    expect(stepAt(CHAT_STEPS.message, 9000, 2500)).toBe('Thinking…');
  });

  it('describes the screening progress from the run', () => {
    expect(screeningStatus({ processed: 0, total: 0 })).toBe('Reading CVs…');
    expect(screeningStatus({ processed: 2, total: 5 })).toBe('Screening CV 3 of 5…');
    expect(screeningStatus({ processed: 5, total: 5 })).toBe('Screening CV 5 of 5…');
  });
});
