// Interview analysis (design: Interview Analysis.dc.html): the Q&A analysis
// of an ended interview (F5), its saved transcript (F4) and the session
// record (F3). The analysis starts by itself when the interview ends; this
// page shows its progress, and "Try again" continues a failed one where it
// stopped. Interviewers only. The optional F8-F10 tabs are not built.

import { Anchor, Button, Tabs } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import {
  IconAlignLeft,
  IconCheck,
  IconChevronRight,
  IconFileText,
  IconInfoCircle,
  IconLoader2,
  IconMessage2Search,
  IconRefresh,
  IconX,
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';

import { apiGet, apiPost } from '../../api/client';
import ConfirmModal from '../../components/ConfirmModal';
import { EmptyState, ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyError } from '../../components/notify';
import StatusBadge from '../../components/StatusBadge';
import { whenText } from '../../utils/dates';
import { usePolling } from '../../utils/usePolling';
import classes from './Analysis.module.css';
import { isRunning } from './analysisFormat';
import QAAnalysis from './QAAnalysis';
import SessionDetails from './SessionDetails';
import TranscriptViewer from './TranscriptViewer';

const RUN_BADGE = {
  pending: { tone: 'info', icon: IconLoader2, text: 'Analysing' },
  running: { tone: 'info', icon: IconLoader2, text: 'Analysing' },
  completed: { tone: 'success', icon: IconCheck, text: 'Completed' },
  failed: { tone: 'danger', icon: IconX, text: 'Stopped' },
};

// "14 Oct 2026, 10:01–10:33".
function spanText(interview) {
  if (!interview.started_at || !interview.ended_at) return whenText(interview.scheduled_at);
  const time = (iso) => new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const day = new Date(interview.started_at).toLocaleDateString('en-GB', { dateStyle: 'medium' });
  return `${day}, ${time(interview.started_at)}–${time(interview.ended_at)}`;
}

// Striped progress while the analysis works (design 3a).
function AnalysisProgress({ run }) {
  const share = run.total ? Math.round((100 * run.processed) / run.total) : 0;
  return (
    <section className={classes.card} role="status">
      <div className={classes.cardHead}>
        <h2 className={classes.cardTitle}>Analysing questions and answers</h2>
        <span className={classes.mono}>
          {run.total ? `${run.processed} of ${run.total} Q&A units` : 'Finding the questions…'}
        </span>
      </div>
      <div className={classes.track}>
        <div className={classes.stripes} style={{ width: `${Math.max(share, 4)}%` }} />
      </div>
      <div className={classes.muted}>
        The transcript is ready now. Scores appear here as soon as the analysis finishes.
      </div>
    </section>
  );
}

export default function InterviewAnalysisPage() {
  const { interviewId } = useParams();
  const [search, setSearch] = useSearchParams();
  const [data, setData] = useState(null); // { interview, analysis, turns, report }
  const [failed, setFailed] = useState(false);
  const [openIds, setOpenIds] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [confirmAgain, setConfirmAgain] = useState(false);
  const tab = search.get('tab') ?? 'qa';
  const highlight = Number(search.get('turn')) || null;
  useDocumentTitle(data ? `${data.interview.candidate_name} · Interview analysis · CandiVue AI` : 'Interview analysis · CandiVue AI');

  const load = useCallback(async () => {
    try {
      const base = `/interviews/${interviewId}`;
      const [interview, analysis, transcript, report] = await Promise.all([
        apiGet(base),
        apiGet(`${base}/analysis`),
        apiGet(`${base}/transcript`),
        apiGet(`${base}/report`),
      ]);
      setData({ interview, analysis, turns: transcript.turns, report: report.report });
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [interviewId]);

  useEffect(() => {
    load();
  }, [load]);
  usePolling(load, isRunning(data?.analysis.run));

  // Start the analysis, continue a failed one, or (again) redo it.
  async function start(again = false) {
    setBusy(true);
    try {
      await apiPost(`/interviews/${interviewId}/analysis`, { again });
      setConfirmAgain(false);
      await load();
    } catch (error) {
      notifyError('The analysis didn’t start.', error);
    } finally {
      setBusy(false);
    }
  }

  // Open the Transcript tab at one turn (from a source chip).
  function showTurn(turnId) {
    setSearch({ tab: 'transcript', turn: String(turnId) });
  }

  // Back to the Q&A tab with one unit opened (from a Q id in the transcript).
  function showPair(pairId) {
    setOpenIds((ids) => new Set(ids).add(pairId));
    setSearch({ tab: 'qa' });
  }

  function toggle(pairId) {
    setOpenIds((ids) => {
      const next = new Set(ids);
      if (!next.delete(pairId)) next.add(pairId);
      return next;
    });
  }

  if (failed && !data) {
    return (
      <ErrorBanner title="We couldn’t load this interview." onRetry={load}>
        Check your connection and try again.
      </ErrorBanner>
    );
  }
  if (!data) {
    return (
      <div className={classes.card}>
        <Skeleton widths={[40, 70, 90, 60]} />
      </div>
    );
  }

  const { interview, analysis, turns, report } = data;
  const run = analysis.run;
  const turnMap = new Map(turns.map((turn) => [turn.id, turn]));
  const badge = run && RUN_BADGE[run.status];

  let qaBody;
  if (interview.status !== 'ended') {
    qaBody = (
      <EmptyState icon={IconMessage2Search} title="Nothing to analyse yet">
        {interview.status === 'cancelled'
          ? 'This interview was cancelled.'
          : `${interview.candidate_name}’s interview is on ${whenText(interview.scheduled_at)}. The transcript and analysis appear here after it ends.`}
      </EmptyState>
    );
  } else if (!run) {
    qaBody = (
      <EmptyState
        icon={IconMessage2Search}
        title="Not analysed yet"
        action={
          <Button onClick={() => start()} loading={busy}>
            Analyse the interview
          </Button>
        }
      >
        The analysis pairs each question with its answer and scores the job-related ones.
      </EmptyState>
    );
  } else if (isRunning(run)) {
    qaBody = <AnalysisProgress run={run} />;
  } else if (run.status === 'failed') {
    qaBody = (
      <ErrorBanner
        title={`The analysis stopped${run.total ? ` at ${run.processed} of ${run.total}` : ''}.`}
        onRetry={() => start()}
      >
        {run.error} The transcript is safe; try again and it continues where it stopped.
      </ErrorBanner>
    );
  } else {
    const results = analysis.results;
    qaBody = (
      <>
        {results.scored === 0 && (
          <div className={classes.notice} role="status">
            <IconInfoCircle size={18} />
            <span>
              <b>No job-related questions were found in this transcript.</b>{' '}
              {turns.length === 0
                ? 'No transcript was saved for this interview.'
                : 'Check the transcript, or reschedule the interview.'}
            </span>
          </div>
        )}
        <QAAnalysis results={results} turns={turnMap} openIds={openIds} onToggle={toggle} onShowTurn={showTurn} />
        <div className={classes.analysedNote}>
          Analysed by {results.model} on {new Date(results.analysed_at).toLocaleString('en-GB')}. Every score is a
          prompt for your judgement, not a decision.
          <Button variant="subtle" size="compact-sm" leftSection={<IconRefresh size={14} />} onClick={() => setConfirmAgain(true)}>
            Analyse again
          </Button>
        </div>
      </>
    );
  }

  return (
    <div className={classes.page}>
      <div className={classes.header}>
        <div className={classes.breadcrumb}>
          <Link to="/interviews">Interviews</Link>
          <IconChevronRight size={14} />
          <span>{interview.candidate_name}</span>
        </div>
        <div className={classes.titleRow}>
          <div className={classes.titleBlock}>
            <h1 className={classes.title}>{interview.candidate_name} · Interview analysis</h1>
            <div className={classes.meta}>
              <Anchor component={Link} to={`/jobs/${interview.job_id}`} c="inherit">
                {interview.job_title}
              </Anchor>
              <span className={classes.sep}>·</span>
              <span>{spanText(interview)}</span>
              {badge && (
                <StatusBadge tone={badge.tone} icon={<badge.icon size={13} />}>
                  {badge.text}
                </StatusBadge>
              )}
            </div>
          </div>
          <Button
            component={Link}
            to={`/interviews/${interviewId}/report`}
            leftSection={<IconFileText size={16} />}
            disabled={!report}
          >
            Open assessment report
          </Button>
        </div>
      </div>

      <Tabs value={tab} onChange={(value) => setSearch({ tab: value })} keepMounted={false}>
        <Tabs.List className={classes.tabs}>
          <Tabs.Tab value="qa" leftSection={<IconMessage2Search size={16} />}>
            Q&amp;A analysis
          </Tabs.Tab>
          <Tabs.Tab value="transcript" leftSection={<IconAlignLeft size={16} />}>
            Transcript
          </Tabs.Tab>
          <Tabs.Tab value="session" leftSection={<IconInfoCircle size={16} />}>
            Session details
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="qa" className={classes.panel}>
          {qaBody}
        </Tabs.Panel>
        <Tabs.Panel value="transcript" className={classes.panel}>
          <TranscriptViewer
            turns={turns}
            pairs={analysis.results?.pairs ?? []}
            highlight={highlight}
            fileName={`Transcript - ${interview.candidate_name}.txt`}
            onPickPair={showPair}
          />
        </Tabs.Panel>
        <Tabs.Panel value="session" className={classes.panel}>
          <SessionDetails interview={interview} analysisRun={run} report={report} />
        </Tabs.Panel>
      </Tabs>

      <ConfirmModal
        opened={confirmAgain}
        onClose={() => setConfirmAgain(false)}
        title="Analyse this interview again?"
        confirmLabel="Analyse again"
        onConfirm={() => start(true)}
        busy={busy}
      >
        The current analysis and the assessment report built on it are replaced, even an approved report. The
        report is prepared again afterwards and waits for your review.
      </ConfirmModal>
    </div>
  );
}
