// The selection email after an approved report (§4B-14): "Send selection
// email" opens the email made from the knowledge-base template, the
// interviewer checks or edits it and sends it. Once sent, the page says so
// and it cannot be sent again (the backend refuses a second one too).

import { Button, Group, Modal, Text, TextInput, Textarea } from '@mantine/core';
import { IconMailCheck, IconSend } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import { apiGet, apiPost } from '../../api/client';
import { POP_TRANSITION } from '../../components/ConfirmModal';
import { ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyDone } from '../../components/notify';
import classes from './Report.module.css';

const MAX_SUBJECT = 200;
const MAX_TEXT = 5000;

// The dialog: recipient, subject and text (editable), then "Send email".
function SelectionEmailModal({ interviewId, candidateName, onClose, onSent }) {
  const [email, setEmail] = useState(null); // { to, subject, text, template }
  const [failed, setFailed] = useState(null);
  const [sendError, setSendError] = useState(null);
  const [busy, setBusy] = useState(false);
  const url = `/interviews/${interviewId}/selection-email`;

  // Load the prepared email when the dialog opens.
  useEffect(() => {
    apiGet(url)
      .then(setEmail)
      .catch((error) => setFailed(error.message));
  }, [url]);

  async function send() {
    setBusy(true);
    setSendError(null);
    try {
      const page = await apiPost(url, { subject: email.subject.trim(), text: email.text.trim() });
      notifyDone(`Selection email sent to ${candidateName}`);
      onSent(page);
    } catch (error) {
      setSendError(error.message);
      setBusy(false);
    }
  }

  const ready = email && email.subject.trim().length >= 2 && email.text.trim().length >= 10;
  return (
    <Modal
      opened
      onClose={onClose}
      size={620}
      radius="md"
      centered
      transitionProps={POP_TRANSITION}
      title={
        <Text fz={18} fw={600}>
          Send the selection email
        </Text>
      }
    >
      {failed && <ErrorBanner title="The email couldn’t be prepared.">{failed}</ErrorBanner>}
      {!failed && !email && <Skeleton widths={[50, 90, 80, 60]} />}
      {email && (
        <>
          <div className={classes.modalText}>
            Check the email before it goes to <b>{candidateName}</b> ({email.to}). It is sent once; the candidate is
            then marked as selected. Offer details are not included: HR sends them separately.
          </div>
          <TextInput
            label="Subject"
            value={email.subject}
            maxLength={MAX_SUBJECT}
            onChange={(event) => setEmail({ ...email, subject: event.currentTarget.value })}
          />
          <Textarea
            mt="sm"
            label="Text"
            description={`From: ${email.template}`}
            autosize
            minRows={8}
            maxRows={16}
            maxLength={MAX_TEXT}
            value={email.text}
            onChange={(event) => setEmail({ ...email, text: event.currentTarget.value })}
          />
          {sendError && (
            <Text mt="sm" fz={14} c="#B03A2E" role="alert">
              {sendError}
            </Text>
          )}
        </>
      )}
      <Group justify="flex-end" gap={8} mt="lg">
        <Button variant="default" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button leftSection={<IconSend size={16} />} onClick={send} disabled={!ready} loading={busy}>
          Send email
        </Button>
      </Group>
    </Modal>
  );
}

// Under the "Approved" banner: the button, or when the email was sent.
export default function SelectionEmail({ interviewId, candidateName, selectedAt, onSent }) {
  const [open, setOpen] = useState(false);
  if (selectedAt) {
    return (
      <div className={`${classes.banner} ${classes.bannerApproved}`} role="status">
        <IconMailCheck size={18} />
        <span>
          <b>Selected.</b> The selection email was sent on {new Date(selectedAt).toLocaleString('en-GB')}.
        </span>
      </div>
    );
  }
  return (
    <div className={classes.selectionRow}>
      <span>Selected this candidate? Tell them with the selection email.</span>
      <Button variant="light" leftSection={<IconSend size={16} />} onClick={() => setOpen(true)}>
        Send selection email
      </Button>
      {open && (
        <SelectionEmailModal
          interviewId={interviewId}
          candidateName={candidateName}
          onClose={() => setOpen(false)}
          onSent={(page) => {
            setOpen(false);
            onSent(page);
          }}
        />
      )}
    </div>
  );
}
