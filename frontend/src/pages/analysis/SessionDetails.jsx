// Session details (design: Interview Analysis.dc.html, frame 1c): the
// session record (F3) and a timeline from scheduling to the report, with
// the note that no audio or video was recorded (N16).

import { IconShieldCheck } from '@tabler/icons-react';

import classes from './Analysis.module.css';

// "14 Oct 2026, 10:00".
function dateText(iso) {
  return new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}

// "10:01:12".
function timeText(iso) {
  return new Date(iso).toLocaleTimeString('en-GB');
}

// The timeline entries that happened, in order.
function timeline(interview, analysisRun, report) {
  const events = [];
  if (interview.started_at) events.push([interview.started_at, 'The call started', 'harbor']);
  if (interview.ended_at) {
    events.push([interview.ended_at, `${interview.interviewer_name ?? 'The interviewer'} ended the interview`, 'harbor']);
  }
  if (analysisRun?.status === 'completed') events.push([analysisRun.finished_at, 'Q&A analysis completed', 'success']);
  if (analysisRun?.status === 'failed') events.push([analysisRun.finished_at, 'Q&A analysis stopped', 'danger']);
  if (report?.content?.generated_at) {
    events.push([report.content.generated_at, `Assessment report version ${report.content.version} ready for review`, 'warning']);
  }
  if (report?.approved_at) events.push([report.approved_at, `Report approved by ${report.reviewed_by ?? 'an interviewer'}`, 'success']);
  return events.filter(([at]) => at).sort((a, b) => new Date(a[0]) - new Date(b[0]));
}

export default function SessionDetails({ interview, analysisRun, report }) {
  const minutes =
    interview.started_at && interview.ended_at
      ? Math.max(1, Math.round((new Date(interview.ended_at) - new Date(interview.started_at)) / 60000))
      : null;
  const facts = [
    ['Candidate', <b key="name">{interview.candidate_name}</b>],
    ['Job', interview.job_title],
    ['Interviewer', interview.interviewer_name ?? '—'],
    ['Scheduled', dateText(interview.scheduled_at)],
    ['Started', interview.started_at ? timeText(interview.started_at) : '—'],
    ['Ended', interview.ended_at ? `${timeText(interview.ended_at)}${minutes ? ` · ${minutes} min` : ''}` : '—'],
    ['Interview link', interview.status === 'ended' ? 'Disabled when the interview ended' : 'Active'],
  ];
  return (
    <>
      <div className={classes.sessionGrid}>
        <section className={`${classes.card} ${classes.facts}`}>
          <h2 className={classes.cardTitle}>Session</h2>
          {facts.map(([label, value]) => (
            <div key={label} className={classes.fact}>
              <span className={classes.factLabel}>{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </section>
        <section className={classes.card}>
          <h2 className={classes.cardTitle}>Timeline</h2>
          <div className={classes.timeline}>
            {timeline(interview, analysisRun, report).map(([at, text, tone]) => (
              <div key={`${at}-${text}`} className={classes.event}>
                <span className={classes.mono}>{timeText(at)}</span>
                <span className={`${classes.dot} ${classes[tone]}`} />
                <span>{text}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
      <div className={classes.privacy}>
        <IconShieldCheck size={18} />
        No audio or video was recorded: the audio was only streamed to speech-to-text during the call. The
        transcript and the analysis are kept.
      </div>
    </>
  );
}
