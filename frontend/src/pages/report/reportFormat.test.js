// Tests for the Assessment Report wording and calculations.

import { describe, expect, it } from 'vitest';

import { compareRows, componentRows, coverageLine, generatingStep, listStatus, reportState } from './reportFormat';

const content = (name, overall) => ({
  position: { headline: `${name} fit` },
  components: {
    cv: { overall, dimensions: { skills: { label: 'Technical skills', score: overall - 5 } } },
    interview: { relevance: 80, accuracy: 70, completeness: 60, articulation: 75 },
    coverage: { explored: 2, total: 3, unexplored: ['AWS Certification'] },
  },
  findings: { strengths: [{ text: `${name} strength` }], weaknesses: [{ text: 'A weakness' }], gaps: [], verify: [] },
});

describe('reportFormat', () => {
  it('derives where the report is', () => {
    const report = (status, review_status) => ({ status, review_status });
    expect(reportState({ analysis: null, report: null })).toBe('none');
    expect(reportState({ analysis: { status: 'running' }, report: null })).toBe('generating');
    expect(reportState({ analysis: { status: 'failed' }, report: null })).toBe('failed');
    expect(reportState({ report: report('running', 'pending_review') })).toBe('generating');
    expect(reportState({ report: report('waiting_for_review', 'pending_review') })).toBe('waiting');
    expect(reportState({ report: report('running', 'changes_requested') })).toBe('changes');
    expect(reportState({ report: report('pending', 'approved') })).toBe('approved');
    expect(reportState({ report: report('failed', 'changes_requested') })).toBe('failed');
  });

  it('shows the active preparation step', () => {
    expect(generatingStep({ analysis: { status: 'running' }, report: null })).toBe(1);
    expect(generatingStep({ analysis: { status: 'completed' }, report: null })).toBe(2);
  });

  it('lists the CV score, then the four interview scores', () => {
    const rows = componentRows(content('Good', 82).components);
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ['CV screening (overall)', 82],
      ['Interview: relevance', 80],
      ['Interview: accuracy', 70],
      ['Interview: completeness', 60],
      ['Interview: articulation', 75],
    ]);
    expect(componentRows({ cv: null, interview: null, coverage: {} })).toEqual([]);
  });

  it('writes the coverage line', () => {
    expect(coverageLine({ explored: 2, total: 3, unexplored: ['AWS'] })).toBe(
      'Requirement coverage: 2 of 3 explored (not explored: AWS)',
    );
    expect(coverageLine({ explored: 3, total: 3, unexplored: [] })).toBe('Requirement coverage: 3 of 3 explored');
  });

  it('labels the Reports list', () => {
    expect(listStatus({ report: null, analysis_status: null }).label).toBe('Not prepared');
    expect(listStatus({ report: null, analysis_status: 'running' }).label).toBe('Being prepared');
    expect(listStatus({ report: null, analysis_status: 'failed' }).tone).toBe('danger');
    const waiting = { status: 'waiting_for_review', review_status: 'pending_review' };
    expect(listStatus({ report: waiting, analysis_status: 'completed' }).label).toBe('Waiting for review');
  });

  it('builds the comparison with one cell per candidate', () => {
    const rows = [
      { report: { content: content('Good', 82), status: 'completed', review_status: 'approved' } },
      { report: { content: content('Strong', 90), status: 'waiting_for_review', review_status: 'pending_review' } },
    ];
    const table = compareRows(rows);
    const row = (label) => table.find((r) => r.label === label).cells.map((c) => c.value);
    expect(row('Suitability position')).toEqual(['Good fit', 'Strong fit']);
    expect(row('CV screening (overall)')).toEqual([82, 90]);
    expect(row('Technical skills')).toEqual([77, 85]);
    expect(row('Requirements explored')).toEqual(['2 of 3', '2 of 3']);
    expect(row('Main gap')).toEqual(['A weakness', 'A weakness']); // no gaps: the first weakness
    expect(row('Review status')).toEqual(['Approved', 'Waiting for review']);
  });
});
