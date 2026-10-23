// The selection email after an approved report (§4B-14, §4B-15): "Send
// selection email" (on the report page or in the final ranking on the
// Reports page) opens the email made from the knowledge-base template. The
// interviewer edits it, checks the preview (the email exactly as the
// candidate will see it), confirms and sends it. A warning shows when the
// identity check did not confirm the candidate. Once sent, the page says so
// and it cannot be sent again (the backend refuses a second one too).

import { Alert, Button, Group, Modal, SegmentedControl, Text, TextInput, Textarea } from '@mantine/core';
import { IconAlertTriangle, IconMailCheck, IconSend } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import { apiGet, apiPost } from '../../api/client';
import { POP_TRANSITION } from '../../components/ConfirmModal';
import { ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyDone } from '../../components/notify';
import classes from './Report.module.css';

const MAX_SUBJECT = 200;
const MAX_TEXT = 5000;

// The email as the candidate will see it, in a sandboxed frame (no scripts,
// nothing can be clicked away from here).
function Preview({ interviewId, email }) {
  const [html, setHtml] = useState(null);
  const [failed, setFailed] = useState(null);

  useEffect(() => {
    let stopped = false;
    apiPost(`/interviews/${interviewId}/selection-email/preview`, {
      subject: email.subject.trim(),
      text: email.text.trim(),
    })
      .then((answer) => !stopped && setHtml(answer.html))
      .catch((error) => !stopped && setFailed(error.message));
    return () => {
      stopped = true;
    };
  }, [interviewId, email.subject, email.text]);

  if (failed) return <ErrorBanner title="The preview couldn’t be shown.">{failed}</ErrorBanner>;
  if (!html) return <Skeleton widths={[60, 90, 80, 70]} />;
  return (
    <div className={classes.previewBox}>
      <div className={classes.previewHead}>
        <span>Subject</span>
        <b>{email.subject.trim()}</b>
      </div>
      <iframe className={classes.previewFrame} title="Email preview" sandbox="" srcDoc={html} />
    </div>
  );
}

// The dialog: edit or preview, then confirm and send. identityWarning: a
// sentence when the identity check did not confirm the candidate.
export function SelectionEmailModal({ interviewId, candidateName, identityWarning, onClose, onSent }) {
  const [email, setEmail] = useState(null); // { to, subject, text, template }
  const [failed, setFailed] = useState(null);
  const [sendError, setSendError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState('edit'); // edit | preview
  const [confirming, setConfirming] = useState(false);
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
      setConfirming(false);
      setBusy(false);
    }
  }

  const ready = email && email.subject.trim().length >= 2 && email.text.trim().length >= 10;
  return (
    <Modal
      opened
      onClose={busy ? () => {} : onClose}
      size={660}
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
            To <b>{candidateName}</b> ({email.to}). It is sent once; the candidate is then marked as selected. Offer
            details are not included: HR sends them separately.
          </div>
          {identityWarning && (
            <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />} mb="sm">
              {identityWarning}
            </Alert>
          )}
          <SegmentedControl
            size="xs"
            mb="sm"
            value={view}
            onChange={setView}
            data={[
              { value: 'edit', label: 'Edit' },
              { value: 'preview', label: 'Preview' },
            ]}
            disabled={!ready}
          />
          {view === 'edit' ? (
            <>
              <TextInput
                label="Subject"
                value={email.subject}
                maxLength={MAX_SUBJECT}
                onChange={(event) => setEmail({ ...email, subject: event.currentTarget.value })}
              />
              <Textarea
                mt="sm"
                label="Text"
                description={`From: ${email.template}. A blank line starts a new paragraph.`}
                autosize
                minRows={8}
                maxRows={16}
                maxLength={MAX_TEXT}
                value={email.text}
                onChange={(event) => setEmail({ ...email, text: event.currentTarget.value })}
              />
            </>
          ) : (
            <Preview interviewId={interviewId} email={email} />
          )}
          {sendError && (
            <Text mt="sm" fz={14} c="var(--cv-danger-text)" role="alert">
              {sendError}
            </Text>
          )}
        </>
      )}
      {confirming ? (
        <div className={classes.confirmRow} role="alert">
          <span>
            Send this email to <b>{email.to}</b> now? It can’t be undone.
          </span>
          <Group gap={8} wrap="nowrap">
            <Button variant="default" onClick={() => setConfirming(false)} disabled={busy}>
              Back
            </Button>
            <Button leftSection={<IconSend size={16} />} onClick={send} loading={busy}>
              Yes, send it
            </Button>
          </Group>
        </div>
      ) : (
        <Group justify="flex-end" gap={8} mt="lg">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button leftSection={<IconSend size={16} />} onClick={() => setConfirming(true)} disabled={!ready}>
            Send email
          </Button>
        </Group>
      )}
    </Modal>
  );
}

// Under the "Approved" banner: the button, or when the email was sent.
export default function SelectionEmail({ interviewId, candidateName, selectedAt, identityWarning, onSent }) {
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
          identityWarning={identityWarning}
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
