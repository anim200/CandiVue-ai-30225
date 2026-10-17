// Wording and small calculations for the Interview Analysis page (F5),
// kept apart from the components so they can be tested.

import { formatElapsed } from '../interview/callTime';

export const DIMENSIONS = [
  ['relevance', 'Relevance'],
  ['accuracy', 'Accuracy'],
  ['completeness', 'Completeness'],
  ['articulation', 'Articulation'],
];

// A background run that is still working.
export function isRunning(run) {
  return run?.status === 'pending' || run?.status === 'running';
}

// Milliseconds from the start of the interview as a clock: "02:47".
export function clock(ms) {
  return formatElapsed(ms / 1000);
}

// The small tags under a question: "part 1 of 2", "follow-up to Q2".
export function pairTags(pair) {
  const tags = [];
  if (pair.part) tags.push(`part ${pair.part[0]} of ${pair.part[1]}`);
  if (pair.follow_up_of) tags.push(`follow-up to ${pair.follow_up_of}`);
  if (pair.kind === 'company') tags.push('company question');
  return tags;
}

// "5 of 6 requirements explored · 7 job-related Q&A units scored · ..."
export function coverageSummary(results) {
  const explored = results.coverage.filter((c) => c.pair_ids.length).length;
  const units = results.scored === 1 ? 'Q&A unit' : 'Q&A units';
  return (
    `${explored} of ${results.coverage.length} requirements explored · ` +
    `${results.scored} job-related ${units} scored · greetings and small talk not scored`
  );
}

// The Q&A unit each transcript turn belongs to (its Q id in the margin).
export function pairOfTurn(pairs) {
  const ids = new Map();
  for (const pair of pairs) {
    for (const turnId of pair.turn_ids) if (!ids.has(turnId)) ids.set(turnId, pair.id);
  }
  return ids;
}

// The turns that match the search words and the speaker filter.
export function filterTurns(turns, query, speaker) {
  const words = query.trim().toLowerCase();
  return turns.filter(
    (turn) =>
      (speaker === 'all' || turn.speaker === speaker) && (!words || turn.text.toLowerCase().includes(words)),
  );
}

// The transcript as plain text for the download: "[02:47] Candidate: ...".
export function transcriptText(turns) {
  return turns
    .map((turn) => `[${clock(turn.start_ms)}] ${turn.speaker === 'interviewer' ? 'Interviewer' : 'Candidate'}: ${turn.text}`)
    .join('\n');
}
