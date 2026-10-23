// The interviewer's review of the report (HITL, §4B-7; design: ReviewBar
// and RequestChangesModal): approve it, or request changes with a comment
// that is used to write the next version.

import { Button, Group, Modal, Textarea } from '@mantine/core';
import { IconCheck, IconCircleCheck, IconEye, IconMessage2 } from '@tabler/icons-react';
import { useState } from 'react';

import { POP_TRANSITION } from '../../components/ConfirmModal';
import StatusBadge from '../../components/StatusBadge';
import classes from './Report.module.css';
import { REVIEW } from './reportFormat';

const ICONS = { waiting: IconEye, changes: IconMessage2, approved: IconCircleCheck };
const MAX_COMMENT = 1000;

// "What should change?" (required), then "Send request".
function RequestChangesModal({ opened, onClose, onSend, busy }) {
  const [comment, setComment] = useState('');
  const empty = comment.trim() === '';
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Request changes"
      centered
      radius="md"
      transitionProps={POP_TRANSITION}
    >
      <div className={classes.modalText}>
        Your comment is used to regenerate the report. You’ll review it again before it is final.
      </div>
      <Textarea
        label="What should change?"
        description="Refer to a section or timestamp where you can."
        required
        autosize
        minRows={4}
        maxLength={MAX_COMMENT}
        value={comment}
        onChange={(event) => setComment(event.currentTarget.value)}
        data-autofocus
      />
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button onClick={() => onSend(comment.trim())} disabled={empty} loading={busy}>
          Send request
        </Button>
      </Group>
    </Modal>
  );
}

// The bar at the bottom of the report: status, a hint and the two actions.
export default function ReviewBar({ state, onApprove, onRequestChanges, busy }) {
  const [asking, setAsking] = useState(false);
  const review = REVIEW[state];
  const Icon = ICONS[state];

  // Send the comment; the dialog closes once the request is accepted.
  async function send(comment) {
    if (await onRequestChanges(comment)) setAsking(false);
  }

  return (
    <div className={classes.reviewBar}>
      <div className={classes.reviewStatus}>
        <StatusBadge tone={review.tone} icon={<Icon size={13} />}>
          {review.label}
        </StatusBadge>
        <span>{review.hint}</span>
      </div>
      {state === 'waiting' && (
        <Group gap={10}>
          <Button variant="light" leftSection={<IconMessage2 size={16} />} onClick={() => setAsking(true)} disabled={busy}>
            Request changes
          </Button>
          <Button leftSection={<IconCheck size={16} />} onClick={onApprove} loading={busy}>
            Approve report
          </Button>
        </Group>
      )}
      <RequestChangesModal opened={asking} onClose={() => setAsking(false)} onSend={send} busy={busy} />
    </div>
  );
}
