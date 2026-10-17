// The three interview-level tabs of the Interview Analysis page (design:
// ClaimsCheckList, InterviewScoreCard, InterviewQualityPanel):
// - CV claims check (F8): what the CV says next to what the interview
//   showed, as prompts for the interviewer's own follow-up;
// - Interview score (F9): six dimensions with their evidence, separate from
//   the CV score;
// - Interview quality (F10): how good the interview was as evidence, with
//   suggestions; a poor interview offers a new one via the Hiring Assistant.
// All come from the same analysis run (one AI request for the review).

import { Button } from '@mantine/core';
import { IconCalendarRepeat, IconInfoCircle, IconMessageQuestion } from '@tabler/icons-react';
import { useNavigate } from 'react-router';

import StatusBadge from '../../components/StatusBadge';
import classes from './Analysis.module.css';
import { clock } from './analysisFormat';
import { CLAIM_RESULTS, claimCounts, rescheduleRequest, scoreTone, VERDICTS } from './insightsFormat';
import own from './Insights.module.css';

// Chips that open the transcript at a turn ("02:47").
function TurnChips({ turnIds, turns, onShowTurn }) {
  return turnIds
    .filter((id) => turns.has(id))
    .map((id) => (
      <button key={id} type="button" className={classes.sourceChip} onClick={() => onShowTurn(id)}>
        Transcript {clock(turns.get(id).start_ms)}
      </button>
    ));
}

// ---------- F8 ----------

export function ClaimsCheck({ claims, turns, onShowTurn }) {
  return (
    <>
      <div className={classes.notice} role="note">
        <IconInfoCircle size={18} />
        <span>
          These are <b>prompts for your own follow-up</b>, not accusations. Nothing here changes a score or a
          decision.
        </span>
      </div>
      <section className={classes.card}>
        <div className={classes.cardHead}>
          <h2 className={classes.cardTitle}>CV claims check</h2>
          <span className={own.counts}>
            {claimCounts(claims).map(([result, count]) => {
              const style = CLAIM_RESULTS[result];
              return (
                <StatusBadge key={result} tone={style.tone} icon={<style.icon size={13} />}>
                  {count} {style.text.toLowerCase()}
                </StatusBadge>
              );
            })}
          </span>
        </div>
        {claims.length === 0 && <div className={classes.muted}>No CV claims to compare were found.</div>}
        <div className={own.claims}>
          {claims.map((claim) => {
            const style = CLAIM_RESULTS[claim.result];
            return (
              <article key={`${claim.claim}-${claim.cv.text}`} className={`${own.claim} ${own[claim.result]}`}>
                <StatusBadge tone={style.tone} icon={<style.icon size={13} />}>
                  {style.text}
                </StatusBadge>
                <div className={own.claimGrid}>
                  <div>
                    <span className={own.label}>CV says</span>
                    <p className={own.claimText}>{claim.claim}</p>
                    <span className={own.quote}>
                      {claim.cv.label}: “{claim.cv.text}”
                    </span>
                  </div>
                  <div>
                    <span className={own.label}>Interview says</span>
                    <p className={own.claimText}>{claim.interview_says || 'Not discussed in the interview.'}</p>
                    <div className={classes.chips}>
                      <TurnChips turnIds={claim.turn_ids} turns={turns} onShowTurn={onShowTurn} />
                    </div>
                  </div>
                </div>
                <div className={own.followUp}>
                  <IconMessageQuestion size={16} />
                  <span>
                    <b>Suggested follow-up:</b> {claim.follow_up}
                  </span>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </>
  );
}

// ---------- F9 ----------

export function InterviewScore({ score, cvScore, turns, onShowTurn, onShowPair }) {
  if (!score) {
    return <div className={classes.muted}>No job-related answers were scored, so there is no interview score.</div>;
  }
  return (
    <section className={classes.card}>
      <div className={own.scoreHead}>
        <div className={`${own.bigScore} ${own[scoreTone(score.overall)]}`}>
          {score.overall}
          <span>/ 100</span>
        </div>
        <div>
          <h2 className={classes.cardTitle}>Interview score</h2>
          <div className={classes.muted}>
            How the candidate did in the interview, over {score.scored} scored answers. Separate from the CV
            screening score{cvScore != null ? ` (${Math.round(cvScore)})` : ''}.
          </div>
        </div>
      </div>
      <div className={own.dimensions}>
        {Object.entries(score.dimensions).map(([key, dim]) => (
          <div key={key} className={own.dimension}>
            <div className={own.dimTop}>
              <b>{dim.label}</b>
              <span className={own.dimScore}>{dim.score ?? '–'}</span>
            </div>
            <div className={classes.miniTrack}>
              <div
                className={`${own.fill} ${own[scoreTone(dim.score)]}`}
                style={{ width: `${dim.score ?? 0}%` }}
              />
            </div>
            <div className={own.reason}>{dim.reason}</div>
            <div className={classes.chips}>
              {(dim.pair_ids ?? []).map((id) => (
                <button key={id} type="button" className={classes.sourceChip} onClick={() => onShowPair(id)}>
                  {id}
                </button>
              ))}
              <TurnChips turnIds={dim.turn_ids ?? []} turns={turns} onShowTurn={onShowTurn} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- F10 ----------

export function InterviewQuality({ quality, interview, onShowPair }) {
  const navigate = useNavigate();
  const verdict = VERDICTS[quality.verdict];
  const talk = quality.talk;
  const consistency = quality.consistency;

  // Open the job's chat with the request for a new interview, to check and send.
  function reschedule() {
    navigate(`/assistant/${interview.job_id}`, { state: { draft: rescheduleRequest(interview, quality) } });
  }

  return (
    <>
      <section className={`${classes.card} ${own.verdict} ${own[verdict.tone]}`}>
        <div className={own.verdictHead}>
          <span className={own.label}>Interview quality</span>
          <StatusBadge tone={verdict.tone}>{verdict.text}</StatusBadge>
        </div>
        {quality.reasons.length > 0 ? (
          <ul className={own.reasons}>
            {quality.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p className={own.claimText}>The interview gave balanced, job-related evidence.</p>
        )}
        {quality.verdict === 'poor' && (
          <div className={own.reschedule}>
            <span>This interview may not be enough evidence for a decision.</span>
            <Button size="xs" leftSection={<IconCalendarRepeat size={15} />} onClick={reschedule}>
              Reschedule with Hiring Assistant
            </Button>
          </div>
        )}
      </section>

      <div className={own.qualityGrid}>
        <section className={classes.card}>
          <h2 className={classes.cardTitle}>Who did the talking</h2>
          {talk ? (
            <>
              <div className={own.talkBar} aria-label={`Interviewer ${talk.interviewer}%, candidate ${talk.candidate}%`}>
                <div className={own.talkInterviewer} style={{ width: `${talk.interviewer}%` }} />
                <div className={own.talkCandidate} style={{ width: `${talk.candidate}%` }} />
              </div>
              <div className={own.talkLegend}>
                <span>
                  <i className={own.talkInterviewer} /> Interviewer {talk.interviewer}%
                </span>
                <span>
                  <i className={own.talkCandidate} /> Candidate {talk.candidate}%
                </span>
              </div>
            </>
          ) : (
            <div className={classes.muted}>No speech was transcribed.</div>
          )}
          <div className={own.stats}>
            <span>
              <b>{quality.answered}</b> job questions answered
            </span>
            <span>
              <b>
                {quality.mandatory.explored} of {quality.mandatory.total}
              </b>{' '}
              mandatory requirements explored
            </span>
          </div>
        </section>

        <section className={classes.card}>
          <h2 className={classes.cardTitle}>Consistency across candidates</h2>
          {consistency ? (
            <>
              <div className={classes.muted}>Compared with {consistency.compared_with} other interviews for this job.</div>
              <div className={own.stats}>
                <span>
                  <b>{consistency.answered.this}</b> answered here, typically <b>{consistency.answered.typical}</b>
                </span>
                <span>
                  <b>{consistency.explored.this}</b> requirements explored, typically{' '}
                  <b>{consistency.explored.typical}</b>
                </span>
              </div>
              {consistency.missing_usual.length > 0 && (
                <p className={own.claimText}>
                  Usually explored, but not here: <b>{consistency.missing_usual.join(', ')}</b>.
                </p>
              )}
            </>
          ) : (
            <div className={classes.muted}>This is the first analysed interview for this job.</div>
          )}
        </section>
      </div>

      {quality.low_signal.length > 0 && (
        <section className={classes.card}>
          <h2 className={classes.cardTitle}>Questions that gave little evidence</h2>
          <ul className={own.lowSignal}>
            {quality.low_signal.map((note) => (
              <li key={note.pair_id}>
                <button type="button" className={`${classes.qid} ${own.qidButton}`} onClick={() => onShowPair(note.pair_id)}>
                  {note.pair_id}
                </button>
                <span>
                  “{note.question}” <span className={classes.muted}>{note.problem}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {quality.suggestions.length > 0 && (
        <section className={classes.card}>
          <h2 className={classes.cardTitle}>Suggestions for the next interview</h2>
          <ul className={own.reasons}>
            {quality.suggestions.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
