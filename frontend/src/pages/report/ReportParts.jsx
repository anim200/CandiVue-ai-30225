// The parts of the assessment report (design: Assessment Report.dc.html,
// frame 1a): the overall position on its 4-step scale with the identity
// line (F7), the component scores (CV and interview score, F9), the four
// lists of conclusions with their source chips, the CV claims to follow up
// and the interview quality (F8, F10), and the source panel that shows the
// CV excerpt or transcript lines behind a chip.

import {
  IconAlertTriangle,
  IconArrowsDiff,
  IconClipboardList,
  IconFileCv,
  IconHelpCircle,
  IconListCheck,
  IconMessage2,
  IconPointer,
  IconThumbDown,
  IconThumbUp,
  IconUserCheck,
} from '@tabler/icons-react';
import { RadarChart } from '@mantine/charts';
import { Link } from 'react-router';

import StatusBadge from '../../components/StatusBadge';
import { CLAIM_RESULTS, VERDICTS } from '../analysis/insightsFormat';

import { clock } from '../analysis/analysisFormat';
import classes from './Report.module.css';
import { componentRows, coverageLine, POSITIONS, radarData } from './reportFormat';

const SECTIONS = [
  { key: 'strengths', title: 'Strengths', icon: IconThumbUp, color: 'var(--cv-success-text)' },
  { key: 'weaknesses', title: 'Weaknesses', icon: IconThumbDown, color: 'var(--cv-danger-text)' },
  { key: 'gaps', title: 'Evidence gaps', icon: IconHelpCircle, color: 'var(--cv-warning-text-mid)' },
  { key: 'verify', title: 'Areas to verify', icon: IconListCheck, color: 'var(--cv-info-text)' },
];
const NEIGHBOURS = 1; // turns shown before and after a cited transcript line
const SOURCE_KINDS = {
  cv: { icon: IconFileCv, note: 'Excerpt from the candidate’s CV.' },
  requirement: { icon: IconClipboardList, note: 'What CV screening found and which questions explored it.' },
  transcript: { icon: IconMessage2, note: 'Times are minutes:seconds from the start of the interview.' },
};

// The icon of a source: CV, requirement record or transcript.
function SourceIcon({ kind, size }) {
  const Icon = SOURCE_KINDS[kind].icon;
  return <Icon size={size} />;
}

// The overall position, highlighted on the 4-step scale.
export function SuitabilityCard({ position, identity }) {
  return (
    <section className={classes.card}>
      <div className={classes.label}>Overall suitability position</div>
      <div className={classes.headline}>{position.headline}</div>
      {position.score !== null && (
        <>
          <div className={classes.steps}>
            {POSITIONS.map(([key]) => (
              <div key={key} className={`${classes.step} ${key === position.key ? classes.stepOn : ''}`} />
            ))}
          </div>
          <div className={classes.stepLabels}>
            {POSITIONS.map(([key, label]) => (
              <span key={key} className={key === position.key ? classes.stepLabelOn : ''}>
                {label}
              </span>
            ))}
          </div>
        </>
      )}
      <div className={classes.note}>
        Based on the component scores{position.score !== null ? ` (combined ${position.score})` : ''}. It is a
        summary for your review, not a decision.
      </div>
      {identity && (
        <div className={`${classes.identityLine} ${identity.state === 'confirmed' ? classes.identityConfirmed : ''}`}>
          <IconUserCheck size={15} /> Identity: {identity.text}
        </div>
      )}
    </section>
  );
}

// One corner name of the radar, centred on its corner (above it on the
// upper half, below it on the lower half) so long names stay inside a
// narrow card.
function RadarCorner({ x, y, payload }) {
  const up = Math.sin((payload.coordinate * Math.PI) / 180);
  const dy = up > 0.1 ? -3 : up < -0.1 ? 14 : 4;
  return (
    <text x={x} y={y} dy={dy} textAnchor="middle" fontSize={12} fill="var(--chart-text-color, var(--mantine-color-dimmed))">
      {payload.value}
    </text>
  );
}

// The interview dimensions (F9) as a radar: one series per candidate
// ({ name, content }); nothing when fewer than three have a score.
export function InterviewRadar({ candidates, height = 260 }) {
  const data = radarData(candidates);
  if (data.length === 0) return null;
  const colours = ['harbor.6', 'orange.6', 'grape.6'];
  return (
    <RadarChart
      h={height}
      data={data}
      dataKey="dimension"
      polarRadiusAxisProps={{ domain: [0, 100] }}
      polarAngleAxisProps={{ tick: RadarCorner }}
      radarChartProps={{ outerRadius: '72%' }}
      withLegend={candidates.length > 1}
      withTooltip
      series={candidates.map(({ name }, index) => ({ name, color: colours[index], opacity: 0.22 }))}
      aria-label="Interview score per dimension"
    />
  );
}

// CV screening and the interview score with its six dimensions, 0-100,
// with coverage (a dimension without evidence shows a dash), and the
// dimensions as a radar.
export function ComponentScoresCard({ components, analysisLink }) {
  const rows = componentRows(components);
  return (
    <section className={classes.card}>
      <div className={classes.label}>Component scores (0–100)</div>
      {rows.map((row) => (
        <div key={row.label} className={classes.scoreRow}>
          <span className={row.part === 'cv' ? classes.cvLabel : undefined}>{row.label}</span>
          <div className={classes.scoreTrack}>
            <div
              className={`${classes.scoreFill} ${row.part === 'cv' ? classes.cvFill : ''}`}
              style={{ width: `${row.value ?? 0}%` }}
            />
          </div>
          <b>{row.value ?? '–'}</b>
        </div>
      ))}
      {rows.length === 0 && <div className={classes.note}>No scores: the CV was not screened and no answer was scored.</div>}
      <InterviewRadar candidates={[{ name: 'Interview score', content: { components } }]} />
      <div className={classes.coverage}>
        {coverageLine(components.coverage)} · <Link to={analysisLink}>Q&amp;A analysis</Link>
      </div>
    </section>
  );
}

// The four lists of conclusions; every conclusion shows its source chips.
export function FindingsList({ findings, sources, selected, onSelect }) {
  return (
    <section className={classes.findings}>
      {SECTIONS.map(({ key, title, icon: Icon, color }) => (
        <div key={key} className={classes.section}>
          <h2 className={classes.sectionTitle}>
            <Icon size={18} color={color} />
            {title}
          </h2>
          {findings[key].length === 0 && <div className={classes.none}>None noted.</div>}
          {findings[key].map((finding) => (
            <div key={finding.text} className={classes.finding}>
              <div className={classes.findingText}>{finding.text}</div>
              <div className={classes.chips}>
                {finding.sources.map((id) => (
                  <button
                    key={id}
                    type="button"
                    className={`${classes.chip} ${selected === id ? classes.chipOn : ''}`}
                    onClick={() => onSelect(id)}
                    aria-pressed={selected === id}
                  >
                    <SourceIcon kind={sources[id].kind} size={13} />
                    {sources[id].label}
                  </button>
                ))}
                {finding.unsupported && (
                  <span className={classes.unsupported}>
                    <IconAlertTriangle size={13} /> No supporting source found: verify before relying on it.
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      ))}
    </section>
  );
}

// CV claims a person should follow up (F8) and the interview quality (F10).
export function FollowUpCard({ claims, quality, sources, selected, onSelect, analysisLink }) {
  if (!claims && !quality) return null; // a report from before these checks
  const verdict = quality && VERDICTS[quality.verdict];
  return (
    <section className={classes.findings}>
      <div className={classes.section}>
        <h2 className={classes.sectionTitle}>
          <IconArrowsDiff size={18} color="var(--cv-danger-text)" />
          CV claims to follow up
        </h2>
        {claims.length === 0 && <div className={classes.none}>None: the interview supported the CV claims checked.</div>}
        {claims.map((claim) => {
          const style = CLAIM_RESULTS[claim.result];
          return (
            <div key={`${claim.claim}-${claim.cv.text}`} className={classes.finding}>
              <div className={classes.findingText}>
                <StatusBadge tone={style.tone} icon={<style.icon size={12} />}>
                  {style.text}
                </StatusBadge>{' '}
                {claim.claim} <span className={classes.cvLabel}>({claim.cv.label})</span>
                {claim.interview_says && <div className={classes.note}>Interview: {claim.interview_says}</div>}
                <div className={classes.note}>Follow up: {claim.follow_up}</div>
              </div>
              <div className={classes.chips}>
                {claim.sources.map((id) => (
                  <button
                    key={id}
                    type="button"
                    className={`${classes.chip} ${selected === id ? classes.chipOn : ''}`}
                    onClick={() => onSelect(id)}
                    aria-pressed={selected === id}
                  >
                    <SourceIcon kind={sources[id].kind} size={13} />
                    {sources[id].label}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {quality && (
        <div className={classes.section}>
          <h2 className={classes.sectionTitle}>
            Interview quality <StatusBadge tone={verdict.tone}>{verdict.text}</StatusBadge>
          </h2>
          <div className={classes.findingText}>
            {quality.reasons.join(' ') || 'The interview gave balanced, job-related evidence.'}{' '}
            <Link to={`${analysisLink}?tab=quality`}>Details and suggestions</Link>
          </div>
        </div>
      )}
    </section>
  );
}

// The evidence behind the selected chip: a CV excerpt, a requirement's
// coverage record, or the transcript line with the turns around it (the
// transcript loads on first use).
export function SourcePanel({ source, turns, transcriptFailed, onRetry, onOpenTranscript }) {
  let body;
  if (!source) {
    body = (
      <div className={classes.panelEmpty}>
        <IconPointer size={22} />
        Click a source chip to see the CV excerpt or transcript segment behind a conclusion.
      </div>
    );
  } else if (source.kind !== 'transcript') {
    body = (
      <>
        <div className={classes.panelLabel}>
          <SourceIcon kind={source.kind} size={14} /> {source.label}
        </div>
        <div className={`${classes.line} ${classes.lineCited}`}>{source.text}</div>
        <div className={classes.panelNote}>{SOURCE_KINDS[source.kind].note}</div>
      </>
    );
  } else if (transcriptFailed) {
    body = (
      <div className={classes.panelEmpty}>
        This excerpt couldn’t be loaded. The conclusion is unchanged.
        <button type="button" className={classes.link} onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  } else {
    const at = turns ? turns.findIndex((turn) => turn.id === source.turn_id) : -1;
    const shown = at >= 0 ? turns.slice(Math.max(at - NEIGHBOURS, 0), at + NEIGHBOURS + 1) : [];
    body = (
      <>
        <div className={classes.panelLabel}>
          <IconMessage2 size={14} /> {source.label}
        </div>
        {(shown.length ? shown : [{ id: source.turn_id, ...source }]).map((turn) => (
          <div key={turn.id} className={`${classes.line} ${turn.id === source.turn_id ? classes.lineCited : ''}`}>
            <div className={classes.lineWho}>
              <span>{clock(turn.start_ms)}</span>
              {turn.speaker === 'interviewer' ? 'Interviewer' : 'Candidate'}
            </div>
            {turn.text}
          </div>
        ))}
        <div className={classes.panelNote}>
          {SOURCE_KINDS.transcript.note}{' '}
          <button type="button" className={classes.link} onClick={() => onOpenTranscript(source.turn_id)}>
            Open in the transcript
          </button>
        </div>
      </>
    );
  }
  return (
    <aside className={classes.panel}>
      <div className={classes.panelHead}>Source</div>
      <div className={classes.panelBody}>{body}</div>
    </aside>
  );
}
