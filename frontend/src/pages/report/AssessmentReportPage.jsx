// Assessment report (design: Assessment Report.dc.html): the consolidated
// assessment of one interviewed candidate (F6). It is prepared by itself
// after the interview's Q&A analysis, then waits for the interviewer's
// review: approve it, or request changes with a comment (HITL, §4B-7).
// Every conclusion shows its sources; the report exports as a printable
// HTML file, and candidates of the same job compare side by side.
// Interviewers only.

import { Anchor, Button, Menu, Stepper, Tabs } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import {
  IconChevronDown,
  IconChevronRight,
  IconCircleCheck,
  IconDownload,
  IconFileText,
  IconMessage2,
  IconMessage2Search,
  IconPrinter,
  IconUsers,
} from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { apiGet, apiPost } from '../../api/client';
import { EmptyState, ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyDone, notifyError } from '../../components/notify';
import StatusBadge from '../../components/StatusBadge';
import { whenText } from '../../utils/dates';
import { usePolling } from '../../utils/usePolling';
import CompareCandidates, { MAX_COMPARED } from './CompareCandidates';
import { downloadReport, printReport } from './exportReport';
import { ComponentScoresCard, FindingsList, FollowUpCard, SourcePanel, SuitabilityCard } from './ReportParts';
import classes from './Report.module.css';
import { generatingStep, REVIEW, reportState } from './reportFormat';
import ReviewBar from './ReviewBar';

// "Interview 14 Oct 2026, 32 min".
function interviewText(interview) {
  const day = new Date(interview.started_at ?? interview.scheduled_at).toLocaleDateString('en-GB', {
    dateStyle: 'medium',
  });
  if (!interview.started_at || !interview.ended_at) return `Interview ${day}`;
  const minutes = Math.max(1, Math.round((new Date(interview.ended_at) - new Date(interview.started_at)) / 60000));
  return `Interview ${day}, ${minutes} min`;
}

// While the report is prepared (design 2c): the three steps.
function Generating({ page }) {
  return (
    <section className={classes.card} role="status">
      <div className={classes.label}>Preparing the report</div>
      <Stepper active={generatingStep(page)} size="sm" allowNextStepsSelect={false}>
        <Stepper.Step label="Interview ended" />
        <Stepper.Step label="Q&A analysis" loading={generatingStep(page) === 1} />
        <Stepper.Step label="Final assessment" loading={generatingStep(page) === 2} />
      </Stepper>
      <div className={classes.note}>
        Pairing questions with answers and checking them against the job requirements. You’ll get a notification
        when the report is ready to review.
      </div>
    </section>
  );
}

export default function AssessmentReportPage() {
  const { interviewId } = useParams();
  const navigate = useNavigate();
  const [interview, setInterview] = useState(null);
  const [page, setPage] = useState(null); // { analysis, report }
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState('report');
  const [selected, setSelected] = useState(null);
  const [turns, setTurns] = useState(null);
  const [turnsFailed, setTurnsFailed] = useState(false);
  const [jobReports, setJobReports] = useState(null);
  const [chosen, setChosen] = useState([]);
  const [busy, setBusy] = useState(false);
  const lastState = useRef(null);
  const state = page && reportState(page);
  useDocumentTitle(interview ? `${interview.candidate_name} · Assessment report · CandiVue AI` : 'Assessment report · CandiVue AI');

  const load = useCallback(async () => {
    try {
      const [details, report] = await Promise.all([
        apiGet(`/interviews/${interviewId}`),
        apiGet(`/interviews/${interviewId}/report`),
      ]);
      setInterview(details);
      setPage(report);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [interviewId]);

  useEffect(() => {
    load();
  }, [load]);
  usePolling(load, state === 'generating' || state === 'changes');

  // "Ready for review" once a version finished while the page was open.
  useEffect(() => {
    if (state === 'waiting' && ['generating', 'changes'].includes(lastState.current)) {
      notifyDone('The assessment report is ready for your review');
    }
    lastState.current = state;
  }, [state]);

  // The transcript (for the source panel), loaded on first use.
  const loadTurns = useCallback(async () => {
    try {
      setTurnsFailed(false);
      setTurns((await apiGet(`/interviews/${interviewId}/transcript`)).turns);
    } catch {
      setTurnsFailed(true);
    }
  }, [interviewId]);

  // The job's reports (for the comparison), loaded when the tab opens.
  const loadJobReports = useCallback(async () => {
    try {
      const rows = await apiGet(`/jobs/${interview.job_id}/reports`);
      const assessed = rows.filter((row) => row.report?.content?.position).map((row) => row.interview_id);
      const others = assessed.filter((id) => id !== Number(interviewId));
      const first = assessed.includes(Number(interviewId)) ? [Number(interviewId)] : [];
      setChosen([...first, ...others].slice(0, MAX_COMPARED));
      setJobReports(rows);
    } catch (error) {
      notifyError('We couldn’t load the other reports.', error);
    }
  }, [interview, interviewId]);

  useEffect(() => {
    if (tab === 'compare' && interview && jobReports === null) loadJobReports();
  }, [tab, interview, jobReports, loadJobReports]);

  function select(sourceId) {
    setSelected(sourceId);
    if (page.report.content.sources[sourceId].kind === 'transcript' && turns === null) loadTurns();
  }

  // Send a request; reload afterwards. Returns true when it was accepted.
  async function act(path, body, done) {
    setBusy(true);
    try {
      await apiPost(path, body);
      if (done) notifyDone(done);
      await load();
      return true;
    } catch (error) {
      notifyError('That didn’t work.', error);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function exportAs(kind) {
    try {
      if (kind === 'print') await printReport(interviewId);
      else await downloadReport(interviewId, `Assessment report - ${interview.candidate_name}.html`);
    } catch (error) {
      notifyError('The report couldn’t be exported.', error);
    }
  }

  if (failed && !page) {
    return (
      <ErrorBanner title="We couldn’t load this report." onRetry={load}>
        Check your connection and try again.
      </ErrorBanner>
    );
  }
  if (!page || !interview) {
    return (
      <div className={classes.card}>
        <Skeleton widths={[40, 70, 90, 60]} />
      </div>
    );
  }

  const { report } = page;
  const content = report?.content?.position ? report.content : null;
  const review = REVIEW[state];
  const base = `/interviews/${interviewId}`;

  let body;
  if (state === 'none') {
    const ended = interview.status === 'ended';
    body = (
      <EmptyState
        icon={IconFileText}
        title="No report yet"
        action={
          ended && (
            <Button onClick={() => act(`${base}/analysis`, {})} loading={busy}>
              Prepare the report
            </Button>
          )
        }
      >
        {ended
          ? 'The interview has ended but was not analysed yet.'
          : `${interview.candidate_name}’s interview is on ${whenText(interview.scheduled_at)}. The report is prepared automatically once the interview ends.`}
      </EmptyState>
    );
  } else if (state === 'failed') {
    const retry = report ? `${base}/report` : `${base}/analysis`;
    body = (
      <ErrorBanner title="The report couldn’t be prepared." onRetry={() => act(retry, {})}>
        {(report ?? page.analysis).error} The transcript and screening results are saved. Try again; it continues
        from the last finished step.
      </ErrorBanner>
    );
  } else if (!content) {
    body = <Generating page={page} />;
  } else {
    const source = selected && content.sources[selected];
    body = (
      <>
        {state === 'changes' && (
          <div className={`${classes.banner} ${classes.bannerChanges}`} role="status">
            <IconMessage2 size={18} />
            <span>
              <b>Changes requested.</b> The report is being updated with your comment: “{report.reviewer_feedback}”
              It will return to you for review.
            </span>
          </div>
        )}
        {state === 'approved' && (
          <div className={`${classes.banner} ${classes.bannerApproved}`}>
            <IconCircleCheck size={18} />
            <span>
              <b>Approved by {report.reviewed_by ?? 'an interviewer'}</b>
              {report.approved_at && ` on ${new Date(report.approved_at).toLocaleString('en-GB')}`}. The report is
              final and can be exported.
            </span>
          </div>
        )}
        {state === 'waiting' && content.version > 1 && (
          <div className={classes.versionNote}>
            <b>Version {content.version} · updated after your comment</b>
            <span>Your comment: “{content.feedback}”</span>
            {content.changes && <span>What changed: {content.changes}</span>}
          </div>
        )}
        <div className={classes.layout}>
          <div className={classes.main}>
            <div className={classes.topCards}>
              <SuitabilityCard position={content.position} identity={content.identity} />
              <ComponentScoresCard components={content.components} analysisLink={`${base}/analysis`} />
            </div>
            <FindingsList
              findings={content.findings}
              sources={content.sources}
              selected={selected}
              onSelect={select}
            />
            <FollowUpCard
              claims={content.claims}
              quality={content.quality}
              sources={content.sources}
              selected={selected}
              onSelect={select}
              analysisLink={`${base}/analysis`}
            />
            <div className={classes.note}>
              Version {content.version}, prepared by {content.model} on{' '}
              {new Date(content.generated_at).toLocaleString('en-GB')}. AI-assisted: check the sources before
              relying on a conclusion.
            </div>
          </div>
          <SourcePanel
            source={source}
            turns={turns}
            transcriptFailed={turnsFailed}
            onRetry={loadTurns}
            onOpenTranscript={(turnId) => navigate(`${base}/analysis?tab=transcript&turn=${turnId}`)}
          />
        </div>
        <ReviewBar
          state={state}
          busy={busy}
          onApprove={() => act(`${base}/report/review`, { action: 'approve' }, 'Report approved')}
          onRequestChanges={(feedback) =>
            act(`${base}/report/review`, { action: 'request_changes', feedback }, 'Changes requested')
          }
        />
      </>
    );
  }

  return (
    <div className={classes.page}>
      <div className={classes.header}>
        <div className={classes.breadcrumb}>
          <Link to={`/reports?job=${interview.job_id}`}>Reports</Link>
          <IconChevronRight size={14} />
          <span>{interview.candidate_name}</span>
        </div>
        <div className={classes.titleRow}>
          <div className={classes.titleBlock}>
            <h1 className={classes.title}>{interview.candidate_name}</h1>
            <div className={classes.meta}>
              <Anchor component={Link} to={`/jobs/${interview.job_id}`} c="inherit">
                {interview.job_title}
              </Anchor>
              <span className={classes.sep}>·</span>
              <span>{interviewText(interview)}</span>
              {review && content && <StatusBadge tone={review.tone}>{review.label}</StatusBadge>}
            </div>
          </div>
          <div className={classes.actions}>
            <Button variant="light" component={Link} to={`${base}/analysis`} leftSection={<IconMessage2Search size={16} />}>
              Interview analysis
            </Button>
            <Menu position="bottom-end">
              <Menu.Target>
                <Button variant="default" rightSection={<IconChevronDown size={15} />} disabled={!content}>
                  Export / print
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconPrinter size={16} />} onClick={() => exportAs('print')}>
                  Print or save as PDF
                </Menu.Item>
                <Menu.Item leftSection={<IconDownload size={16} />} onClick={() => exportAs('html')}>
                  Download HTML
                </Menu.Item>
                {state !== 'approved' && (
                  <Menu.Label>Drafts are marked “Not yet approved” on every page.</Menu.Label>
                )}
              </Menu.Dropdown>
            </Menu>
          </div>
        </div>
      </div>

      <Tabs value={tab} onChange={setTab}>
        <Tabs.List>
          <Tabs.Tab value="report" leftSection={<IconFileText size={16} />}>
            Report
          </Tabs.Tab>
          <Tabs.Tab value="compare" leftSection={<IconUsers size={16} />}>
            Compare candidates
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="report" className={classes.tabPanel}>
          {body}
        </Tabs.Panel>
        <Tabs.Panel value="compare" className={classes.tabPanel}>
          {jobReports === null ? (
            <div className={classes.card}>
              <Skeleton />
            </div>
          ) : (
            <CompareCandidates rows={jobReports} chosen={chosen} onChoose={setChosen} jobTitle={interview.job_title} />
          )}
        </Tabs.Panel>
      </Tabs>
    </div>
  );
}
