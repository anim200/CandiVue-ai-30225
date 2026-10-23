// Wording for the CV claims, interview score and interview quality tabs
// (F8-F10), kept apart from the components so it can be tested.

import { IconArrowsDiff, IconCircleCheck, IconHelp, IconMinus } from '@tabler/icons-react';

// The four claim results (design: Supported · Contradiction · Unverified ·
// Never discussed), most important first.
export const CLAIM_RESULTS = {
  contradiction: { tone: 'danger', icon: IconArrowsDiff, text: 'Contradiction' },
  unverified: { tone: 'warning', icon: IconHelp, text: 'Unverified' },
  never_discussed: { tone: 'neutral', icon: IconMinus, text: 'Never discussed' },
  supported: { tone: 'success', icon: IconCircleCheck, text: 'Supported' },
};

export const VERDICTS = {
  good: { tone: 'success', text: 'Good' },
  needs_attention: { tone: 'warning', text: 'Needs attention' },
  poor: { tone: 'danger', text: 'Poor' },
};

// How many claims have each result: [["contradiction", 1], ...] (only > 0).
export function claimCounts(claims) {
  return Object.keys(CLAIM_RESULTS)
    .map((result) => [result, claims.filter((c) => c.result === result).length])
    .filter(([, count]) => count > 0);
}

// The colour of a 0-100 score: green from 70, amber from 50, red below.
export function scoreTone(score) {
  if (score == null) return 'neutral';
  return score >= 70 ? 'success' : score >= 50 ? 'warning' : 'danger';
}

// The message put in the Hiring Assistant's box for a new interview.
export function rescheduleRequest(interview, quality) {
  const day = new Date(interview.started_at ?? interview.scheduled_at).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
  });
  const why = quality.reasons.join(' ').replace(/\.$/, '');
  return (
    `Please invite ${interview.candidate_name} to a new interview (invite again): ` +
    `the interview on ${day} was rated poor quality (${why}).`
  );
}
