// Jobs list (design: Jobs.dc.html). Jobs are created through the Hiring
// Assistant: the button makes an empty job and opens its chat (§4B-8).
// Clicking a job opens its page with the applicants.
// "CVs received" counts the CVs the CV Collector took from the Google Form;
// "Screening" shows the job's latest screening run; "Interviews" the
// scheduled ones.

import { Button, Loader } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import {
  IconAlertTriangle,
  IconBriefcase,
  IconCheck,
  IconChevronRight,
  IconClock,
  IconSparkles,
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import { apiGet, apiPost } from '../api/client';
import { EmptyState, ErrorBanner, Skeleton } from '../components/Feedback';
import { notifyError } from '../components/notify';
import StatusBadge from '../components/StatusBadge';
import classes from './JobsPage.module.css';

// Show a date like "Today" or "5 Oct".
export function shortDate(value) {
  const date = new Date(value);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return 'Today';
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

// The job's latest screening run as a badge (design: run status badges).
function ScreeningBadge({ job }) {
  if (job.screening_status === 'completed') {
    return (
      <StatusBadge tone="success" icon={<IconCheck size={13} />}>
        {job.ranked_count} ranked
      </StatusBadge>
    );
  }
  if (job.screening_status === 'pending' || job.screening_status === 'running') {
    return (
      <StatusBadge tone="info" icon={<Loader size={10} color="var(--cv-info-text-strong)" />}>
        Screening…
      </StatusBadge>
    );
  }
  if (job.screening_status === 'failed') {
    return (
      <StatusBadge tone="danger" icon={<IconAlertTriangle size={13} />}>
        Screening stopped
      </StatusBadge>
    );
  }
  return (
    <StatusBadge tone="neutral" icon={<IconClock size={13} />}>
      Not screened
    </StatusBadge>
  );
}

// Button that creates an empty job and opens its Hiring Assistant chat.
function CreateJobButton() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);

  // Create the job on the backend, then go to its chat.
  async function createJob() {
    setCreating(true);
    try {
      const job = await apiPost('/jobs');
      navigate(`/assistant/${job.id}`);
    } catch (error) {
      notifyError('The job wasn’t created.', error);
      setCreating(false);
    }
  }

  return (
    <Button leftSection={<IconSparkles size={16} />} loading={creating} onClick={createJob}>
      Create job with Hiring Assistant
    </Button>
  );
}

// The jobs page: loading, error, empty or the jobs table.
export default function JobsPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState(null); // null = still loading
  const [failed, setFailed] = useState(false);
  useDocumentTitle('Jobs · CandiVue AI');

  // Load the jobs from the backend.
  const load = useCallback(async () => {
    setFailed(false);
    try {
      setJobs(await apiGet('/jobs'));
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  let body;
  if (failed) {
    body = (
      <ErrorBanner title="We couldn’t load your jobs." onRetry={load}>
        Check your connection and try again.
      </ErrorBanner>
    );
  } else if (jobs === null) {
    body = (
      <div className={classes.card}>
        <Skeleton />
      </div>
    );
  } else if (jobs.length === 0) {
    body = (
      <div className={classes.card}>
        <EmptyState icon={IconBriefcase} title="No jobs yet" action={<CreateJobButton />}>
          Describe the role to the Hiring Assistant. It drafts the job description for you to
          approve.
        </EmptyState>
      </div>
    );
  } else {
    body = (
      <div className={classes.card}>
        <div className={classes.head}>
          <div>Job</div>
          <div>CVs received</div>
          <div>Screening</div>
          <div className={classes.medium}>Interviews</div>
          <div className={classes.medium}>Updated</div>
          <div />
        </div>
        {jobs.map((job) => (
          <button
            type="button"
            key={job.id}
            className={classes.row}
            onClick={() => navigate(`/jobs/${job.id}`)}
          >
            <div className={classes.jobTitle}>{job.title}</div>
            <div className={`${classes.number} ${classes.cvs}`}>
              {job.cvs_received}
              <span className={classes.cvLabel}>{job.cvs_received === 1 ? ' CV' : ' CVs'}</span>
            </div>
            <div className={classes.status}>
              <ScreeningBadge job={job} />
            </div>
            <div className={`${classes.muted} ${classes.medium}`}>{job.interview_count || '—'}</div>
            <div className={`${classes.muted} ${classes.medium}`}>{shortDate(job.updated_at)}</div>
            <IconChevronRight size={16} className={classes.chevron} />
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className={classes.page}>
      <div className={classes.top}>
        <h1 className={classes.title}>Jobs</h1>
        {jobs?.length > 0 && <CreateJobButton />}
      </div>
      {body}
    </div>
  );
}
