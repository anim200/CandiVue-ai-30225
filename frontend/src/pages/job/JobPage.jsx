// One job's page (design: CV Screening Results.dc.html). Header with
// "Screen CVs", the scoring weights, the screening run (progress, ranking,
// excluded and unreadable CVs, candidate drawer) and the applicants: the
// CVs the CV Collector took from the job's Google Form, plus any added by
// hand ("Add CV"). Interviewers only (route guard + backend).

import { Anchor, Button, Collapse, FileButton, Group, Loader, Text } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import {
  IconAlertTriangle,
  IconChevronDown,
  IconChevronRight,
  IconCircleCheck,
  IconExternalLink,
  IconFileText,
  IconInbox,
  IconMessageCircle,
  IconPlayerPlay,
  IconRefresh,
  IconTrash,
  IconUpload,
  IconX,
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';

import { apiDelete, apiGet, apiGetFile, apiPost, apiUpload } from '../../api/client';
import ConfirmModal from '../../components/ConfirmModal';
import { ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyDone } from '../../components/notify';
import StatusBadge from '../../components/StatusBadge';
import { STAGES } from '../assistant/labels';
import classes from './JobPage.module.css';
import ScreeningResults, { ScreeningProgress } from './ScreeningResults';
import WeightsCard from './WeightsCard';

const POLL_MS = 2000; // progress refresh while screening runs
const ACTIVE = ['pending', 'running'];

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

// "Add CV": pick one or a few PDF/Word files (checked again by the backend).
function AddCvButton({ onFiles, busy, variant = 'default' }) {
  return (
    <FileButton
      onChange={onFiles}
      accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      multiple
    >
      {(props) => (
        <Button {...props} variant={variant} loading={busy} leftSection={<IconUpload size={16} />}>
          Add CV
        </Button>
      )}
    </FileButton>
  );
}

// What happened to each file of the last "Add CV": added, or why not.
function UploadResults({ results, onClose }) {
  const added = results.filter((r) => r.added).length;
  return (
    <div className={classes.uploadResults} role="status">
      <div className={classes.uploadTop}>
        <span>
          {added} of {results.length} {results.length === 1 ? 'file' : 'files'} added
        </span>
        <button type="button" className={classes.closeButton} onClick={onClose} aria-label="Close">
          <IconX size={15} />
        </button>
      </div>
      <ul className={classes.uploadList}>
        {results.map((result, index) => (
          <li key={index} className={result.added ? classes.uploadOk : classes.uploadBad}>
            {result.added ? <IconCircleCheck size={15} /> : <IconAlertTriangle size={15} />}
            <span className={classes.uploadName}>{result.filename}</span>
            {!result.added && <span>· {result.message}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

// One applicant row: who, when, which file, status and actions.
function ApplicantRow({ applicant, onView, onRemove, viewing }) {
  const received = applicant.status !== 'rejected';
  return (
    <div className={classes.item}>
      <div className={classes.row}>
        <div className={classes.who}>
          <span className={classes.name}>{applicant.full_name || 'Name not given'}</span>
          <span className={classes.email}>
            {applicant.source === 'upload' && <span className={classes.source}>Added by hand</span>}
            {applicant.email || (applicant.source === 'upload' ? '' : '—')}
          </span>
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
            // The file was refused, not the person: CandiVue never rejects anyone.
            <StatusBadge tone="warning" icon={<IconAlertTriangle size={13} />}>
              File refused
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
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState(null); // last "Add CV" outcome
  const [uploadProgress, setUploadProgress] = useState(null); // "3 of 19"
  const [screening, setScreening] = useState(null); // latest run and results
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [applicantsOpen, setApplicantsOpen] = useState(null); // null = automatic
  useDocumentTitle(`${job?.title ?? 'Job'} · CandiVue AI`);

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

  // Load the latest screening run (progress or results).
  const loadScreening = useCallback(async () => {
    try {
      setScreening(await apiGet(`/jobs/${jobId}/screenings/latest`));
    } catch (error) {
      setActionError(error.message);
    }
  }, [jobId]);

  useEffect(() => {
    loadScreening();
  }, [loadScreening]);

  // While a run works, refresh its progress; when it ends, reload the page data.
  const running = ACTIVE.includes(screening?.run?.status);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(async () => {
      const latest = await apiGet(`/jobs/${jobId}/screenings/latest`).catch(() => null);
      if (!latest) return;
      setScreening(latest);
      if (ACTIVE.includes(latest.run?.status)) return;
      load(); // names/emails read from CVs
      if (latest.run?.status === 'completed') notifyDone(`Screening finished: ${latest.ranked.length} ranked`);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [running, jobId, load]);

  // Start screening all of the job's CVs (one batch, in the background).
  async function startScreening() {
    setStarting(true);
    setActionError(null);
    try {
      setScreening(await apiPost(`/jobs/${jobId}/screenings`));
    } catch (error) {
      setActionError(error.message);
    } finally {
      setStarting(false);
    }
  }

  // "View CV" from the screening drawer (same as in the applicants list).
  const viewResultCv = (result) => view({ id: result.candidate_id, cv_filename: result.cv_filename });

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

  // Send the chosen files one at a time (small requests, progress shown);
  // each file is added or refused on its own, and one failure never stops
  // the rest.
  async function addCvs(files) {
    if (!files?.length) return;
    setUploading(true);
    setActionError(null);
    setUploadResults(null);
    const results = [];
    for (const [index, file] of files.entries()) {
      setUploadProgress(`${index + 1} of ${files.length}`);
      const form = new FormData();
      form.append('files', file);
      try {
        results.push(...(await apiUpload(`/jobs/${jobId}/cvs`, form)));
      } catch (error) {
        results.push({ filename: file.name, added: false, message: error.message });
      }
    }
    setUploadResults(results);
    setUploadProgress(null);
    setUploading(false);
    await load();
  }

  // Remove the confirmed applicant and their CV file.
  async function remove() {
    setRemoveBusy(true);
    setActionError(null);
    try {
      await apiDelete(`/jobs/${jobId}/cvs/${removing.id}`);
      notifyDone(`Removed ${removing.full_name || 'the applicant'}`);
      setRemoving(null);
      await load();
    } catch (error) {
      setActionError(error.message);
      setRemoving(null);
    } finally {
      setRemoveBusy(false);
    }
  }

  // "Refresh": check for new CVs, with a spinner so the click is visible.
  async function refresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
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
  // Once there is a ranking, the applicants list starts folded (shorter page).
  const showApplicants = applicantsOpen ?? screening?.run?.status !== 'completed';

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
              {screening?.run?.finished_at && (
                <>
                  <span className={classes.dot}>·</span>
                  <span>Last screened {receivedAt(screening.run.finished_at)}</span>
                </>
              )}
              {stage && (
                <>
                  <span className={classes.dot}>·</span>
                  <StatusBadge tone={stage.attention ? 'warning' : 'neutral'}>{stage.text}</StatusBadge>
                </>
              )}
            </div>
          </div>
          <Group gap={8} className={classes.headerActions}>
            {applicants.length > 0 && (
              <Button
                onClick={startScreening}
                loading={starting}
                disabled={!job.profile || running}
                leftSection={running ? <Loader size={14} color="white" /> : <IconPlayerPlay size={16} />}
                className={running ? classes.screeningButton : undefined}
              >
                {running ? 'Screening…' : 'Screen CVs'}
              </Button>
            )}
            <AddCvButton onFiles={addCvs} busy={uploading} />
            {uploadProgress && <span className={classes.progress}>Adding {uploadProgress}…</span>}
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
            <Button component={Link} to={`/assistant/${job.id}`} variant="default" leftSection={<IconMessageCircle size={16} />}>
              Open chat
            </Button>
          </Group>
        </div>
        {/* Says why "Screen CVs" is disabled (a tooltip never shows on a disabled button). */}
        {applicants.length > 0 && !job.profile && (
          <div className={classes.hint}>
            Save the job profile in the chat before screening: the CVs are checked against it.
          </div>
        )}
      </header>

      {actionError && <ErrorBanner title="That didn’t work.">{actionError}</ErrorBanner>}
      {uploadResults && <UploadResults results={uploadResults} onClose={() => setUploadResults(null)} />}

      {job.profile && <WeightsCard job={job} onSaved={setJob} disabled={running} />}

      {screening?.run && !running && (screening.weights_changed || screening.new_cvs > 0) && (
        <div className={classes.staleNote} role="status">
          <IconAlertTriangle size={17} />
          <span className={classes.staleText}>
            {screening.weights_changed && 'The weights changed since the last screening. '}
            {screening.new_cvs > 0 && `${screening.new_cvs} new ${screening.new_cvs === 1 ? 'CV' : 'CVs'} arrived since then. `}
            Screen again to update the ranking.
          </span>
          <Button size="xs" variant="default" onClick={startScreening} loading={starting}>
            Screen again
          </Button>
        </div>
      )}
      {running && <ScreeningProgress run={screening.run} />}
      {screening?.run?.status === 'failed' && (
        <ErrorBanner title="Screening stopped." onRetry={startScreening}>
          {screening.run.error} No CVs were lost. Try again.
        </ErrorBanner>
      )}
      {screening?.run?.status === 'completed' && (
        <ScreeningResults data={screening} onViewCv={viewResultCv} viewingId={viewingId} />
      )}

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
              The job is not posted yet.{' '}
              <Anchor component={Link} to={`/assistant/${job.id}`} fz={15} fw={600}>
                Post it from the chat
              </Anchor>{' '}
              so people can apply.
            </Text>
          )}
          <Text fz={14} c="#66717A">
            Received a CV another way? Use <b>Add CV</b> to add it by hand.
          </Text>
        </div>
      ) : (
        <section className={classes.card} aria-label="Applicants">
          <div className={classes.cardTop}>
            <button
              type="button"
              className={classes.collapseHead}
              onClick={() => setApplicantsOpen(!showApplicants)}
              aria-expanded={showApplicants}
            >
              {showApplicants ? <IconChevronDown size={18} /> : <IconChevronRight size={18} />}
              <div>
                <div className={classes.cardTitle}>Applicants</div>
                <div className={classes.cardHint}>
                  {cvCount(job.cvs_received)}
                  {rejected > 0 && ` · ${rejected} ${rejected === 1 ? 'file' : 'files'} refused`} · new
                  CVs arrive every 5 minutes
                </div>
              </div>
            </button>
            <Button
              variant="default"
              size="xs"
              onClick={refresh}
              loading={refreshing}
              leftSection={<IconRefresh size={15} />}
              className={classes.noShrink}
              title="Check for new CVs"
            >
              Refresh
            </Button>
          </div>
          <Collapse expanded={showApplicants}>
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
          </Collapse>
        </section>
      )}

      <ConfirmModal
        opened={Boolean(removing)}
        onClose={() => setRemoving(null)}
        title="Remove this applicant?"
        confirmLabel="Remove"
        onConfirm={remove}
        busy={removeBusy}
      >
        {removing?.full_name || 'This applicant'} and their CV will be deleted from CandiVue. This
        can’t be undone. The answer in the Google Form is not changed.
      </ConfirmModal>
    </div>
  );
}
