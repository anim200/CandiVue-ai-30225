// The pipeline board and the score distribution on the job page, kept apart
// from the components so they can be tested.

// The board's columns, left to right, and which steps each one holds
// (the steps come from the backend: screening's "pipeline").
export const COLUMNS = [
  { key: 'new', title: 'Screened', steps: ['new'] },
  { key: 'shortlisted', title: 'Shortlisted', steps: ['shortlisted'] },
  { key: 'invited', title: 'Invited', steps: ['invitation_pending', 'invited', 'invitation_failed'] },
  { key: 'interviewed', title: 'Interviewed', steps: ['in_interview', 'interviewed'] },
  { key: 'selected', title: 'Selected', steps: ['selected'] },
];

// The candidates per column (best rank first), plus the excluded ones.
export function pipelineColumns(ranked, excluded) {
  const byRank = [...ranked].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
  const columns = COLUMNS.map((column) => ({
    ...column,
    cards: byRank.filter((result) => column.steps.includes(result.pipeline)),
  }));
  // An excluded candidate the interviewer still moved on (e.g. invited)
  // appears in that column, not under "Excluded".
  const movedOn = excluded.filter((result) => result.pipeline !== 'new');
  for (const result of movedOn) {
    columns.find((column) => column.steps.includes(result.pipeline))?.cards.push(result);
  }
  return {
    columns,
    excluded: excluded.filter((result) => result.pipeline === 'new'),
  };
}

// How many ranked candidates fall in each 10-point score band (0-9 ... 90-100).
export function scoreBands(ranked) {
  const bands = Array.from({ length: 10 }, (_, i) => ({
    band: i === 9 ? '90–100' : `${i * 10}–${i * 10 + 9}`,
    Candidates: 0,
  }));
  for (const result of ranked) {
    if (result.overall == null) continue;
    bands[Math.min(9, Math.floor(result.overall / 10))].Candidates += 1;
  }
  return bands;
}

// Whole-number ticks 0, 1, 2 ... for a small count chart (the chart's own
// ticks skip numbers, e.g. 0, 1, 2, 4); undefined above 6 so it picks.
export function countTicks(bands) {
  const top = Math.max(0, ...bands.map((b) => b.Candidates));
  return top <= 6 ? Array.from({ length: top + 1 }, (_, i) => i) : undefined;
}
