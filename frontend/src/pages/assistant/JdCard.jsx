// One job description version (design: JdApprovalCard, frames 1a and 2a).
// While it waits for review it gets the three actions: reject with
// feedback, edit, approve. Posting comes later, so the button says "Approve".

import { Button } from '@mantine/core';
import { IconCheck, IconCircleCheck, IconEye, IconPencil, IconX } from '@tabler/icons-react';
import { useState } from 'react';

import StatusBadge from '../../components/StatusBadge';
import { shortDate } from '../JobsPage';
import classes from './Assistant.module.css';
import { sourceLabel } from './labels';

// The status badge in the card header.
function JdStatus({ jd, waiting }) {
  if (jd.status === 'approved') {
    return (
      <StatusBadge tone="success" icon={<IconCircleCheck size={13} />}>
        Approved by you · {shortDate(jd.approved_at)}
      </StatusBadge>
    );
  }
  if (jd.status === 'rejected') {
    return (
      <StatusBadge tone="neutral" icon={<IconX size={13} />}>
        Not used
      </StatusBadge>
    );
  }
  return waiting ? (
    <StatusBadge tone="warning" icon={<IconEye size={13} />}>
      Waiting for your approval
    </StatusBadge>
  ) : (
    <StatusBadge tone="neutral">Draft</StatusBadge>
  );
}

// The card. `previousFeedback`: why the version before this one was rejected.
export default function JdCard({ jd, waiting, busy, previousFeedback, onApprove, onEdit, onReject }) {
  const [open, setOpen] = useState(false);
  const { content } = jd;

  return (
    <div className={`${classes.jdCard} ${waiting ? classes.jdPending : ''}`}>
      <div className={classes.jdHead}>
        <span className={classes.jdHeadTitle}>Job description · version {jd.version}</span>
        <JdStatus jd={jd} waiting={waiting} />
      </div>

      <div className={classes.jdBody}>
        <p className={`${classes.jdAbout} ${open ? '' : classes.jdClamp}`}>{content.about}</p>
        {open && (
          <>
            <div className={classes.jdSection}>Responsibilities</div>
            <ul className={classes.jdList}>
              {content.responsibilities.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </>
        )}
        <button type="button" className={classes.toggle} onClick={() => setOpen(!open)}>
          {open ? 'Show less' : 'Show the full description'}
        </button>
      </div>

      {(jd.sources.length > 0 || previousFeedback) && (
        <div className={classes.sources}>
          {jd.sources.length > 0 && <span className={classes.sourcesLabel}>Based on</span>}
          {jd.sources.map((source) => (
            <span key={source.document_id} className={classes.sourceChip}>
              {sourceLabel(source)}
            </span>
          ))}
          {previousFeedback && (
            <span className={classes.rejectedNote}>
              Version {jd.version - 1} rejected: “{previousFeedback}”
            </span>
          )}
        </div>
      )}

      {waiting && (
        <div className={classes.jdActions}>
          <Button variant="subtle" color="red" onClick={onReject} disabled={busy}>
            Reject with feedback
          </Button>
          <Button variant="light" leftSection={<IconPencil size={15} />} onClick={onEdit} disabled={busy}>
            Edit
          </Button>
          <Button leftSection={<IconCheck size={15} />} onClick={onApprove} loading={busy}>
            Approve
          </Button>
        </div>
      )}
    </div>
  );
}
