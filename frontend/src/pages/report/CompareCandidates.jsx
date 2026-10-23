// Compare candidates (design: Assessment Report.dc.html, 1b and 2f): up to
// three assessed candidates for the same job side by side, one row per
// dimension. Each value comes from the same reports as the individual pages.

import { Button, CloseButton, Menu } from '@mantine/core';
import { IconPlus, IconUsers } from '@tabler/icons-react';
import { Link } from 'react-router';

import { EmptyState } from '../../components/Feedback';
import classes from './Report.module.css';
import { compareRows } from './reportFormat';

export const MAX_COMPARED = 3;

export default function CompareCandidates({ rows, chosen, onChoose, jobTitle }) {
  const assessed = rows.filter((row) => row.report?.content?.position);
  if (assessed.length < 2) {
    return (
      <EmptyState icon={IconUsers} title="Nothing to compare yet">
        Comparison needs at least two assessed candidates for this job.{' '}
        {assessed.length === 1 && `${assessed[0].candidate_name} is the only one so far.`}
      </EmptyState>
    );
  }
  const compared = assessed.filter((row) => chosen.includes(row.interview_id));
  const others = assessed.filter((row) => !chosen.includes(row.interview_id));
  const table = compareRows(compared);
  const columns = { gridTemplateColumns: `180px repeat(${compared.length}, minmax(0, 1fr))` };
  const drafts = compared.filter((row) => row.report.review_status !== 'approved');

  return (
    <div className={classes.compare}>
      <div className={classes.compareBar}>
        <span className={classes.compareLabel}>Comparing</span>
        {compared.map((row) => (
          <span key={row.interview_id} className={classes.person}>
            {row.candidate_name}
            {compared.length > 2 && (
              <CloseButton
                size="xs"
                onClick={() => onChoose(chosen.filter((id) => id !== row.interview_id))}
                aria-label={`Remove ${row.candidate_name} from the comparison`}
              />
            )}
          </span>
        ))}
        {compared.length < MAX_COMPARED && others.length > 0 && (
          <Menu position="bottom-start">
            <Menu.Target>
              <Button variant="subtle" size="compact-sm" leftSection={<IconPlus size={14} />}>
                Add
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              {others.map((row) => (
                <Menu.Item key={row.interview_id} onClick={() => onChoose([...chosen, row.interview_id])}>
                  {row.candidate_name}
                </Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
        )}
        <span className={classes.note}>Up to {MAX_COMPARED} assessed candidates for {jobTitle}</span>
      </div>
      <div className={classes.compareScroll}>
        <div className={classes.compareTable} role="table">
          <div className={`${classes.compareRow} ${classes.compareHead}`} style={columns} role="row">
            <div role="columnheader">Dimension</div>
            {compared.map((row) => (
              <div key={row.interview_id} role="columnheader">
                <Link to={`/interviews/${row.interview_id}/report`}>{row.candidate_name}</Link>
              </div>
            ))}
          </div>
          {table.map((line) => (
            <div
              key={line.label}
              className={`${classes.compareRow} ${line.head ? classes.compareFirst : ''}`}
              style={columns}
              role="row"
            >
              <div className={line.sub ? classes.subLabel : classes.rowLabel} role="rowheader">
                {line.label}
              </div>
              {line.cells.map((cell, index) => (
                <div key={compared[index].interview_id} role="cell">
                  {cell.kind === 'bar' && cell.value != null ? (
                    <div className={classes.cellBar}>
                      <div className={classes.scoreTrack}>
                        <div className={classes.scoreFill} style={{ width: `${cell.value}%` }} />
                      </div>
                      <b>{cell.value}</b>
                    </div>
                  ) : (
                    cell.value ?? '—'
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className={classes.note}>
        Each value comes from the candidate’s own report.
        {drafts.length > 0 &&
          ` ${drafts.map((row) => row.candidate_name).join(', ')}: still waiting for review; treat as a draft.`}
      </div>
    </div>
  );
}
