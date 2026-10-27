// Wording and small calculations for the Assessment Report and Reports
// pages (F6), kept apart from the components so they can be tested.

export const POSITIONS = [
  ['not_yet_suitable', 'Not yet suitable'],
  ['partial_fit', 'Partial fit'],
  ['good_fit', 'Good fit'],
  ['strong_fit', 'Strong fit'],
];

const QUALITY = { good: 'Good', needs_attention: 'Needs attention', poor: 'Poor' };

// The review bar per state (design: ReviewBar).
export const REVIEW = {
  waiting: {
    tone: 'warning',
    label: 'Waiting for review',
    hint: 'Approving makes the report final. Nothing is sent to the candidate.',
  },
  changes: { tone: 'harbor', label: 'Changes requested', hint: 'The report is being updated. You’ll review it again.' },
  approved: { tone: 'success', label: 'Approved', hint: 'Final. You can export or print it.' },
};

// Where the report is, from the report page's data: none, generating,
// failed, waiting (for review), changes (being rewritten) or approved.
export function reportState({ analysis, report }) {
  if (report) {
    if (report.status === 'failed') return 'failed';
    if (report.review_status === 'approved') return 'approved';
    if (report.review_status === 'changes_requested') return 'changes';
    if (report.status === 'waiting_for_review') return 'waiting';
    return 'generating';
  }
  if (analysis?.status === 'failed') return 'failed';
  return analysis ? 'generating' : 'none';
}

// The active step while the report is prepared: 1 = Q&A analysis,
// 2 = final assessment (step 0, "Interview ended", is always done).
export function generatingStep({ analysis, report }) {
  return report || analysis?.status === 'completed' ? 2 : 1;
}

// The six interview dimensions (F9) as [key, label], from the reports given
// (a report from before the interview score has none).
function interviewDimensions(contents) {
  const labels = new Map();
  for (const c of contents) {
    for (const [key, dim] of Object.entries(c.components.interview?.dimensions ?? {})) labels.set(key, dim.label);
  }
  return [...labels];
}

// The rows of the component scores card: CV screening, then the interview
// score and its six dimensions (a dimension without evidence has no value).
export function componentRows(components) {
  const rows = [];
  if (components.cv) {
    rows.push({ label: 'CV screening (overall)', value: components.cv.overall, part: 'cv' });
  }
  if (components.interview) {
    rows.push({ label: 'Interview score (overall)', value: components.interview.overall, part: 'interview' });
    for (const [key, label] of interviewDimensions([{ components }])) {
      rows.push({ label: `Interview: ${label}`, value: components.interview.dimensions[key].score, part: 'interview' });
    }
  }
  return rows;
}

// "1 contradiction, 2 unverified" for the CV claims to follow up (F8).
export function claimsSummary(claims = []) {
  const count = (result) => claims.filter((c) => c.result === result).length;
  const parts = [
    [count('contradiction'), 'contradiction', 'contradictions'],
    [count('unverified'), 'unverified', 'unverified'],
    [count('never_discussed'), 'never discussed', 'never discussed'],
  ].filter(([n]) => n > 0);
  return parts.map(([n, one, many]) => `${n} ${n === 1 ? one : many}`).join(', ') || 'None';
}

// "Requirement coverage: 2 of 3 explored (not explored: AWS Certification)".
export function coverageLine(coverage) {
  const missing = coverage.unexplored.length ? ` (not explored: ${coverage.unexplored.join('; ')})` : '';
  return `Requirement coverage: ${coverage.explored} of ${coverage.total} explored${missing}`;
}

// The status of one row of the Reports list.
export function listStatus(row) {
  const { report, analysis_status: analysis } = row;
  if (report?.status === 'failed' || (!report && analysis === 'failed')) {
    return { tone: 'danger', label: 'Couldn’t be prepared' };
  }
  if (!report && !analysis) return { tone: 'neutral', label: 'Not prepared' };
  const state = report ? reportState({ report }) : 'generating';
  if (state === 'generating') return { tone: 'info', label: 'Being prepared' };
  return { tone: REVIEW[state].tone, label: REVIEW[state].label };
}

// The comparison table (design: CompareCandidatesTable): one row per
// dimension, one cell per candidate; bars for scores, text otherwise.
export function compareRows(rows) {
  const content = rows.map((row) => row.report.content);
  const cvKeys = [...new Set(content.flatMap((c) => Object.keys(c.components.cv?.dimensions ?? {})))];
  const bar = (value) => ({ kind: 'bar', value });
  const text = (value) => ({ kind: 'text', value });
  return [
    { label: 'Suitability position', head: true, cells: content.map((c) => text(c.position.headline)) },
    { label: 'CV screening (overall)', cells: content.map((c) => bar(c.components.cv?.overall)) },
    ...cvKeys.map((key) => ({
      label: content.find((c) => c.components.cv?.dimensions[key])?.components.cv.dimensions[key].label,
      sub: true,
      cells: content.map((c) => bar(c.components.cv?.dimensions[key]?.score)),
    })),
    { label: 'Interview score (overall)', cells: content.map((c) => bar(c.components.interview?.overall)) },
    ...interviewDimensions(content).map(([key, label]) => ({
      label,
      sub: true,
      cells: content.map((c) => bar(c.components.interview?.dimensions?.[key]?.score)),
    })),
    {
      label: 'Requirements explored',
      cells: content.map((c) => text(`${c.components.coverage.explored} of ${c.components.coverage.total}`)),
    },
    { label: 'Main strength', cells: content.map((c) => text(c.findings.strengths[0]?.text)) },
    { label: 'Main gap', cells: content.map((c) => text((c.findings.gaps[0] ?? c.findings.weaknesses[0])?.text)) },
    { label: 'CV claims to follow up', cells: content.map((c) => text(c.claims && claimsSummary(c.claims))) },
    { label: 'Interview quality', cells: content.map((c) => text(c.quality && QUALITY[c.quality.verdict])) },
    { label: 'Identity', cells: content.map((c) => text(c.identity?.text)) },
    { label: 'Review status', cells: rows.map((row) => text(listStatus(row).label)) },
  ];
}

// A warning for the selection email when the identity check (F7) did not
// confirm the candidate: from a report ("confirmed", ...) or from the
// final ranking ("matched", ...). None when it matched or is not set up.
const NOT_CHECKED = ['no_photo', 'declined', 'waiting', 'not_checked'];
export function identityWarning(identity) {
  if (!identity || ['confirmed', 'matched', 'off'].includes(identity.state)) return null;
  const detail = identity.text.replace(/^(No comparison|Not checked): /, '').replace(/\.$/, '');
  const said = detail.charAt(0).toLowerCase() + detail.slice(1);
  return NOT_CHECKED.includes(identity.state)
    ? `The face check was not done: ${said}. Make sure you are emailing the right person.`
    : `The face check did not confirm this candidate: ${said}.`;
}

// Short names for the radar's corners (the full names are in the bars).
const SHORT = {
  'Response relevance': 'Relevance',
  'Technical competency': 'Technical',
  'Job alignment': 'Alignment',
  'Problem-solving approach': 'Problem-solving',
  'Experience depth': 'Depth',
};

// The radar chart of the interview dimensions (F9): one point per dimension
// that has a score for at least one candidate, one series per candidate
// ({ name, content }). Fewer than three dimensions make no radar: [].
export function radarData(candidates) {
  const contents = candidates.map((c) => c.content);
  const points = interviewDimensions(contents)
    .map(([key, label]) => {
      const point = { dimension: SHORT[label] ?? label };
      for (const { name, content } of candidates) {
        point[name] = content.components.interview?.dimensions?.[key]?.score ?? null;
      }
      return point;
    })
    .filter((point) => candidates.some(({ name }) => point[name] != null));
  return points.length >= 3 ? points : [];
}
