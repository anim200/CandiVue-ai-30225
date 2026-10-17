// The parts of the assessment report (design: Assessment Report.dc.html,
// frame 1a): the overall position on its 4-step scale, the component
// scores, the four lists of conclusions with their source chips, and the
// source panel that shows the CV excerpt or transcript lines behind a chip.

import {
  IconAlertTriangle,
  IconClipboardList,
  IconFileCv,
  IconHelpCircle,
  IconListCheck,
  IconMessage2,
  IconPointer,
  IconThumbDown,
  IconThumbUp,
} from '@tabler/icons-react';
import { Link } from 'react-router';

import { clock } from '../analysis/analysisFormat';
import classes from './Report.module.css';
import { componentRows, coverageLine, POSITIONS } from './reportFormat';

const SECTIONS = [
  { key: 'strengths', title: 'Strengths', icon: IconThumbUp, color: '#2D7A4E' },
  { key: 'weaknesses', title: 'Weaknesses', icon: IconThumbDown, color: '#B03A2E' },
  { key: 'gaps', title: 'Evidence gaps', icon: IconHelpCircle, color: '#C08A1E' },
  { key: 'verify', title: 'Areas to verify', icon: IconListCheck, color: '#2B5FA8' },
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
export function SuitabilityCard({ position }) {
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
    </section>
  );
}

// CV screening and the four interview dimensions, 0-100, with coverage.
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
              style={{ width: `${row.value}%` }}
            />
          </div>
          <b>{row.value}</b>
        </div>
      ))}
      {rows.length === 0 && <div className={classes.note}>No scores: the CV was not screened and no answer was scored.</div>}
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
