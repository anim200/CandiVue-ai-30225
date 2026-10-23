// Wording and small calculations for the Assessment Report and Reports
// pages (F6), kept apart from the components so they can be tested.

export const POSITIONS = [
  ['not_yet_suitable', 'Not yet suitable'],
  ['partial_fit', 'Partial fit'],
  ['good_fit', 'Good fit'],
  ['strong_fit', 'Strong fit'],
];

export const INTERVIEW_DIMENSIONS = [
  ['relevance', 'Interview: relevance'],
  ['accuracy', 'Interview: accuracy'],
  ['completeness', 'Interview: completeness'],
  ['articulation', 'Interview: articulation'],
];

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

// The rows of the component scores card: CV screening, then the interview.
export function componentRows(components) {
  const rows = [];
  if (components.cv) {
    rows.push({ label: 'CV screening (overall)', value: components.cv.overall, part: 'cv' });
  }
  if (components.interview) {
    for (const [key, label] of INTERVIEW_DIMENSIONS) {
      rows.push({ label, value: components.interview[key], part: 'interview' });
    }
  }
  return rows;
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
    ...INTERVIEW_DIMENSIONS.map(([key, label]) => ({
      label,
      cells: content.map((c) => bar(c.components.interview?.[key])),
    })),
    {
      label: 'Requirements explored',
      cells: content.map((c) => text(`${c.components.coverage.explored} of ${c.components.coverage.total}`)),
    },
    { label: 'Main strength', cells: content.map((c) => text(c.findings.strengths[0]?.text)) },
    { label: 'Main gap', cells: content.map((c) => text((c.findings.gaps[0] ?? c.findings.weaknesses[0])?.text)) },
    { label: 'Review status', cells: rows.map((row) => text(listStatus(row).label)) },
  ];
}
