// CV screening results on the job page (design: CV Screening Results.dc.html:
// ScreeningProgress, RankingTable, CandidateDrawer with ScoreBreakdownCard and
// RequirementList, ExcludedList, UnreadableList). Interviewers only.

import { Button, Collapse, Drawer } from '@mantine/core';
import {
  IconAlertTriangle,
  IconCalendarQuestion,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconFileAlert,
  IconFileText,
  IconInfoCircle,
  IconProgress,
  IconScan,
  IconX,
} from '@tabler/icons-react';
import { useState } from 'react';

import { WEIGHT_FIELDS } from './WeightsCard';
import classes from './Screening.module.css';

const STATUS_STYLE = {
  met: { text: 'Met', icon: IconCheck, className: classes.statusMet },
  partial: { text: 'Partly met', icon: IconProgress, className: classes.statusPartial },
  unmet: { text: 'Not met', icon: IconX, className: classes.statusUnmet },
};
const SECTION_NAMES = {
  experience: 'Work history',
  skills: 'Skills',
  education: 'Education',
  certifications: 'Certifications',
  projects: 'Projects',
  summary: 'Summary',
  intro: 'Header',
};

// "technical 35%, experience 30%, ..." for the table header.
export function weightsLine(weights) {
  const short = { skills: 'technical', experience: 'experience', qualifications: 'qualifications', ats: 'ATS match' };
  return WEIGHT_FIELDS.map(([key]) => `${short[key]} ${weights[key]}%`).join(', ');
}

// Striped progress while a run works (design 2a).
export function ScreeningProgress({ run }) {
  const total = run.total || 0;
  const share = total ? Math.round((100 * run.processed) / total) : 0;
  return (
    <div className={classes.progressCard} role="status">
      <div className={classes.progressTop}>
        <div className={classes.cardTitle}>Screening CVs</div>
        <div className={classes.progressCount}>{total ? `${run.processed} of ${total} CVs` : 'Starting…'}</div>
      </div>
      <div className={classes.bar}>
        <div className={classes.barFill} style={{ width: `${Math.max(share, 4)}%` }} />
      </div>
      <div className={classes.muted}>
        Reading CVs, checking mandatory requirements and scoring each one. You can leave this page;
        screening continues in the background. The ranking appears when all CVs are screened, so
        candidates are compared on the same basis.
      </div>
    </div>
  );
}

// One requirement in the drawer: status, evidence and where it was found.
function RequirementRow({ match }) {
  const style = STATUS_STYLE[match.status];
  const Icon = style.icon;
  let how = null;
  if (match.decided_by === 'also_counts') how = `“${match.matched_name}” counts for this requirement.`;
  if (match.decided_by === 'related') how = `“${match.matched_name}” is a close substitute, so partly met.`;
  if (match.decided_by === 'meaning' && match.evidence)
    how = `Closest line by meaning (similarity ${match.similarity}).`;
  if (match.decided_by === 'local_model')
    how = 'Not found by the rules; the local AI model found this line when checking again before excluding.';
  return (
    <div className={classes.requirement}>
      <div className={classes.requirementTop}>
        <div className={classes.requirementName}>
          {match.requirement} <span className={classes.levelTag}>{match.level}</span>
        </div>
        <span className={`${classes.statusBadge} ${style.className}`}>
          <Icon size={13} />
          {style.text}
        </span>
      </div>
      <div className={classes.evidence}>
        {match.evidence ? `“${match.evidence}”` : 'Not found in the CV.'}
        {how && <span className={classes.how}> {how}</span>}
      </div>
      {match.section && <span className={classes.sourceChip}>CV · {SECTION_NAMES[match.section] ?? match.section}</span>}
    </div>
  );
}

// The side panel for one candidate (design CandidateDrawer).
function CandidateDrawer({ result, rankedCount, onClose, onViewCv, viewing }) {
  const met = result?.matches.filter((m) => m.status === 'met').length ?? 0;
  return (
    <Drawer
      opened={Boolean(result)}
      onClose={onClose}
      position="right"
      size={500}
      withCloseButton={false}
      overlayProps={{ backgroundOpacity: 0.28, color: '#1A2227' }}
      transitionProps={{ transition: 'slide-left', duration: 280, timingFunction: 'cubic-bezier(.2,.8,.2,1)' }}
      classNames={{ body: classes.drawerBody }}
    >
      {result && (
        <>
          <div className={classes.drawerHead}>
            <div className={classes.drawerTitle}>
              <div className={classes.drawerRank}>
                {result.outcome === 'ranked' ? `Rank ${result.rank} of ${rankedCount}` : 'Excluded'}
              </div>
              {result.scanned && (
                <div className={classes.scannedLine}>
                  <IconScan size={13} /> Scanned CV, read with text recognition
                </div>
              )}
              {/* Drawer.Title also names the dialog for screen readers. */}
              <Drawer.Title className={classes.drawerName}>{result.name || 'Name not found'}</Drawer.Title>
              {result.email && <div className={classes.muted}>{result.email}</div>}
            </div>
            <div className={classes.drawerActions}>
              <Button variant="default" size="xs" leftSection={<IconFileText size={15} />} loading={viewing} onClick={() => onViewCv(result)}>
                View CV
              </Button>
              <button type="button" className={classes.closeButton} onClick={onClose} aria-label="Close">
                <IconX size={18} />
              </button>
            </div>
          </div>
          <div className={classes.drawerScroll}>
            {result.years_unknown && (
              <div className={classes.checkNote}>
                <IconCalendarQuestion size={18} /> Years of experience could not be read from this CV (no job
                dates or stated years), so they were not used to exclude. Please check the CV.
              </div>
            )}
            {result.outcome === 'ranked' ? (
              <div className={classes.breakdown}>
                <div className={classes.breakdownTop}>
                  <div className={classes.cardTitle}>Score breakdown</div>
                  <div className={classes.bigScore}>
                    {result.overall}
                    <span> / 100 overall</span>
                  </div>
                </div>
                {WEIGHT_FIELDS.map(([key]) => {
                  const dim = result.dimensions[key];
                  return (
                    <div key={key} className={classes.dimension}>
                      <div className={classes.dimensionTop}>
                        <span>
                          <b>{dim.label}</b> <span className={classes.weightNote}>· weight {dim.weight}%</span>
                        </span>
                        <b className={classes.num}>{dim.score}</b>
                      </div>
                      <div className={classes.dimBar}>
                        <div className={classes.dimFill} style={{ width: `${dim.score}%` }} />
                      </div>
                      <div className={classes.muted}>{dim.reason}</div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className={classes.excludedNote}>
                <IconAlertTriangle size={18} /> {result.summary}
              </div>
            )}
            <div className={classes.requirements}>
              <div className={classes.breakdownTop}>
                <div className={classes.cardTitle}>Requirements</div>
                <div className={classes.small}>
                  {met} of {result.matches.length} met
                </div>
              </div>
              {result.matches.map((match) => (
                <RequirementRow key={match.requirement} match={match} />
              ))}
            </div>
          </div>
        </>
      )}
    </Drawer>
  );
}

// The ranking, excluded and unreadable lists, and the drawer.
export default function ScreeningResults({ data, onViewCv, viewingId }) {
  const [selected, setSelected] = useState(null);
  const [excludedOpen, setExcludedOpen] = useState(true);
  const { run, ranked, excluded, unreadable } = data;
  const total = ranked.length + excluded.length + unreadable.length;

  return (
    <>
      <div className={classes.info}>
        <IconInfoCircle size={18} />
        Scores support your decision. CandiVue never rejects or hires anyone automatically.
      </div>

      <section className={classes.card} aria-label="Ranked candidates">
        <div className={classes.cardTop}>
          <div className={classes.cardTitle}>Ranked candidates</div>
          <div className={classes.small}>
            {ranked.length} {ranked.length === 1 ? 'candidate' : 'candidates'} met every mandatory requirement.
            Weights: {weightsLine(run.weights)}.
            {ranked.some((r) => r.scanned) && ' The scan icon marks CVs read from an image with text recognition.'}
            {ranked.some((r) => r.years_unknown) && ' The calendar icon marks CVs whose years of experience could not be read: please check them.'}
          </div>
        </div>
        {ranked.length === 0 ? (
          <div className={classes.emptyRow}>No candidate met every mandatory requirement.</div>
        ) : (
          <>
            <div className={classes.head}>
              <div>Rank</div>
              <div>Candidate</div>
              <div>Overall (0–100)</div>
              <div className={classes.dimCol}>Technical skills</div>
              <div className={classes.dimCol}>Relevant experience</div>
              <div className={classes.dimCol}>Qualifi­cations</div>
              <div className={classes.dimCol}>ATS CV–JD match</div>
              <div />
            </div>
            {ranked.map((result) => (
              <button
                type="button"
                key={result.candidate_id}
                className={`${classes.row} ${selected?.candidate_id === result.candidate_id ? classes.rowSelected : ''}`}
                onClick={() => setSelected(result)}
              >
                <div className={classes.rank}>{result.rank}</div>
                <div className={classes.name}>
                  <span className={classes.nameText}>{result.name || result.cv_filename}</span>
                  {result.scanned && (
                    <span className={classes.scanChip} title="Scanned CV: read from an image with text recognition. Worth a quick check against the original.">
                      <IconScan size={12} />
                    </span>
                  )}
                  {result.years_unknown && (
                    <span className={classes.checkChip} title="Years of experience could not be read from this CV. Please check it.">
                      <IconCalendarQuestion size={12} />
                    </span>
                  )}
                </div>
                <div className={classes.overall}>
                  <b className={classes.num}>{result.overall}</b>
                  <div className={classes.miniBar}>
                    <div className={classes.miniFill} style={{ width: `${result.overall}%` }} />
                  </div>
                </div>
                {WEIGHT_FIELDS.map(([key]) => (
                  <div key={key} className={`${classes.num} ${classes.dimCol}`}>
                    {result.dimensions[key]?.score}
                  </div>
                ))}
                <IconChevronRight size={16} className={classes.chevron} />
              </button>
            ))}
          </>
        )}
      </section>

      {excluded.length > 0 && (
        <section className={classes.card} aria-label="Excluded candidates">
          <button type="button" className={classes.collapseHead} onClick={() => setExcludedOpen((open) => !open)}>
            {excludedOpen ? <IconChevronDown size={18} /> : <IconChevronRight size={18} />}
            <div>
              <div className={classes.cardTitle}>
                Excluded: failed a mandatory requirement <span className={classes.count}>({excluded.length})</span>
              </div>
              <div className={classes.small}>Not ranked. You can still open each CV and decide for yourself.</div>
            </div>
          </button>
          <Collapse expanded={excludedOpen}>
            <div className={classes.excludedHead}>
              <div>Candidate</div>
              <div>Reason</div>
            </div>
            {excluded.map((result) => (
              <button type="button" key={result.candidate_id} className={classes.excludedRow} onClick={() => setSelected(result)}>
                <div className={classes.nameText}>{result.name || result.cv_filename}</div>
                <div className={classes.reason}>
                  <IconX size={15} className={classes.reasonIcon} />
                  {result.summary}
                </div>
              </button>
            ))}
          </Collapse>
        </section>
      )}

      {unreadable.length > 0 && (
        <section className={classes.unreadable} aria-label="Unreadable CVs">
          <IconFileAlert size={20} className={classes.unreadableIcon} />
          <div>
            <div className={classes.cardTitle}>
              {unreadable.length} {unreadable.length === 1 ? 'CV' : 'CVs'} could not be read
            </div>
            {unreadable.map((result) => (
              <div key={result.candidate_id} className={classes.muted}>
                <b>{result.name || result.cv_filename}</b>: {result.summary} The other{' '}
                {total - unreadable.length} CVs were screened normally.
              </div>
            ))}
          </div>
        </section>
      )}

      <CandidateDrawer
        result={selected}
        rankedCount={ranked.length}
        onClose={() => setSelected(null)}
        onViewCv={onViewCv}
        viewing={viewingId === selected?.candidate_id}
      />
    </>
  );
}
