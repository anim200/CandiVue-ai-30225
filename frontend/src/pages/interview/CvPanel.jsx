// The candidate's CV beside the call (interviewer only, N9): the screening
// result (rank, overall score, the four scores), each job requirement with
// the CV line that showed it, roles, degree, certificates and skills, and the
// CV itself ("Preview CV" shows a PDF inside the page; a Word file is
// downloaded). The file is loaded with the login token as a Blob, so the
// link never works for anyone else.

import { Button, Modal, Tooltip } from '@mantine/core';
import {
  IconCheck,
  IconChevronsLeft,
  IconDownload,
  IconExternalLink,
  IconEye,
  IconProgress,
  IconShieldCheck,
  IconX,
} from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import { apiGet, apiGetFile } from '../../api/client';
import { ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyError } from '../../components/notify';
import classes from './RoomPanels.module.css';

const STATUS = {
  met: { icon: IconCheck, text: 'Met', className: classes.met },
  partial: { icon: IconProgress, text: 'Partly met', className: classes.partly },
  unmet: { icon: IconX, text: 'Not met', className: classes.unmet },
};
const DIMENSIONS = ['skills', 'experience', 'qualifications', 'ats'];

// "2020-01" → "Jan 2020"; the current month reads "now".
function monthText(value) {
  if (!value) return '';
  const [year, month] = value.split('-').map(Number);
  const date = new Date(year, month - 1);
  const now = new Date();
  if (year === now.getFullYear() && month === now.getMonth() + 1) return 'now';
  return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });
}

// Initials for the avatar.
function initials(name) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

// The CV file as a Blob URL (freed when no longer needed).
async function cvUrl(cv) {
  const file = await apiGetFile(`/jobs/${cv.job_id}/cvs/${cv.candidate_id}/file`);
  return URL.createObjectURL(file);
}

// A titled block in the panel.
function Section({ title, children }) {
  return (
    <section className={classes.section}>
      <h3 className={classes.sectionTitle}>{title}</h3>
      {children}
    </section>
  );
}

// Rank and overall score, or why there is none.
function ScreeningSummary({ screening }) {
  if (!screening) return <div className={classes.note}>Not screened yet: no scores for this CV.</div>;
  if (!screening.passed)
    return (
      <div className={`${classes.note} ${classes.noteWarn}`}>
        Excluded in screening (failed a mandatory requirement). {screening.summary}
      </div>
    );
  const overall = Math.round(screening.overall);
  return (
    <div className={classes.scoreRow}>
      <div className={classes.ring} style={{ '--value': overall }}>
        <span>{overall}</span>
      </div>
      <div>
        <div className={classes.scoreTitle}>
          Rank {screening.rank} of {screening.ranked_count}
        </div>
        <div className={classes.muted}>Overall score out of 100</div>
      </div>
    </div>
  );
}

export default function CvPanel({ interviewId, onCollapse }) {
  const [cv, setCv] = useState(null);
  const [failed, setFailed] = useState(null);
  const [preview, setPreview] = useState(null); // Blob URL of the PDF shown
  const [opening, setOpening] = useState(false);

  useEffect(() => {
    apiGet(`/interviews/${interviewId}/candidate`)
      .then(setCv)
      .catch((error) => setFailed(error.message));
  }, [interviewId]);

  // Free the previewed file once the preview closes.
  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview]);

  // Show the PDF inside the page; a Word file is downloaded instead.
  async function openPreview() {
    setOpening(true);
    try {
      const url = await cvUrl(cv);
      if (cv.file_type === 'pdf') {
        setPreview(url);
      } else {
        const link = document.createElement('a');
        link.href = url;
        link.download = cv.cv_filename;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
    } catch (error) {
      notifyError('The CV couldn’t be opened.', error);
    } finally {
      setOpening(false);
    }
  }

  // Open the PDF in a new tab (the tab opens first, so it is not blocked).
  async function openTab() {
    const tab = window.open('', '_blank');
    try {
      const url = await cvUrl(cv);
      tab.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      tab?.close();
      notifyError('The CV couldn’t be opened.', error);
    }
  }

  if (failed) return <ErrorBanner title="The CV couldn’t be loaded.">{failed}</ErrorBanner>;
  if (!cv) return <Skeleton widths={[70, 90, 60, 80]} />;

  const screening = cv.screening;
  return (
    <div className={classes.cvPanel}>
      <div className={classes.cvHead}>
        <span className={classes.avatar}>{initials(cv.name)}</span>
        <div className={classes.cvName}>
          <b>{cv.name}</b>
          {cv.email && <span>{cv.email}</span>}
        </div>
        {onCollapse && (
          <Tooltip label="Hide the CV" withArrow>
            <button type="button" className={classes.iconButton} onClick={onCollapse} aria-label="Hide the CV">
              <IconChevronsLeft size={17} />
            </button>
          </Tooltip>
        )}
      </div>

      <div className={classes.cvScroll}>
        <ScreeningSummary screening={screening} />

        {screening?.passed && (
          <Section title="Scores">
            {DIMENSIONS.filter((key) => screening.dimensions[key]).map((key) => {
              const dim = screening.dimensions[key];
              return (
                <Tooltip key={key} label={dim.reason} multiline w={260} withArrow position="right">
                  <div className={classes.dim}>
                    <span>{dim.label}</span>
                    <b>{dim.score}</b>
                    <div className={classes.dimBar}>
                      <div style={{ width: `${dim.score}%` }} />
                    </div>
                  </div>
                </Tooltip>
              );
            })}
          </Section>
        )}

        {screening?.matches?.length > 0 && (
          <Section title="Requirements">
            <ul className={classes.reqs}>
              {screening.matches.map((match) => {
                const status = STATUS[match.status] ?? STATUS.unmet;
                const Icon = status.icon;
                return (
                  <li key={match.requirement}>
                    <span className={`${classes.reqIcon} ${status.className}`} title={status.text}>
                      <Icon size={12} stroke={2.5} />
                    </span>
                    <div>
                      <div className={classes.reqName}>
                        {match.requirement} <span className={classes.level}>{match.level}</span>
                      </div>
                      {match.evidence && <div className={classes.evidence}>“{match.evidence}”</div>}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Section>
        )}

        {cv.parsed ? (
          <Section title="Background">
            <div className={classes.facts}>
              <span>Experience</span>
              <b>{cv.years != null ? `about ${cv.years} years` : 'not readable from the CV'}</b>
              <span>Degree</span>
              <b className={classes.capital}>{cv.degree ?? 'none found'}</b>
            </div>
            {cv.jobs.length > 0 && (
              <ul className={classes.roles}>
                {cv.jobs.map((job, index) => (
                  <li key={index}>
                    <b>{job.title || 'Role'}</b>
                    <span>
                      {monthText(job.start)} – {monthText(job.end)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {cv.certifications.length > 0 && (
              <div className={classes.tags}>
                {cv.certifications.map((cert) => (
                  <span key={cert} className={classes.tag}>
                    {cert}
                  </span>
                ))}
              </div>
            )}
            {cv.skills && <p className={classes.skills}>{cv.skills}</p>}
          </Section>
        ) : (
          <div className={classes.note}>The CV hasn’t been read yet. Screen the job’s CVs to see its details.</div>
        )}

        <div className={classes.identity}>
          <IconShieldCheck size={17} />
          <div>
            <b>Identity check</b>
            Face and voice identification comes in a later step. Confirm the candidate’s identity another way for
            now.
          </div>
        </div>
      </div>

      <div className={classes.cvFoot}>
        {cv.file_type ? (
          <>
            <Button
              size="xs"
              variant="light"
              leftSection={cv.file_type === 'pdf' ? <IconEye size={15} /> : <IconDownload size={15} />}
              onClick={openPreview}
              loading={opening}
            >
              {cv.file_type === 'pdf' ? 'Preview CV' : 'Download CV'}
            </Button>
            {cv.file_type === 'pdf' && (
              <Button size="xs" variant="subtle" leftSection={<IconExternalLink size={15} />} onClick={openTab}>
                New tab
              </Button>
            )}
          </>
        ) : (
          <span className={classes.muted}>The CV file is missing.</span>
        )}
      </div>

      <Modal
        opened={Boolean(preview)}
        onClose={() => setPreview(null)}
        title={cv.cv_filename}
        size="min(1100px, 94vw)"
        centered
        classNames={{ body: classes.previewBody }}
      >
        {preview && <iframe src={preview} title={`CV of ${cv.name}`} className={classes.previewFrame} />}
      </Modal>
    </div>
  );
}
