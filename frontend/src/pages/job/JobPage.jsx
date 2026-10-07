// One job's page (design: CV Screening Results.dc.html, JobHeader and the
// "No CVs yet" state). Before screening exists it shows the applicants: the
// CVs the CV Collector took from the job's Google Form. The ranking and
// "Screen CVs" come here later. Interviewers only (route guard + backend).

import { Anchor, Button, Group, Modal, Text } from '@mantine/core';
import {
  IconAlertTriangle,
  IconChevronRight,
  IconCircleCheck,
  IconExternalLink,
  IconFileText,
  IconInbox,
  IconMessageCircle,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';

import { apiDelete, apiGet, apiGetFile } from '../../api/client';
import { ErrorBanner, Skeleton } from '../../components/Feedback';
import StatusBadge from '../../components/StatusBadge';
import { STAGES } from '../assistant/labels';
import classes from './JobPage.module.css';

// "7 Oct, 15:09" for the time a CV arrived.
function receivedAt(value) {
  return new Date(value).toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// "1 CV received" / "2 CVs received".
function cvCount(count) {
  return `${count} ${count === 1 ? 'CV' : 'CVs'} received`;
}

// Open a PDF in a new tab, or download a Word file. The file is fetched with
// the login token, so a plain link would not work. The tab is opened at
// once (before the download) so the browser does not block it as a pop-up.
async function openCv(jobId, applicant) {
  const isPdf = applicant.cv_filename.toLowerCase().endsWith('.pdf');
  const tab = isPdf ? window.open('', '_blank') : null;
  try {
    const file = await apiGetFile(`/jobs/${jobId}/cvs/${applicant.id}/file`);
    const url = URL.createObjectURL(file);
    if (tab) {
      tab.location.href = url;
    } else {
      const link = document.createElement('a');
      link.href = url;
      link.download = applicant.cv_filename;
      link.click();
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000); // free the memory later
  } catch (error) {
    tab?.close();
    throw error;
  }
}

// One applicant row: who, when, which file, status and actions.
function ApplicantRow({ applicant, onView, onRemove, viewing }) {
  const received = applicant.status !== 'rejected';
  return (
    <div className={classes.item}>
      <div className={classes.row}>
        <div className={classes.who}>
          <span className={classes.name}>{applicant.full_name || 'Name not given'}</span>
          <span className={classes.email}>{applicant.email || '—'}</span>
        </div>
        <div className={classes.when}>{receivedAt(applicant.received_at)}</div>
        <div className={`${classes.file} ${classes.fileColumn}`} title={applicant.cv_filename}>
          {applicant.cv_filename}
        </div>
        <div className={classes.status}>
          {received ? (
            <StatusBadge tone="success" icon={<IconCircleCheck size={13} />}>
              Received
            </StatusBadge>
          ) : (
            <StatusBadge tone="warning" icon={<IconAlertTriangle size={13} />}>
              Rejected
            </StatusBadge>
          )}
        </div>
        <div className={classes.actions}>
          {received && (
            <Button
              size="xs"
              variant="light"
              leftSection={<IconFileText size={14} />}
              loading={viewing}
              onClick={() => onView(applicant)}
            >
              View CV
            </Button>
          )}
          <button
            type="button"
            className={classes.iconButton}
            title="Remove applicant"
            aria-label={`Remove ${applicant.full_name || 'applicant'}`}
            onClick={() => onRemove(applicant)}
          >
            <IconTrash size={16} />
          </button>
        </div>
      </div>
      {!received && applicant.problem && <div className={classes.problem}>{applicant.problem}</div>}
    </div>
  );
}

// The page: job header, then the applicants (or the empty state).
export default function JobPage() {
  const { jobId } = useParams();
  const [job, setJob] = useState(null);
  const [applicants, setApplicants] = useState(null); // null = loading
  const [failed, setFailed] = useState(null); // message, or null
  const [viewingId, setViewingId] = useState(null);
  const [removing, setRemoving] = useState(null); // applicant to confirm
  const [removeBusy, setRemoveBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  // Load the job and its applicants.
  const load = useCallback(async () => {
    setFailed(null);
    try {
      const [jobData, cvs] = await Promise.all([apiGet(`/jobs/${jobId}`), apiGet(`/jobs/${jobId}/cvs`)]);
      setJob(jobData);
      setApplicants(cvs);
    } catch (error) {
      setFailed(error.message);
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  // Show an applicant's CV.
  async function view(applicant) {
    setViewingId(applicant.id);
    setActionError(null);
    try {
      await openCv(jobId, applicant);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setViewingId(null);
    }
  }

  // Remove the confirmed applicant and their CV file.
  async function remove() {
    setRemoveBusy(true);
    setActionError(null);
    try {
      await apiDelete(`/jobs/${jobId}/cvs/${removing.id}`);
      setRemoving(null);
      await load();
    } catch (error) {
      setActionError(error.message);
      setRemoving(null);
    } finally {
      setRemoveBusy(false);
    }
  }

  if (failed) {
    return (
      <ErrorBanner title="We couldn’t load this job." onRetry={load}>
        {failed}
      </ErrorBanner>
    );
  }

  if (!job || !applicants) {
    return (
      <div className={classes.card}>
        <Skeleton />
      </div>
    );
  }

  const stage = STAGES[job.stage];
  const rejected = applicants.filter((a) => a.status === 'rejected').length;

  return (
    <div className={classes.page}>
      <header className={classes.header}>
        <nav className={classes.breadcrumb} aria-label="Breadcrumb">
          <Link to="/jobs">Jobs</Link>
          <IconChevronRight size={14} />
          <span>{job.title}</span>
        </nav>
        <div className={classes.titleRow}>
          <div className={classes.titleBlock}>
            <h1 className={classes.title}>{job.title}</h1>
            <div className={classes.meta}>
              <span>{cvCount(job.cvs_received)}</span>
              {stage && (
                <>
                  <span className={classes.dot}>·</span>
                  <StatusBadge tone={stage.attention ? 'warning' : 'neutral'}>{stage.text}</StatusBadge>
                </>
              )}
            </div>
          </div>
          <Group gap={8} className={classes.headerActions}>
            {job.job_board_post_url && (
              <Button
                component="a"
                href={job.job_board_post_url}
                target="_blank"
                rel="noopener noreferrer"
                variant="default"
                leftSection={<IconExternalLink size={16} />}
              >
                View job post
              </Button>
            )}
            <Button component={Link} to={`/assistant/${job.id}`} leftSection={<IconMessageCircle size={16} />}>
              Open chat
            </Button>
          </Group>
        </div>
      </header>

      {actionError && <ErrorBanner title="That didn’t work.">{actionError}</ErrorBanner>}

      {applicants.length === 0 ? (
        <div className={classes.empty}>
          <span className={classes.emptyIcon}>
            <IconInbox size={24} />
          </span>
          <div className={classes.emptyTitle}>No CVs yet</div>
          <div className={classes.emptyText}>
            CVs sent through this job’s application form appear here automatically. New ones are
            checked every 5 minutes.
          </div>
          {/* Applicants must use the job post's link: it fills in the job. */}
          {job.job_board_post_url ? (
            <Anchor href={job.job_board_post_url} target="_blank" rel="noopener noreferrer" fz={15} fw={600}>
              Open the job post <IconExternalLink size={13} />
            </Anchor>
          ) : (
            <Text fz={15} c="#7A5000">
              The job is not posted yet. Post it from the chat so people can apply.
            </Text>
          )}
        </div>
      ) : (
        <section className={classes.card} aria-label="Applicants">
          <div className={classes.cardTop}>
            <div>
              <div className={classes.cardTitle}>Applicants</div>
              <div className={classes.cardHint}>
                {cvCount(job.cvs_received)}
                {rejected > 0 && ` · ${rejected} rejected`} · new CVs arrive every 5 minutes
              </div>
            </div>
            <button type="button" className={classes.refresh} onClick={load} title="Check for new CVs">
              <IconRefresh size={16} />
              <span>Refresh</span>
            </button>
          </div>
          <div className={classes.head}>
            <div>Applicant</div>
            <div className={classes.when}>Received</div>
            <div className={classes.fileColumn}>CV file</div>
            <div>Status</div>
            <div />
          </div>
          {applicants.map((applicant) => (
            <ApplicantRow
              key={applicant.id}
              applicant={applicant}
              viewing={viewingId === applicant.id}
              onView={view}
              onRemove={setRemoving}
            />
          ))}
        </section>
      )}

      <Modal
        opened={Boolean(removing)}
        onClose={() => setRemoving(null)}
        title="Remove this applicant?"
        centered
      >
        <Text fz={15} c="#48535B" lh={1.55}>
          {removing?.full_name || 'This applicant'} and their CV will be deleted from CandiVue. This
          can’t be undone. The answer in the Google Form is not changed.
        </Text>
        <Group justify="flex-end" mt="lg" gap={8}>
          <Button variant="default" onClick={() => setRemoving(null)}>
            Cancel
          </Button>
          <Button color="red" loading={removeBusy} onClick={remove}>
            Remove
          </Button>
        </Group>
      </Modal>
    </div>
  );
}
