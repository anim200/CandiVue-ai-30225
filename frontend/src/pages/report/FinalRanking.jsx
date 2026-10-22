// The final ranking on the Reports page (§4B-15 f): the candidates of one
// job whose assessment report the interviewer approved, ranked by the
// overall score (CV + interview, the same number as in the report; equal
// candidates share a rank). The interviewer compares up to three of them
// side by side and decides whom to send the selection email; nothing is
// sent automatically. Interviews that are not ranked yet are listed with
// the reason (report being prepared, waiting for review, ...).

import { Button, Checkbox, Tooltip } from '@mantine/core';
import { IconMailCheck, IconSend, IconTrophy, IconUsers } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';

import StatusBadge from '../../components/StatusBadge';
import CompareCandidates, { MAX_COMPARED } from './CompareCandidates';
import classes from './FinalRanking.module.css';
import { identityWarning } from './reportFormat';
import { SelectionEmailModal } from './SelectionEmail';

// The identity check result (F7) as a small badge.
const IDENTITY = {
  matched: ['success', 'Photo match'],
  not_confirmed: ['warning', 'Identity not confirmed'],
  no_match: ['danger', 'Different person'],
  other_applicant: ['danger', 'Different person'],
  failed: ['warning', 'Check-in failed'],
  declined: ['neutral', 'Face check skipped'],
  no_photo: ['neutral', 'No photo compared'],
  waiting: ['neutral', 'Not checked in'],
};

function IdentityBadge({ identity }) {
  const shown = identity && IDENTITY[identity.state];
  if (!shown) return null;
  return (
    <Tooltip label={identity.text} withArrow multiline w={260}>
      <span>
        <StatusBadge tone={shown[0]}>
          {shown[1]}
          {identity.score != null && ` · ${identity.score}%`}
        </StatusBadge>
      </span>
    </Tooltip>
  );
}

// One score cell: the number, or a dash.
function Score({ value, strong }) {
  if (value == null) return <span className={classes.none}>—</span>;
  return strong ? <b className={classes.overall}>{value}</b> : <span>{value}</span>;
}

export default function FinalRanking({ rows, jobTitle, onChanged }) {
  const [compared, setCompared] = useState([]);
  const [comparing, setComparing] = useState(false);
  const [emailFor, setEmailFor] = useState(null); // the row whose email is open
  const ranked = rows.filter((row) => row.rank != null).sort((a, b) => a.rank - b.rank);
  const waiting = rows.filter((row) => row.rank == null);

  // Tick or untick a candidate for the comparison (at most MAX_COMPARED).
  function toggle(id) {
    setCompared((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id].slice(-MAX_COMPARED)));
  }

  return (
    <section className={classes.card} aria-labelledby="final-ranking">
      <div className={classes.head}>
        <div>
          <h2 id="final-ranking" className={classes.title}>
            <IconTrophy size={18} /> Final ranking
          </h2>
          <p className={classes.lead}>
            Candidates with an approved report, by the overall score (CV and interview). You decide whom to select.
          </p>
        </div>
        {ranked.length >= 2 && (
          <Button
            variant="light"
            leftSection={<IconUsers size={16} />}
            disabled={compared.length < 2}
            onClick={() => setComparing((open) => !open)}
          >
            {comparing ? 'Hide comparison' : `Compare (${compared.length})`}
          </Button>
        )}
      </div>

      {ranked.length === 0 ? (
        <p className={classes.empty}>
          No candidate is ranked yet: approve an assessment report to rank its candidate here.
        </p>
      ) : (
        <div className={classes.table} role="table" aria-label="Final ranking">
          <div className={`${classes.row} ${classes.header}`} role="row">
            <span role="columnheader">#</span>
            <span role="columnheader">Candidate</span>
            <span role="columnheader">Overall</span>
            <span role="columnheader">CV</span>
            <span role="columnheader">Interview</span>
            <span role="columnheader">Compare</span>
            <span role="columnheader" aria-label="Actions" />
          </div>
          {ranked.map((row) => {
            const content = row.report.content;
            const blocked = !row.selected_at && !row.has_email ? 'This candidate has no email address.' : null;
            return (
              <div key={row.interview_id} className={classes.row} role="row">
                <span className={classes.rank} role="cell">
                  {row.rank}
                </span>
                <span className={classes.who} role="cell">
                  <Link to={`/interviews/${row.interview_id}/report`} className={classes.name}>
                    {row.candidate_name}
                  </Link>
                  <span className={classes.position}>{content.position?.label}</span>
                  <span className={classes.badges}>
                    <IdentityBadge identity={row.identity} />
                    {row.selected_at && (
                      <StatusBadge tone="success" icon={<IconMailCheck size={13} />}>
                        Selected
                      </StatusBadge>
                    )}
                  </span>
                </span>
                <span role="cell" data-label="Overall">
                  <Score value={content.position?.score} strong />
                </span>
                <span role="cell" data-label="CV">
                  <Score value={content.components?.cv?.overall} />
                </span>
                <span role="cell" data-label="Interview">
                  <Score value={content.components?.interview?.overall} />
                </span>
                <span role="cell">
                  <Checkbox
                    aria-label={`Compare ${row.candidate_name}`}
                    label={<span className={classes.compareLabel}>Compare</span>}
                    checked={compared.includes(row.interview_id)}
                    onChange={() => toggle(row.interview_id)}
                  />
                </span>
                <span role="cell" className={classes.action}>
                  {row.selected_at ? (
                    <span className={classes.sent}>Email sent</span>
                  ) : (
                    <Tooltip label={blocked} disabled={!blocked} withArrow>
                      <span>
                        <Button
                          size="xs"
                          variant="light"
                          leftSection={<IconSend size={14} />}
                          disabled={Boolean(blocked)}
                          onClick={() => setEmailFor(row)}
                        >
                          Send selection email
                        </Button>
                      </span>
                    </Tooltip>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {comparing && compared.length >= 2 && (
        <div className={classes.compare}>
          <CompareCandidates
            rows={ranked}
            chosen={compared}
            onChoose={(ids) => setCompared(ids.slice(0, MAX_COMPARED))}
            jobTitle={jobTitle}
          />
        </div>
      )}

      {waiting.length > 0 && (
        <div className={classes.waiting}>
          <h3 className={classes.subTitle}>Not ranked yet</h3>
          <ul>
            {waiting.map((row) => (
              <li key={row.interview_id}>
                <Link to={`/interviews/${row.interview_id}/report`}>{row.candidate_name}</Link>
                <span>{row.not_ranked}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {emailFor && (
        <SelectionEmailModal
          interviewId={emailFor.interview_id}
          candidateName={emailFor.candidate_name}
          identityWarning={identityWarning(emailFor.identity)}
          onClose={() => setEmailFor(null)}
          onSent={() => {
            setEmailFor(null);
            onChanged();
          }}
        />
      )}
    </section>
  );
}
