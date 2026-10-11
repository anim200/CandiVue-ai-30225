// Interviews (design: Interviews.dc.html): upcoming and past interviews.
// Interviews are planned in the Hiring Assistant and appear here once the
// interviewer confirms them (the invitation email is sent then). "Join now"
// opens the video call (any time until the interview is ended). "Send
// invitation" emails it again; "Copy link" makes the candidate's private
// link (only its hash is stored, so a new link replaces the old one, also
// an emailed one); "Cancel" stops the interview and its link.
// Interviewers only.

import { ActionIcon, Button, Group, SegmentedControl, Tooltip } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import {
  IconBan,
  IconCalendarEvent,
  IconCheck,
  IconClock,
  IconLink,
  IconMailCheck,
  IconMailX,
  IconPlayerPlay,
  IconPlayerRecord,
  IconSend,
  IconVideo,
  IconX,
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { apiGet, apiPost } from '../api/client';
import ConfirmModal from '../components/ConfirmModal';
import { EmptyState, ErrorBanner, Skeleton } from '../components/Feedback';
import { notifyDone, notifyError } from '../components/notify';
import StatusBadge from '../components/StatusBadge';
import { whenText } from '../utils/dates';
import classes from './InterviewsPage.module.css';

const SESSION = {
  scheduled: { tone: 'neutral', icon: IconCalendarEvent, text: 'Scheduled' },
  live: { tone: 'info', icon: IconPlayerRecord, text: 'Live' },
  ended: { tone: 'success', icon: IconCheck, text: 'Ended' },
  cancelled: { tone: 'neutral', icon: IconBan, text: 'Cancelled' },
};
const INVITATION = {
  pending: { tone: 'warning', icon: IconClock, text: 'Invitation pending' },
  sent: { tone: 'success', icon: IconMailCheck, text: 'Invited' },
  failed: { tone: 'danger', icon: IconMailX, text: 'Invitation failed' },
};

// A status badge from one of the tables above.
function Badge({ of, value }) {
  const { tone, icon: Icon, text } = of[value];
  return (
    <StatusBadge tone={tone} icon={<Icon size={13} />}>
      {text}
    </StatusBadge>
  );
}

export default function InterviewsPage() {
  const [when, setWhen] = useState('upcoming');
  const [interviews, setInterviews] = useState(null); // null = loading
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(null); // "send-<id>" or "link-<id>"
  const [cancelling, setCancelling] = useState(null); // interview to confirm
  const [cancelBusy, setCancelBusy] = useState(false);
  const navigate = useNavigate();
  useDocumentTitle('Interviews · CandiVue AI');

  // Load the chosen list.
  const load = useCallback(async () => {
    setFailed(false);
    try {
      setInterviews(await apiGet(`/interviews?when=${when}`));
    } catch {
      setFailed(true);
    }
  }, [when]);

  useEffect(() => {
    setInterviews(null);
    load();
  }, [load]);

  // Email the invitation (again) with a new private link.
  async function send(interview) {
    setBusy(`send-${interview.id}`);
    try {
      const result = await apiPost(`/interviews/${interview.id}/send`);
      if (result.sent) notifyDone(`Invitation sent to ${interview.candidate_name}`);
      else notifyError('The invitation wasn’t sent.', result);
      await load();
    } catch (error) {
      notifyError('The invitation wasn’t sent.', error);
    } finally {
      setBusy(null);
    }
  }

  // Make a new private link and copy it (the previous one stops working).
  async function copyLink(interview) {
    setBusy(`link-${interview.id}`);
    try {
      const { link_token: token } = await apiPost(`/interviews/${interview.id}/link`);
      await navigator.clipboard.writeText(`${window.location.origin}/join/${token}`);
      notifyDone(`Link for ${interview.candidate_name} copied. Earlier links, also an emailed one, no longer work.`);
    } catch (error) {
      notifyError('The link wasn’t made.', error);
    } finally {
      setBusy(null);
    }
  }

  // Cancel the confirmed interview.
  async function cancel() {
    setCancelBusy(true);
    try {
      await apiPost(`/interviews/${cancelling.id}/cancel`);
      notifyDone(`Interview with ${cancelling.candidate_name} cancelled`);
      await load();
    } catch (error) {
      notifyError('The interview wasn’t cancelled.', error);
    } finally {
      setCancelling(null);
      setCancelBusy(false);
    }
  }

  let body;
  if (failed) {
    body = (
      <ErrorBanner title="We couldn’t load interviews." onRetry={load}>
        Check your connection and try again.
      </ErrorBanner>
    );
  } else if (interviews === null) {
    body = (
      <div className={classes.card}>
        <Skeleton />
      </div>
    );
  } else if (interviews.length === 0) {
    body = (
      <div className={classes.card}>
        <EmptyState icon={IconVideo} title={when === 'upcoming' ? 'No upcoming interviews' : 'No past interviews'}>
          Ask the Hiring Assistant to invite candidates from a job’s shortlist. Interviews appear here once you
          confirm them.
        </EmptyState>
      </div>
    );
  } else {
    body = (
      <div className={classes.card}>
        <div className={classes.head}>
          <div>Candidate</div>
          <div className={classes.medium}>Job</div>
          <div>Date and time</div>
          <div className={classes.medium}>Session</div>
          <div>Invitation</div>
          <div />
        </div>
        {interviews.map((interview) => (
          <div key={interview.id} className={classes.row}>
            <div className={classes.name}>{interview.candidate_name}</div>
            <Link to={`/jobs/${interview.job_id}`} className={`${classes.job} ${classes.medium}`}>
              {interview.job_title}
            </Link>
            <div className={classes.when}>
              {whenText(interview.scheduled_at)} · {interview.duration_minutes} min
            </div>
            <div className={classes.medium}>
              <Badge of={SESSION} value={interview.status} />
            </div>
            <div className={classes.invitation}>
              <Badge of={INVITATION} value={interview.invitation_status} />
            </div>
            <Group gap={6} wrap="nowrap" className={classes.actions}>
              {when === 'upcoming' && (
                <>
                  <Button
                    size="xs"
                    leftSection={<IconPlayerPlay size={14} />}
                    onClick={() => navigate(`/interviews/${interview.id}/room`)}
                  >
                    {interview.status === 'live' ? 'Rejoin' : 'Join now'}
                  </Button>
                  <Tooltip label={interview.invitation_status === 'pending' ? 'Send the invitation' : 'Send the invitation again'}>
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      loading={busy === `send-${interview.id}`}
                      onClick={() => send(interview)}
                      aria-label={`Send the invitation to ${interview.candidate_name}`}
                    >
                      <IconSend size={17} />
                    </ActionIcon>
                  </Tooltip>
                  <Tooltip label="Copy the private link">
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      loading={busy === `link-${interview.id}`}
                      onClick={() => copyLink(interview)}
                      aria-label={`Copy the private link for ${interview.candidate_name}`}
                    >
                      <IconLink size={17} />
                    </ActionIcon>
                  </Tooltip>
                  <Tooltip label="Cancel the interview">
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      onClick={() => setCancelling(interview)}
                      aria-label={`Cancel the interview with ${interview.candidate_name}`}
                    >
                      <IconX size={17} />
                    </ActionIcon>
                  </Tooltip>
                </>
              )}
            </Group>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={classes.page}>
      <div className={classes.top}>
        <h1 className={classes.title}>Interviews</h1>
        <SegmentedControl
          value={when}
          onChange={setWhen}
          data={[
            { value: 'upcoming', label: 'Upcoming' },
            { value: 'past', label: 'Past' },
          ]}
        />
      </div>
      {body}
      <ConfirmModal
        opened={Boolean(cancelling)}
        onClose={() => setCancelling(null)}
        title="Cancel this interview?"
        confirmLabel="Cancel interview"
        onConfirm={cancel}
        busy={cancelBusy}
      >
        The interview with {cancelling?.candidate_name} on {cancelling && whenText(cancelling.scheduled_at)} is
        cancelled and their link stops working. The candidate is not emailed about it.
      </ConfirmModal>
    </div>
  );
}
