// One job's page (design: CV Screening Results.dc.html). Header with
// "Screen CVs", the scoring weights, the screening run (progress, ranking,
// excluded and unreadable CVs, candidate drawer), past applicants who may
// fit (talent pool, F11) and the applicants: the CVs the CV Collector took
// from the job's Google Form, plus any added by hand ("Add CV"). "Delete
// job" removes the job with everything about it, after a confirmation.
// Interviewers only (route guard + backend).

import { Anchor, Button, Checkbox, Collapse, FileButton, Group, Loader, Modal, Text } from '@mantine/core';
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
  IconUserPlus,
  IconUsersGroup,
  IconX,
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { apiDelete, apiGet, apiGetFile, apiPost, apiPut, apiUpload } from '../../api/client';
import ConfirmModal, { POP_TRANSITION } from '../../components/ConfirmModal';
import { ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyDone, notifyWarning } from '../../components/notify';
import StatusBadge from '../../components/StatusBadge';
import { STAGES } from '../assistant/labels';
import classes from './JobPage.module.css';
import ScreeningResults, { ScreeningProgress } from './ScreeningResults';
import TalentPool from './TalentPool';
import WeightsCard from './WeightsCard';

const POLL_MS = 2000; // progress refresh while screening runs
const ACTIVE = ['pending', 'running'];
const DELETE_TIMEOUT_MS = 120000; // cancels interviews and removes the job post

// "7 Oct, 15:09": when a CV arrived, a run finished or applications close.
function dateTime(value) {
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

// "1 applicant" / "3 applicants".
function plural(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`;
}

// What "Delete job" will remove, for the confirmation dialog.
function DeleteJobText({ job, applicants }) {
  const what =
    applicants > 0
      ? `its ${plural(applicants, 'applicant')} and their CVs, interviews, transcripts and reports.`
      : 'its profile and chat.';
  const one = job.interview_count === 1;
  const interviews = job.interview_count
    ? ` ${plural(job.interview_count, 'scheduled interview')} will be cancelled: ${one ? 'the candidate is' : 'the candidates are'} emailed and the calendar ${one ? 'event' : 'events'} removed.`
    : '';
  const post = job.job_board_post_url ? ' The job post is removed from the job board.' : '';
  return (
    <>
      <b>{job.title}</b> will be deleted with {what}
      {interviews}
      {post} This can’t be undone.
    </>
  );
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
function AddCvButton({ onFiles, busy, disabled, variant = 'default' }) {
  return (
    <FileButton
      onChange={onFiles}
      accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      multiple
      disabled={disabled}
    >
      {(props) => (
        <Button {...props} variant={variant} loading={busy} disabled={disabled} leftSection={<IconUpload size={16} />}>
          Add CV
        </Button>
      )}
    </FileButton>
  );
}

// After choosing files: did these applicants agree to the talent pool
// (F11)? The Google Form asks applicants; for a CV received another way
// the interviewer says so. Unticked by default: no consent, no matching.
function AddCvDialog({ files, onClose, onAdd }) {
  const [inPool, setInPool] = useState(false);
  const what = files.length === 1 ? '1 CV' : `${files.length} CVs`;
  return (
    <Modal
      opened
      onClose={onClose}
      size={460}
      radius="md"
      centered
      transitionProps={POP_TRANSITION}
      title={
        <Text fz={18} fw={600}>
          Add {what}
        </Text>
      }
    >
      <Text fz={15} c="#48535B" lh={1.55}>
        Each file is checked and added to this job’s applicants.
      </Text>
      <Checkbox
        mt="md"
        checked={inPool}
        onChange={(event) => setInPool(event.currentTarget.checked)}
        label="They agreed to be considered for other vacancies (talent pool)"
        description="Tick only if every applicant said yes. You can remove anyone from the talent pool later."
      />
      <Group justify="flex-end" gap={8} mt="lg">
        <Button variant="default" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={() => onAdd(files, inPool)}>Add {what}</Button>
      </Group>
    </Modal>
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

// One applicant row: who, when, which file, status and actions (view the
// CV, talent pool in or out, remove).
function ApplicantRow({ applicant, onView, onTalentPool, onRemove, viewing }) {
  const received = applicant.status !== 'rejected';
  return (
    <div className={classes.item}>
      <div className={classes.row}>
        <div className={classes.who}>
          <span className={classes.name}>{applicant.full_name || 'Name not given'}</span>
          <span className={classes.email}>
            {applicant.source === 'upload' && <span className={classes.source}>Added by hand</span>}
            {applicant.source === 'rediscovered' && (
              <span className={classes.source} title={`Applied for ${applicant.rediscovered_from ?? 'another job'}`}>
                From talent pool
              </span>
            )}
            {applicant.open_to_other_roles && <span className={classes.poolChip}>Talent pool</span>}
            {applicant.email || (applicant.source === 'upload' ? '' : '—')}
          </span>
        </div>
        <div className={classes.when}>{dateTime(applicant.received_at)}</div>
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
          {received && (
            <button
              type="button"
              className={`${classes.poolButton} ${applicant.open_to_other_roles ? classes.poolOn : ''}`}
              title={
                applicant.open_to_other_roles
                  ? 'In the talent pool. Click to remove (e.g. they asked to be left out).'
                  : 'Add to the talent pool (only if they agreed to other vacancies).'
              }
              aria-pressed={applicant.open_to_other_roles}
              aria-label={`Talent pool: ${applicant.full_name || 'applicant'}`}
              onClick={() => onTalentPool(applicant, !applicant.open_to_other_roles)}
            >
              {applicant.open_to_other_roles ? <IconUsersGroup size={16} /> : <IconUserPlus size={16} />}
            </button>
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
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [applicants, setApplicants] = useState(null); // null = loading
  const [failed, setFailed] = useState(null); // message, or null
  const [viewingId, setViewingId] = useState(null);
  const [removing, setRemoving] = useState(null); // applicant to confirm
  const [removeBusy, setRemoveBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [pendingFiles, setPendingFiles] = useState(null); // chosen, not sent yet
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState(null); // last "Add CV" outcome
  const [uploadProgress, setUploadProgress] = useState(null); // "3 of 19"
  const [screening, setScreening] = useState(null); // latest run and results
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [applicantsOpen, setApplicantsOpen] = useState(null); // null = automatic
  const [deleting, setDeleting] = useState(false); // confirmation open
  const [deleteBusy, setDeleteBusy] = useState(false);
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

  // Show an applicant's CV (of this job, or of the job a talent-pool
  // suggestion applied for).
  async function view(applicant, fromJob = jobId) {
    setViewingId(applicant.id);
    setActionError(null);
    try {
      await openCv(fromJob, applicant);
    } catch (error) {
      setActionError(error.message);
    } finally {
      setViewingId(null);
    }
  }

  // Send the chosen files one at a time (small requests, progress shown);
  // each file is added or refused on its own, and one failure never stops
  // the rest. inPool: the applicants agreed to the talent pool.
  async function addCvs(files, inPool) {
    setPendingFiles(null);
    setUploading(true);
    setActionError(null);
    setUploadResults(null);
    const results = [];
    for (const [index, file] of files.entries()) {
      setUploadProgress(`${index + 1} of ${files.length}`);
      const form = new FormData();
      form.append('files', file);
      form.append('open_to_other_roles', String(inPool));
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

  // Put an applicant in the talent pool or take them out (their choice).
  async function setTalentPool(applicant, inPool) {
    setActionError(null);
    const who = applicant.full_name || 'The applicant';
    try {
      await apiPut(`/jobs/${jobId}/cvs/${applicant.id}/talent-pool`, { open_to_other_roles: inPool });
      notifyDone(inPool ? `${who} is in the talent pool` : `${who} left the talent pool`);
      await load();
    } catch (error) {
      setActionError(error.message);
    }
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

  // Delete the job (confirmed), then go back to the jobs list. What could
  // not be done (e.g. the job post) is shown so it can be done by hand.
  async function deleteJob() {
    setDeleteBusy(true);
    setActionError(null);
    try {
      const result = await apiDelete(`/jobs/${jobId}`, DELETE_TIMEOUT_MS);
      const cancelled = result.interviews_cancelled;
      notifyDone(`Deleted ${job.title}${cancelled ? ` and cancelled ${plural(cancelled, 'interview')}` : ''}`);
      if (result.problems.length) notifyWarning('Please finish by hand', result.problems.join(' '));
      navigate('/jobs');
    } catch (error) {
      setActionError(error.message);
      setDeleting(false);
      setDeleteBusy(false);
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
  // After the closing date no CVs are added (the backend refuses them too).
  const closed = Boolean(job.applications_close_at) && new Date(job.applications_close_at) <= new Date();
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
                  <span>Last screened {dateTime(screening.run.finished_at)}</span>
                </>
              )}
              {job.applications_close_at && (
                <>
                  <span className={classes.dot}>·</span>
                  <span>
                    {closed ? 'Applications closed' : 'Applications close'} {dateTime(job.applications_close_at)}
                  </span>
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
            <AddCvButton onFiles={(files) => files?.length && setPendingFiles(files)} busy={uploading} disabled={closed} />
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
            <Button
              variant="subtle"
              color="#B03A2E"
              leftSection={<IconTrash size={16} />}
              onClick={() => setDeleting(true)}
              disabled={running}
              title={running ? 'Wait until the screening finishes' : undefined}
            >
              Delete job
            </Button>
          </Group>
        </div>
        {/* Says why "Screen CVs" is disabled (a tooltip never shows on a disabled button). */}
        {applicants.length > 0 && !job.profile && (
          <div className={classes.hint}>
            Save the job profile in the chat before screening: the CVs are checked against it.
          </div>
        )}
        {closed && (
          <div className={classes.hint}>
            Applications are closed, so no more CVs are added. Change the closing date in the chat to
            reopen them.
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
      {/* A finished screening starts a new talent-pool check: the new key reloads the card. */}
      {job.profile && (
        <TalentPool
          key={screening?.run?.finished_at ?? 'never'}
          job={job}
          onAdded={load}
          onViewCv={(fromJob, file) => view(file, fromJob)}
          viewingId={viewingId}
        />
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
                onTalentPool={setTalentPool}
                onRemove={setRemoving}
              />
            ))}
          </Collapse>
        </section>
      )}

      {pendingFiles && <AddCvDialog files={pendingFiles} onClose={() => setPendingFiles(null)} onAdd={addCvs} />}

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

      <ConfirmModal
        opened={deleting}
        onClose={() => setDeleting(false)}
        title="Delete this job?"
        confirmLabel="Delete job"
        onConfirm={deleteJob}
        busy={deleteBusy}
      >
        <DeleteJobText job={job} applicants={applicants.length} />
      </ConfirmModal>
    </div>
  );
}
