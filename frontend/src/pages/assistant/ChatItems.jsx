// The pieces of the chat: user and assistant messages, tool step lines,
// review notes and the job profile card (design: ChatThread, frames 1a, 2c).

import { IconCheck, IconSparkles } from '@tabler/icons-react';

import classes from './Assistant.module.css';
import { LEVELS } from './labels';

// The interviewer's message, on the right.
export function UserBubble({ text }) {
  return <div className={classes.userBubble}>{text}</div>;
}

// A row with the assistant's round avatar on the left and content on the right.
export function AssistantRow({ children }) {
  return (
    <div className={classes.assistantRow}>
      <span className={classes.avatar} aria-hidden="true">
        <IconSparkles size={15} />
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

// "Working…" line with a spinner while the assistant is busy (frame 2c).
export function WorkingLine() {
  return (
    <AssistantRow>
      <div className={classes.stepLines}>
        <div className={`${classes.stepLineItem} ${classes.working}`}>
          <span className={classes.spinner} />
          Working on it…
        </div>
      </div>
    </AssistantRow>
  );
}

// Small centred note after a review, e.g. "You approved version 1".
export function ReviewNote({ text }) {
  return <div className={classes.reviewNote}>{text}</div>;
}

// The job profile: requirements grouped as Mandatory / Required / Preferred.
export function ProfileCard({ profile }) {
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
    </div>
  );
}
