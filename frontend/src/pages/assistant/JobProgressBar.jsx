// Top of the chat: job name, the safety note and the five steps of a job
// (design: JobProgressBar).

import { IconArrowLeft, IconCircle, IconCircleCheckFilled, IconEye, IconShieldCheck } from '@tabler/icons-react';
import { Fragment } from 'react';
import { Link } from 'react-router';

import classes from './Assistant.module.css';

// Which steps are done, and which one needs the interviewer now.
function stepsFor(job) {
  const posted = job.stage === 'posted';
  const approved = posted || ['jd_approved', 'post_to_confirm', 'posting_failed'].includes(job.stage);
  return [
    { label: 'Profile', done: Boolean(job.profile) },
    { label: 'JD approved', done: approved, now: job.stage === 'jd_to_approve' },
    { label: 'Posted', done: posted, now: ['post_to_confirm', 'posting_failed'].includes(job.stage) },
    { label: 'CVs screened', done: job.screening_status === 'completed' },
    { label: 'Invitations', done: job.interview_count > 0 },
  ];
}

// The progress bar with a back link for phones.
export default function JobProgressBar({ job }) {
  const steps = stepsFor(job);
  return (
    <div className={classes.progress}>
      <div className={classes.progressTop}>
        <div className={classes.jobName}>
          <Link to="/assistant" className={classes.backLink} aria-label="Back to all jobs">
            <IconArrowLeft size={18} />
          </Link>
          {job.title}
        </div>
        <span className={classes.safeNote}>
          <IconShieldCheck size={14} color="var(--cv-primary-text)" />
          Nothing is posted or sent until you confirm
        </span>
      </div>
      <div className={classes.steps}>
        {steps.map((step, index) => {
          const Icon = step.done ? IconCircleCheckFilled : step.now ? IconEye : IconCircle;
          const tone = step.done ? classes.stepDone : step.now ? classes.stepNow : '';
          return (
            <Fragment key={step.label}>
              {index > 0 && (
                <div className={`${classes.stepLine} ${steps[index - 1].done ? classes.stepLineDone : ''}`} />
              )}
              <span className={`${classes.step} ${tone}`}>
                <Icon size={16} />
                {step.label}
              </span>
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
