// The pieces of the chat: user and assistant messages, tool step lines,
// review notes and the job profile card (design: ChatThread, frames 1a, 2c).

import { IconCheck } from '@tabler/icons-react';

import AiSignalStatus from '../../components/AiSignalStatus';
import AssistantMark from '../../components/AssistantMark';
import classes from './Assistant.module.css';
import { DIMENSION_NAMES, LEVELS } from './labels';

// The interviewer's message, on the right.
export function UserBubble({ text }) {
  return <div className={classes.userBubble}>{text}</div>;
}

// A row with the assistant's mark on the left and content on the right
// (the same mark moves in WorkingLine while the assistant works).
export function AssistantRow({ children }) {
  return (
    <div className={classes.assistantRow}>
      <span className={classes.avatar} aria-hidden="true">
        <AssistantMark size={28} />
      </span>
      <div className={classes.assistantBody}>{children}</div>
    </div>
  );
}

// Plain assistant text.
export function AssistantText({ text }) {
  return <div className={classes.assistantText}>{text}</div>;
}

// Green "done" lines for the tools the assistant used, e.g. "Saved the job profile".
export function StepLines({ steps }) {
  return (
    <div className={classes.stepLines}>
      {steps.map((text, index) => (
        <div key={index} className={classes.stepLineItem}>
          <IconCheck size={15} />
          {text}
        </div>
      ))}
    </div>
  );
}

// The assistant's answer while it works: the Signal status, its moving
// mark in the avatar's place (steps, then the last one until the reply
// replaces it). Default: "Thinking…".
export function WorkingLine({ steps, startedAt }) {
  return (
    <div className={`${classes.assistantRow} ${classes.working}`}>
      <AiSignalStatus steps={steps} startedAt={startedAt} markSize={28} />
    </div>
  );
}

// Small centred note after a review, e.g. "You approved version 1".
export function ReviewNote({ text }) {
  return <div className={classes.reviewNote}>{text}</div>;
}

// The saved job profile: experience, requirements by level, and the
// scoring weights (suggested by the assistant or given by the interviewer).
export function ProfileCard({ profile, weights }) {
  return (
    <div className={classes.profileCard}>
      {profile.min_years_experience != null && (
        <>
          <span className={classes.profileLabel}>Minimum experience</span>
          <span>{profile.min_years_experience}+ years</span>
        </>
      )}
      {LEVELS.map(([level, label]) => {
        const items = profile.requirements.filter((r) => r.level === level);
        if (items.length === 0) return null;
        return (
          <div key={level} style={{ display: 'contents' }}>
            <span className={classes.profileLabel}>{label}</span>
            <span>{items.map((r) => r.text).join(' · ')}</span>
          </div>
        );
      })}
      {weights && (
        <>
          <span className={classes.profileLabel}>Scoring weights</span>
          <span>
            {DIMENSION_NAMES.map(([key, name]) => `${name} ${weights[key]}%`).join(' · ')}
            <span className={classes.weightsNote}>
              {weights.source === 'interviewer'
                ? ' (set by you)'
                : ' (suggested; you can change them on the job page)'}
            </span>
          </span>
        </>
      )}
    </div>
  );
}
