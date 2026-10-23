// The candidate pipeline as a board (an addition to the design): one column
// per step after screening (Screened → Shortlisted → Invited → Interviewed
// → Selected), excluded candidates folded away at the end. Read-only: the
// steps move when the interviewer shortlists and invites in the Hiring
// Assistant (with their confirmation) or sends the selection email.
// Clicking a card opens the same candidate panel as the ranking.

import { Avatar, Collapse, UnstyledButton } from '@mantine/core';
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react';
import { useState } from 'react';

import StatusBadge from '../../components/StatusBadge';
import classes from './Pipeline.module.css';
import { pipelineColumns } from './pipelineFormat';

// A step within a column that deserves a word on the card.
const SUB_STEPS = {
  invitation_pending: ['warning', 'Not emailed yet'],
  invitation_failed: ['danger', 'Email failed'],
  in_interview: ['info', 'In interview now'],
};

// One candidate on the board.
function Card({ result, onOpen }) {
  const sub = SUB_STEPS[result.pipeline];
  const name = result.name || result.cv_filename;
  return (
    <UnstyledButton className={classes.card} onClick={() => onOpen(result)} aria-label={`Open ${name}`}>
      <span className={classes.cardTop}>
        <Avatar name={name} color="initials" size={30} radius="xl" />
        <span className={classes.name}>{name}</span>
      </span>
      <span className={classes.meta}>
        {result.rank != null ? <span className={classes.rank}>#{result.rank}</span> : <span>Excluded</span>}
        {result.overall != null && <span className={classes.score}>{Math.round(result.overall)}</span>}
      </span>
      {sub && <StatusBadge tone={sub[0]}>{sub[1]}</StatusBadge>}
    </UnstyledButton>
  );
}

export default function PipelineBoard({ ranked, excluded, onOpen }) {
  const [showExcluded, setShowExcluded] = useState(false);
  const { columns, excluded: left } = pipelineColumns(ranked, excluded);
  const Chevron = showExcluded ? IconChevronDown : IconChevronRight;

  return (
    <section className={classes.wrap} aria-label="Candidate pipeline">
      <div className={classes.board}>
        {columns.map((column) => (
          <div key={column.key} className={`${classes.column} ${classes[`col_${column.key}`]}`}>
            <div className={classes.columnHead}>
              <span>{column.title}</span>
              <span className={classes.count}>{column.cards.length}</span>
            </div>
            <div className={classes.cards}>
              {column.cards.length === 0 ? (
                <span className={classes.empty}>Nobody yet</span>
              ) : (
                column.cards.map((result) => <Card key={result.candidate_id} result={result} onOpen={onOpen} />)
              )}
            </div>
          </div>
        ))}
      </div>
      {left.length > 0 && (
        <div className={classes.excluded}>
          <UnstyledButton className={classes.excludedToggle} onClick={() => setShowExcluded((open) => !open)}>
            <Chevron size={16} />
            Excluded by the mandatory requirements ({left.length})
          </UnstyledButton>
          <Collapse expanded={showExcluded}>
            <div className={classes.excludedCards}>
              {left.map((result) => (
                <Card key={result.candidate_id} result={result} onOpen={onOpen} />
              ))}
            </div>
          </Collapse>
        </div>
      )}
      <p className={classes.note}>
        Candidates move along when you shortlist and invite them in the Hiring Assistant, and when you send the
        selection email.
      </p>
    </section>
  );
}
