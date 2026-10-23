// Reports (design: Reports.dc.html): the assessment reports of one job, one
// row per interviewed candidate, with the suitability position and where
// the report is (being prepared, waiting for review, approved). A report is
// prepared automatically after each interview ends. Interviewers only.

import { Select } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import { IconFileText } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import { apiGet } from '../../api/client';
import { EmptyState, ErrorBanner, Skeleton } from '../../components/Feedback';
import StatusBadge from '../../components/StatusBadge';
import { whenText } from '../../utils/dates';
import { usePolling } from '../../utils/usePolling';
import classes from './Report.module.css';
import { listStatus } from './reportFormat';

export default function ReportsPage() {
  useDocumentTitle('Reports · CandiVue AI');
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [jobs, setJobs] = useState(null);
  const [rows, setRows] = useState(null);
  const [failed, setFailed] = useState(false);
  // Default: the first job with a ranking (only screened jobs have interviews).
  const fallback = jobs?.find((job) => job.ranked_count > 0) ?? jobs?.[0];
  const jobId = search.get('job') ?? (fallback ? String(fallback.id) : null);

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await apiGet('/jobs'));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  const loadRows = useCallback(async () => {
    if (!jobId) return;
    try {
      setRows(await apiGet(`/jobs/${jobId}/reports`));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [jobId]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);
  useEffect(() => {
    setRows(null);
    loadRows();
  }, [loadRows]);
  usePolling(loadRows, Boolean(rows?.some((row) => listStatus(row).label === 'Being prepared')));

  let body;
  if (failed) {
    body = (
      <ErrorBanner title="We couldn’t load reports." onRetry={jobs ? loadRows : loadJobs}>
        Check your connection and try again.
      </ErrorBanner>
    );
  } else if (jobs !== null && jobs.length === 0) {
    body = (
      <div className={classes.listCard}>
        <EmptyState icon={IconFileText} title="No jobs yet">
          Create a job with the Hiring Assistant. Its reports appear here after its interviews.
        </EmptyState>
      </div>
    );
  } else if (rows === null) {
    body = (
      <div className={classes.listCard}>
        <Skeleton />
      </div>
    );
  } else if (rows.length === 0) {
    body = (
      <div className={classes.listCard}>
        <EmptyState icon={IconFileText} title="No reports for this job yet">
          A report is prepared automatically after each interview ends, then waits here for your review.
        </EmptyState>
      </div>
    );
  } else {
    body = (
      <div className={classes.listCard}>
        <div className={classes.listHead}>
          <div>Candidate</div>
          <div>Interview</div>
          <div>Suitability position</div>
          <div>Status</div>
        </div>
        {rows.map((row) => {
          const status = listStatus(row);
          return (
            <button
              key={row.interview_id}
              type="button"
              className={classes.listRow}
              onClick={() => navigate(`/interviews/${row.interview_id}/report`)}
            >
              <span className={classes.listName}>{row.candidate_name}</span>
              <span>{whenText(row.interview_at)}</span>
              <span>{row.report?.content?.position?.headline ?? '—'}</span>
              <span>
                <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
              </span>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className={classes.page}>
      <div className={classes.listTop}>
        <h1 className={classes.title}>Reports</h1>
        {jobs?.length > 0 && (
          <Select
            className={classes.jobSelect}
            aria-label="Job"
            data={jobs.map((job) => ({ value: String(job.id), label: job.title }))}
            value={jobId}
            onChange={(value) => setSearch({ job: value })}
            allowDeselect={false}
            searchable
          />
        )}
      </div>
      {body}
    </div>
  );
}
