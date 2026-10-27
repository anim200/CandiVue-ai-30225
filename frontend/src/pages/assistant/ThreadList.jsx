// Left column: one chat thread per job, with where each job is
// (design: ThreadList). "+" starts a new job.

import { Loader, Tooltip } from '@mantine/core';
import { IconEye, IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';

import classes from './Assistant.module.css';
import { STAGES } from './labels';

// The list of job threads; the open one is highlighted.
export default function ThreadList({ jobs, activeId, onNewJob, creating, className = '' }) {
  return (
    <aside className={`${classes.threads} ${className}`}>
      <div className={classes.threadsHead}>
        <div className={classes.threadsTitle}>One thread per job</div>
        <Tooltip label="New job">
          <button type="button" className={classes.newThread} onClick={onNewJob} aria-label="New job">
            {creating ? <Loader size={14} /> : <IconPlus size={16} />}
          </button>
        </Tooltip>
      </div>
      <div className={classes.threadItems}>
        {jobs.map((job) => {
          const stage = STAGES[job.stage] ?? STAGES.drafting_profile;
          const active = job.id === activeId;
          return (
            <Link
              key={job.id}
              to={`/assistant/${job.id}`}
              className={`${classes.thread} ${active ? classes.threadActive : ''}`}
              aria-current={active ? 'page' : undefined}
            >
              <span className={classes.threadName}>{job.title}</span>
              <span className={`${classes.threadStage} ${stage.attention ? classes.attention : ''}`}>
                {stage.attention && <IconEye size={13} />}
                {stage.text}
              </span>
            </Link>
          );
        })}
      </div>
    </aside>
  );
}
