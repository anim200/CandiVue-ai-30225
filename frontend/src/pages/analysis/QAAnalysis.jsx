// The Q&A analysis tab (design: Interview Analysis.dc.html, frame 1a):
// requirement coverage, then one card per question–answer unit with its
// four scores; a card opens to show the turns, why these scores, and the
// reference documents the accuracy was checked against.

import { Collapse, UnstyledButton } from '@mantine/core';
import {
  IconAlertCircle,
  IconChevronDown,
  IconChevronUp,
  IconCircleCheck,
  IconFileText,
  IconMessage2,
} from '@tabler/icons-react';

import classes from './Analysis.module.css';
import { clock, coverageSummary, DIMENSIONS, pairTags } from './analysisFormat';

// Each job requirement with the Q ids that explored it; never-explored ones
// stand out (warning tint).
function RequirementCoverageCard({ results }) {
  return (
    <section className={classes.card}>
      <div className={classes.cardHead}>
        <h2 className={classes.cardTitle}>Requirement coverage</h2>
        <span className={classes.cardNote}>{coverageSummary(results)}</span>
      </div>
      <div className={classes.coverage}>
        {results.coverage.map((item) => {
          const never = item.pair_ids.length === 0;
          return (
            <div key={item.requirement} className={`${classes.requirement} ${never ? classes.never : ''}`}>
              <div className={classes.requirementName}>
                {never ? (
                  <IconAlertCircle size={15} className={classes.warnIcon} />
                ) : (
                  <IconCircleCheck size={15} className={classes.okIcon} />
                )}
                {item.requirement}
              </div>
              <div className={classes.chips}>
                {item.pair_ids.map((id) => (
                  <span key={id} className={classes.qid}>
                    {id}
                  </span>
                ))}
                {never && <span className={classes.neverText}>Never explored</span>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// The four scores as small bars (they grow from the left when shown).
function ScoreBars({ scores }) {
  return (
    <div className={classes.bars}>
      {DIMENSIONS.map(([key, label]) => (
        <div key={key} className={classes.barItem}>
          <div className={classes.barLabel}>
            <span>{label}</span>
            <b>{scores[key].score}</b>
          </div>
          <div className={classes.miniTrack}>
            <div className={classes.miniFill} style={{ width: `${scores[key].score}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

// One question–answer unit; click to open the turns and the reasons.
function QAPairCard({ pair, turns, open, onToggle, onShowTurn }) {
  const scored = pair.status === 'scored';
  const shown = pair.turn_ids.map((id) => turns.get(id)).filter(Boolean);
  const cited = turns.get(pair.evidence_turn_ids?.[0] ?? pair.answer_turn_ids[0]);
  return (
    <div className={`${classes.pair} ${scored ? '' : classes.pairMuted}`}>
      <UnstyledButton className={classes.pairHead} onClick={onToggle} aria-expanded={open}>
        <span className={classes.pairId}>{pair.id}</span>
        <div className={classes.pairText}>
          <div className={classes.question}>{pair.question}</div>
          <div className={classes.pairMeta}>
            <span className={classes.mono}>
              {clock(pair.start_ms)} → {clock(pair.end_ms)}
            </span>
            <span>·</span>
            <span>{scored ? pair.requirements.join(', ') || 'No job requirement' : pair.reason}</span>
            {pairTags(pair).map((tag) => (
              <span key={tag} className={classes.tag}>
                {tag}
              </span>
            ))}
          </div>
        </div>
        {scored ? <ScoreBars scores={pair.scores} /> : <span className={classes.notScored}>Not scored</span>}
        {open ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
      </UnstyledButton>
      <Collapse expanded={open}>
        <div className={classes.pairBody}>
          <div className={classes.turns}>
            {shown.map((turn) => (
              <div key={turn.id} className={classes.turn}>
                <span className={classes.mono}>{clock(turn.start_ms)}</span>
                <span className={turn.speaker === 'interviewer' ? classes.interviewer : classes.candidate}>
                  {turn.speaker === 'interviewer' ? 'Interviewer' : 'Candidate'}
                </span>
                <span>{turn.text}</span>
              </div>
            ))}
            {shown.length === 0 && <div className={classes.muted}>The transcript is loading…</div>}
          </div>
          {scored && (
            <div className={classes.why}>
              <div className={classes.whyTitle}>Why these scores</div>
              <div className={classes.whyText}>{pair.summary}</div>
              <ul className={classes.reasons}>
                {DIMENSIONS.map(([key, label]) => (
                  <li key={key}>
                    <b>
                      {label} {pair.scores[key].score}:
                    </b>{' '}
                    {pair.scores[key].reason}
                  </li>
                ))}
              </ul>
              <div className={classes.checked}>
                {pair.verified ? (
                  <>
                    <IconFileText size={14} /> Accuracy checked against{' '}
                    {[...new Set(pair.sources.map((s) => s.filename))].join(', ')}
                  </>
                ) : (
                  'Not checked against a reference document: the AI judged accuracy on its own.'
                )}
              </div>
              {cited && (
                <button type="button" className={classes.sourceChip} onClick={() => onShowTurn(cited.id)}>
                  <IconMessage2 size={13} /> Transcript {clock(cited.start_ms)}
                </button>
              )}
            </div>
          )}
        </div>
      </Collapse>
    </div>
  );
}

// The whole tab: coverage, then every unit in the order it was asked.
export default function QAAnalysis({ results, turns, openIds, onToggle, onShowTurn }) {
  return (
    <>
      <RequirementCoverageCard results={results} />
      <div className={classes.pairs}>
        {results.pairs.map((pair) => (
          <QAPairCard
            key={pair.id}
            pair={pair}
            turns={turns}
            open={openIds.has(pair.id)}
            onToggle={() => onToggle(pair.id)}
            onShowTurn={onShowTurn}
          />
        ))}
      </div>
    </>
  );
}
