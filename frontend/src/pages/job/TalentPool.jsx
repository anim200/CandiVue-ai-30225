// "Past applicants who may fit" on the job page (F11, innovation feature).
// People who applied for another job, agreed to be considered for other
// vacancies, and pass this job's mandatory requirements. The check runs
// after each screening and on "Check again"; a suggestion becomes an
// applicant only when the interviewer clicks "Add to this job".
// Interviewers only (route guard + backend).

import { Button, Loader } from '@mantine/core';
import { IconCircleCheck, IconRefresh, IconUserPlus, IconUsersGroup } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';

import { apiGet, apiPost } from '../../api/client';
import { notifyDone } from '../../components/notify';
import StatusBadge from '../../components/StatusBadge';
import { usePolling } from '../../utils/usePolling';
import { CandidateDrawer } from './ScreeningResults';
import classes from './TalentPool.module.css';

const POLL_MS = 2000; // progress refresh while the check runs
const ACTIVE = ['pending', 'running'];

// "12 Oct 2026": when they applied for the other job.
function day(value) {
  return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

// "4 of 5 requirements met".
function metLine(matches) {
  const met = matches.filter((m) => m.status === 'met').length;
  return `${met} of ${matches.length} requirements met`;
}

// One suggestion: who, where they applied, the score and "Add to this job".
function MatchRow({ match, onOpen, onAdd, adding }) {
  return (
    <div className={classes.row}>
      <button type="button" className={classes.who} onClick={() => onOpen(match)}>
        <span className={classes.name}>{match.name}</span>
        <span className={classes.applied}>
          Applied for {match.applied_for} · {day(match.applied_at)} · {match.outcome_there}
        </span>
      </button>
      <div className={classes.score} title="Overall score for this job (0–100)">
        <b>{match.overall}</b>
        <div className={classes.bar}>
          <div className={classes.fill} style={{ width: `${match.overall}%` }} />
        </div>
      </div>
      <div className={classes.met}>{metLine(match.matches)}</div>
      <div className={classes.action}>
        {match.added_as ? (
          <StatusBadge tone="success" icon={<IconCircleCheck size={13} />}>
            Added
          </StatusBadge>
        ) : (
          <Button size="xs" variant="light" leftSection={<IconUserPlus size={14} />} loading={adding} onClick={() => onAdd(match)}>
            Add to this job
          </Button>
        )}
      </div>
    </div>
  );
}

// The card. onAdded(): reload the applicants; onViewCv(jobId, file): open
// a CV of any job (the suggestion's CV belongs to the job they applied for).
export default function TalentPool({ job, onAdded, onViewCv, viewingId }) {
  const [data, setData] = useState(null); // null = loading
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(false);
  const [addingId, setAddingId] = useState(null);
  const [selected, setSelected] = useState(null); // suggestion in the drawer

  const load = useCallback(async () => {
    try {
      setData(await apiGet(`/jobs/${job.id}/rediscovery`));
    } catch (exc) {
      setError(exc.message);
    }
  }, [job.id]);

  useEffect(() => {
    load();
  }, [load]);

  const running = ACTIVE.includes(data?.run?.status);
  usePolling(load, running, POLL_MS);

  // "Check again": e.g. more people agreed to the talent pool since.
  async function checkAgain() {
    setChecking(true);
    setError(null);
    try {
      setData(await apiPost(`/jobs/${job.id}/rediscovery`));
    } catch (exc) {
      setError(exc.message);
    } finally {
      setChecking(false);
    }
  }

  // Make a suggestion an applicant of this job (their CV is copied).
  async function add(match) {
    setAddingId(match.candidate_id);
    setError(null);
    try {
      await apiPost(`/jobs/${job.id}/rediscovery/${match.candidate_id}/add`);
      notifyDone(`${match.name} added. Screen again to rank them with the others.`);
      await Promise.all([load(), onAdded()]);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setAddingId(null);
    }
  }

  if (!data) return null; // appears once loaded (it is below the main results)

  const { run, matches, pool_size: poolSize } = data;
  return (
    <section className={classes.card} aria-label="Past applicants who may fit">
      <div className={classes.top}>
        <IconUsersGroup size={20} className={classes.icon} />
        <div className={classes.titleBlock}>
          <div className={classes.title}>Past applicants who may fit</div>
          <div className={classes.hint}>
            People who applied for other jobs in the last year and agreed to be considered for other
            vacancies. {poolSize} {poolSize === 1 ? 'person is' : 'people are'} in the talent pool now.
          </div>
        </div>
        <Button
          size="xs"
          variant="default"
          leftSection={<IconRefresh size={15} />}
          onClick={checkAgain}
          loading={checking}
          disabled={running}
          className={classes.noShrink}
        >
          Check again
        </Button>
      </div>

      {error && <div className={classes.error}>{error}</div>}
      {running && (
        <div className={classes.status} role="status">
          <Loader size={14} />
          Checking the talent pool{run.total ? ` · ${run.processed} of ${run.total}` : '…'}
        </div>
      )}
      {run?.status === 'failed' && (
        <div className={classes.error}>The last check stopped: {run.error} Try “Check again”.</div>
      )}
      {!run && <div className={classes.status}>Not checked yet. The talent pool is checked after each screening.</div>}
      {run?.status === 'completed' && matches.length === 0 && (
        <div className={classes.status}>
          No past applicant fits this job yet. A suggestion must meet every mandatory requirement and score at
          least 50.
        </div>
      )}
      {matches.length > 0 && !running && (
        <>
          {matches.map((match) => (
            <MatchRow
              key={match.candidate_id}
              match={match}
              onOpen={setSelected}
              onAdd={add}
              adding={addingId === match.candidate_id}
            />
          ))}
          <div className={classes.note}>
            Suggestions only, scored with this job’s requirements and weights. Adding someone makes them an
            applicant here; screen again to rank them with the others.
          </div>
        </>
      )}

      {/* Every suggestion passed the gate, so the drawer shows its breakdown. */}
      <CandidateDrawer
        result={selected && { ...selected, outcome: 'ranked' }}
        heading={selected && `Applied for ${selected.applied_for} · ${selected.outcome_there}`}
        onClose={() => setSelected(null)}
        onViewCv={() => onViewCv(selected.applied_job_id, { id: selected.candidate_id, cv_filename: selected.cv_filename })}
        viewing={viewingId === selected?.candidate_id}
      />
    </section>
  );
}
