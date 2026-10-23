// Tests for the Assessment Report wording and calculations.

import { describe, expect, it } from 'vitest';

import {
  claimsSummary,
  compareRows,
  componentRows,
  coverageLine,
  generatingStep,
  identityWarning,
  listStatus,
  radarData,
  reportState,
} from './reportFormat';

const content = (name, overall) => ({
  position: { headline: `${name} fit` },
  components: {
    cv: { overall, dimensions: { skills: { label: 'Technical skills', score: overall - 5 } } },
    interview: {
      overall: 72,
      dimensions: {
        technical: { label: 'Technical competency', score: 70 },
        experience_depth: { label: 'Experience depth', score: null },
      },
    },
    coverage: { explored: 2, total: 3, unexplored: ['AWS Certification'] },
  },
  findings: { strengths: [{ text: `${name} strength` }], weaknesses: [{ text: 'A weakness' }], gaps: [], verify: [] },
  claims: [{ result: 'contradiction' }, { result: 'never_discussed' }],
  quality: { verdict: 'needs_attention', reasons: [] },
  identity: { state: 'confirmed', text: 'Confirmed by face recognition at 00:04.' },
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

  it('lists the CV score, then the interview score and its dimensions', () => {
    const rows = componentRows(content('Good', 82).components);
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ['CV screening (overall)', 82],
      ['Interview score (overall)', 72],
      ['Interview: Technical competency', 70],
      ['Interview: Experience depth', null],
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
    expect(row('Interview score (overall)')).toEqual([72, 72]);
    expect(row('CV claims to follow up')).toEqual(['1 contradiction, 1 never discussed', '1 contradiction, 1 never discussed']);
    expect(row('Interview quality')).toEqual(['Needs attention', 'Needs attention']);
    expect(row('Identity')[0]).toBe('Confirmed by face recognition at 00:04.');
  });

  it('summarises the CV claims to follow up', () => {
    expect(claimsSummary([{ result: 'unverified' }, { result: 'unverified' }])).toBe('2 unverified');
    expect(claimsSummary([])).toBe('None');
  });

  it('warns before the selection email when the identity was not confirmed', () => {
    expect(identityWarning({ state: 'confirmed', text: 'Matched' })).toBeNull();
    expect(identityWarning({ state: 'matched', text: 'Matches the application photo' })).toBeNull();
    expect(identityWarning({ state: 'off', text: 'Not set up' })).toBeNull();
    expect(identityWarning(null)).toBeNull();
    expect(identityWarning({ state: 'no_match', text: 'Different person: does not match the application photo' })).toBe(
      'The face check did not confirm this candidate: different person: does not match the application photo.',
    );
    expect(identityWarning({ state: 'no_photo', text: 'No comparison: no photo was sent with the application.' })).toBe(
      'The face check was not done: no photo was sent with the application. Make sure you are emailing the right person.',
    );
    expect(identityWarning({ state: 'not_checked', text: 'Not checked: the candidate has not checked in yet.' })).toBe(
      'The face check was not done: the candidate has not checked in yet. Make sure you are emailing the right person.',
    );
  });

  it('builds the radar of the interview dimensions per candidate', () => {
    const content = (scores) => ({
      components: {
        interview: {
          dimensions: Object.fromEntries(
            Object.entries(scores).map(([key, score]) => [key, { label: key.toUpperCase(), score }]),
          ),
        },
      },
    });
    const a = { name: 'Rina', content: content({ tech: 80, comm: 70, depth: 60, align: null }) };
    const b = { name: 'Sami', content: content({ tech: 50, comm: 90, depth: 40, align: null }) };

    expect(radarData([a, b])).toEqual([
      { dimension: 'TECH', Rina: 80, Sami: 50 },
      { dimension: 'COMM', Rina: 70, Sami: 90 },
      { dimension: 'DEPTH', Rina: 60, Sami: 40 },
    ]); // ALIGN has no score for anyone
    expect(radarData([{ name: 'X', content: content({ tech: 80, comm: 70 }) }])).toEqual([]); // too few
    expect(radarData([{ name: 'Y', content: { components: { interview: null } } }])).toEqual([]);
    const named = { name: 'Z', content: content({ a: 1, b: 2, c: 3 }) };
    named.content.components.interview.dimensions.a.label = 'Experience depth';
    expect(radarData([named])[0].dimension).toBe('Depth'); // short corner names
  });
});
