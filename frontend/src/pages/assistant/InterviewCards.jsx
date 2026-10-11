// Chat cards after screening (design: InvitationConfirmCard): the saved
// shortlist, the interviews waiting for confirmation (Cancel / Change /
// Confirm), and what was done after confirming. Nothing is booked before
// the interviewer confirms; the backend checks everything again then.

import { Anchor, Button, Checkbox, TextInput } from '@mantine/core';
import {
  IconAlertTriangle,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconEye,
  IconMail,
  IconInfoCircle,
  IconListCheck,
  IconPencil,
  IconX,
} from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';

import StatusBadge from '../../components/StatusBadge';
import { toLocalInput, whenText } from '../../utils/dates';
import classes from './Assistant.module.css';
import { DIMENSION_NAMES } from './labels';

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

// Notes (e.g. a tie, a name not found) and warnings (e.g. new CVs) under a card.
function Notes({ notes = [], warnings = [] }) {
  if (!notes.length && !warnings.length) return null;
  return (
    <div className={classes.cardNotes}>
      {notes.map((note) => (
        <span key={note} className={classes.noteLine}>
          <IconInfoCircle size={15} /> {note}
        </span>
      ))}
      {warnings.map((warning) => (
        <span key={warning} className={`${classes.noteLine} ${classes.warningText}`}>
          <IconAlertTriangle size={15} /> {warning}
        </span>
      ))}
    </div>
  );
}

// The saved shortlist with each candidate's rank and scores.
export function ShortlistCard({ card }) {
  const count = card.candidates.length;
  return (
    <div className={classes.jdCard}>
      <div className={classes.jdHead}>
        <span className={classes.jdHeadTitle}>Shortlist · {plural(count, 'candidate')}</span>
        <StatusBadge tone="harbor" icon={<IconListCheck size={13} />}>
          Saved
        </StatusBadge>
      </div>
      {count === 0 ? (
        <div className={classes.jdBody}>The shortlist is empty.</div>
      ) : (
        <ul className={classes.people}>
          {card.candidates.map((c) => (
            <li key={c.candidate_id} className={classes.person}>
              <span className={classes.personRank}>{c.ranked ? `#${c.rank}` : '—'}</span>
              <span className={classes.personName}>{c.name}</span>
              {c.ranked ? (
                <span className={classes.personScore}>{Math.round(c.overall)}</span>
              ) : (
                <StatusBadge tone="warning">No longer ranked</StatusBadge>
              )}
              {c.ranked && (
                <span className={classes.personMeta}>
                  {DIMENSION_NAMES.map(([key, name]) => `${name} ${c.scores[key]}`).join(' · ')}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <Notes notes={card.notes} warnings={card.warnings} />
    </div>
  );
}

// The email the first candidate gets (collapsible; design: email preview).
function EmailPreview({ email, action }) {
  const [open, setOpen] = useState(false);
  const Chevron = open ? IconChevronDown : IconChevronRight;
  return (
    <div className={classes.cardNotes}>
      <button type="button" className={classes.previewToggle} onClick={() => setOpen(!open)} aria-expanded={open}>
        <Chevron size={15} />
        <IconMail size={15} />
        Email preview · {email.template}
      </button>
      {open && (
        <div className={classes.preview}>
          <b>Subject: {email.subject}</b>
          {'\n\n'}
          {email.text}
        </div>
      )}
      <span className={classes.hint}>
        {action === 'reschedule' ? 'Moved candidates get this email with the new time and a new link.' : 'Each candidate gets it with their own name, time and private link.'}
      </span>
    </div>
  );
}

// Words for each kind of plan: title, confirm button, keep-as-is button.
const PLAN_WORDS = {
  invite: { title: 'Interview invitations', confirm: 'Confirm', back: 'Cancel' },
  reschedule: { title: 'Move interviews', confirm: 'Move', back: 'Cancel' },
  cancel: { title: 'Cancel interviews', confirm: 'Cancel', back: 'Keep them' },
};

// The planned interviews, waiting for the interviewer. "Change" lets them
// leave people out and edit times before confirming.
export function InvitationConfirmCard({ plan, busy, onDecide }) {
  const words = PLAN_WORDS[plan.action];
  const timed = plan.action !== 'cancel';
  const [editing, setEditing] = useState(false);
  const [left, setLeft] = useState({}); // candidate_id -> true when left out
  const [times, setTimes] = useState(() =>
    Object.fromEntries(plan.items.map((i) => [i.candidate_id, i.starts_at && toLocalInput(i.starts_at)])),
  );
  const chosen = plan.items.filter((i) => !left[i.candidate_id]);

  // Send the decision: the items still on the card with their (new) times.
  function confirm() {
    const items = chosen.map((i) => ({
      candidate_id: i.candidate_id,
      starts_at: timed ? (editing ? times[i.candidate_id] : i.starts_at) : null,
    }));
    onDecide({ action: 'confirm', items });
  }

  return (
    <div className={`${classes.jdCard} ${classes.jdPending}`}>
      <div className={classes.jdHead}>
        <span className={classes.jdHeadTitle}>
          {words.title} · {plan.duration} min
        </span>
        <StatusBadge tone="warning" icon={<IconEye size={13} />}>
          Waiting for your confirmation
        </StatusBadge>
      </div>
      <ul className={classes.people}>
        {plan.items.map((item) => (
          <li key={item.candidate_id} className={`${classes.person} ${left[item.candidate_id] ? classes.skipped : ''}`}>
            {editing ? (
              <Checkbox
                checked={!left[item.candidate_id]}
                onChange={(e) => setLeft({ ...left, [item.candidate_id]: !e.currentTarget.checked })}
                aria-label={`Keep ${item.name}`}
              />
            ) : (
              <span className={classes.personRank}>{item.rank ? `#${item.rank}` : ''}</span>
            )}
            <span className={classes.personName}>{item.name}</span>
            {editing && timed ? (
              <TextInput
                type="datetime-local"
                size="xs"
                className={classes.timeInput}
                value={times[item.candidate_id] ?? ''}
                onChange={(e) => setTimes({ ...times, [item.candidate_id]: e.currentTarget.value })}
                aria-label={`Start time for ${item.name}`}
              />
            ) : (
              <span className={classes.personTime}>{whenText(item.starts_at ?? item.old_starts_at)}</span>
            )}
            {(plan.action === 'reschedule' || item.warnings.length > 0) && (
              <span className={`${classes.personMeta} ${classes.warningText}`}>
                {plan.action === 'reschedule' && `Was ${whenText(item.old_starts_at)}. `}
                {item.warnings.join(' ')}
              </span>
            )}
          </li>
        ))}
      </ul>
      <Notes warnings={plan.warnings} />
      {plan.email && <EmailPreview email={plan.email} action={plan.action} />}
      {plan.action === 'cancel' && (
        <div className={classes.cardNotes}>
          <span className={classes.hint}>Candidates are not emailed about a cancellation.</span>
        </div>
      )}
      <div className={classes.jdActions}>
        <span className={`${classes.hint} ${classes.actionsHint}`}>Nothing is booked until you confirm.</span>
        <Button variant="subtle" color="gray" onClick={() => onDecide({ action: 'cancel' })} disabled={busy}>
          {words.back}
        </Button>
        {!editing && (
          <Button variant="light" leftSection={<IconPencil size={15} />} onClick={() => setEditing(true)} disabled={busy}>
            Change
          </Button>
        )}
        <Button
          color={plan.action === 'cancel' ? '#B03A2E' : undefined}
          leftSection={<IconCheck size={15} />}
          onClick={confirm}
          loading={busy}
          disabled={chosen.length === 0}
        >
          {words.confirm} {plural(chosen.length, 'interview')}
        </Button>
      </div>
    </div>
  );
}

const DONE_TITLES = { invite: 'scheduled', reschedule: 'moved', cancel: 'cancelled' };

// What happened after confirming: done, or skipped with the reason.
export function InvitationResultsCard({ result }) {
  const done = result.results.filter((r) => r.done).length;
  const unsent = result.results.some((r) => r.email && r.email !== 'sent');
  return (
    <div className={classes.jdCard}>
      <div className={classes.jdHead}>
        <span className={classes.jdHeadTitle}>
          {plural(done, 'interview')} {DONE_TITLES[result.action]}
        </span>
      </div>
      <ul className={classes.people}>
        {result.results.map((r) => (
          <li key={r.name} className={classes.person}>
            {r.done ? <IconCheck size={16} color="#2D7A4E" /> : <IconX size={16} color="#B03A2E" />}
            <span className={classes.personName}>{r.name}</span>
            <span className={classes.personTime}>{r.starts_at && whenText(r.starts_at)}</span>
            {!r.done && <span className={`${classes.personMeta} ${classes.problemText}`}>{r.reason}</span>}
            {r.email && (
              <span className={`${classes.personMeta} ${r.email === 'sent' ? '' : classes.warningText}`}>
                {r.email === 'sent' ? 'Email sent' : `Email not sent: ${r.email}`}
              </span>
            )}
          </li>
        ))}
      </ul>
      {unsent && (
        <div className={classes.cardNotes}>
          <span className={classes.noteLine}>
            <IconInfoCircle size={15} />
            <span>
              Send the missing emails again, or copy the link, on the{' '}
              <Anchor component={Link} to="/interviews" fz={14} fw={600}>
                Interviews page
              </Anchor>
              .
            </span>
          </span>
        </div>
      )}
    </div>
  );
}
