// Hiring Assistant (design: Hiring Assistant.dc.html). One chat per job:
// the interviewer describes the role, the assistant saves the profile,
// may search the knowledge base, writes the JD and waits for review.
// After approval it asks "Post this job to the job board?" (Post / Don't
// post); the job board result appears as a card. After screening it keeps
// the shortlist and plans interviews, which wait for the interviewer's
// Confirm on a card. The AI model can be switched under the chat box.
// Interviewers only (route guard + backend, N9).

import { Button } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import { IconPlus, IconSparkles } from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { apiGet, apiPost, apiPostAi, apiPut } from '../../api/client';
import { EmptyState, ErrorBanner } from '../../components/Feedback';
import { notifyError } from '../../components/notify';
import classes from './Assistant.module.css';
import ChatComposer from './ChatComposer';
import {
  AssistantRow,
  AssistantText,
  ProfileCard,
  ReviewNote,
  StepLines,
  UserBubble,
  WorkingLine,
} from './ChatItems';
import { InvitationConfirmCard, InvitationResultsCard, ShortlistCard } from './InterviewCards';
import JdCard from './JdCard';
import JobProgressBar from './JobProgressBar';
import ModelPicker from './ModelPicker';
import PostingCard, { PostConfirmCard } from './PostingCard';
import { JdEditModal, RejectModal } from './ReviewModals';
import ThreadList from './ThreadList';

// What to do first while the graph waits for the interviewer.
const LOCKED_HINTS = {
  jd_approval: 'Approve, edit or reject the job description to continue the chat.',
  post_confirmation: 'Choose Post or Don’t post to continue the chat.',
  invitation_confirmation: 'Confirm, change or cancel the interviews to continue the chat.',
};

// Example openers for an empty chat (design frame 2b).
const STARTERS = ['Start from a previous job', 'Backend developer, 3+ years'];

// Pulsing placeholder bubbles while a chat loads (design frame 2h).
function ChatSkeleton() {
  return (
    <div className={classes.skeleton} aria-label="Loading">
      <div style={{ height: 36, width: '60%', alignSelf: 'flex-end', borderRadius: 10 }} />
      <div style={{ height: 80, width: '80%', borderRadius: 8 }} />
      <div style={{ height: 36, width: '50%', alignSelf: 'flex-end', borderRadius: 10 }} />
    </div>
  );
}

// The feedback given on the version before `jd`, if that one was rejected.
function feedbackBefore(items, jd) {
  const previous = items.find((item) => item.kind === 'jd' && item.jd.version === jd.version - 1);
  const feedback = previous?.jd.status === 'rejected' ? previous.jd.feedback : null;
  return feedback && !feedback.startsWith('Replaced') ? feedback : null;
}

// Turn the thread items into chat rows; consecutive tool steps share one row.
function ChatRows({ items, profile, pending, reviewBusy, onApprove, onEdit, onReject, onPost, postBusy }) {
  const rows = [];
  const approvedJd = items.find((item) => item.kind === 'jd' && item.jd.status === 'approved')?.jd;
  const lastPosting = items.findLastIndex((item) => item.kind === 'posting');
  let steps = [];
  const flushSteps = () => {
    if (steps.length) rows.push(<AssistantRow key={`s${rows.length}`}><StepLines steps={steps} /></AssistantRow>);
    steps = [];
  };

  items.forEach((item, index) => {
    if (item.kind === 'step') {
      steps.push(item.text);
      return;
    }
    flushSteps();
    if (item.kind === 'user') rows.push(<UserBubble key={index} text={item.text} />);
    if (item.kind === 'review') rows.push(<ReviewNote key={index} text={item.text} />);
    if (item.kind === 'assistant')
      rows.push(
        <AssistantRow key={index}>
          <AssistantText text={item.text} />
        </AssistantRow>,
      );
    if (item.kind === 'profile')
      rows.push(
        <AssistantRow key={index}>
          <ProfileCard profile={item.profile} weights={item.weights} />
        </AssistantRow>,
      );
    if (item.kind === 'jd')
      rows.push(
        <AssistantRow key={index}>
          <JdCard
            jd={item.jd}
            profile={profile}
            waiting={pending?.kind === 'jd_approval' && pending.jd_id === item.jd.id}
            busy={reviewBusy}
            previousFeedback={feedbackBefore(items, item.jd)}
            onApprove={onApprove}
            onEdit={onEdit}
            onReject={onReject}
          />
        </AssistantRow>,
      );
    if (item.kind === 'shortlist')
      rows.push(
        <AssistantRow key={index}>
          <ShortlistCard card={item} />
        </AssistantRow>,
      );
    if (item.kind === 'invitations')
      rows.push(
        <AssistantRow key={index}>
          <InvitationResultsCard result={item} />
        </AssistantRow>,
      );
    if (item.kind === 'posting')
      rows.push(
        <AssistantRow key={index}>
          <PostingCard
            result={item}
            approvedJd={approvedJd}
            profile={profile}
            onPost={index === lastPosting && item.status !== 'posted' && !pending ? onPost : null}
            busy={postBusy}
          />
        </AssistantRow>,
      );
  });
  flushSteps();
  return rows;
}

// The page: thread list on the left, the selected job's chat on the right.
export default function HiringAssistantPage() {
  const { jobId } = useParams();
  const id = jobId ? Number(jobId) : null;
  const navigate = useNavigate();

  const [jobs, setJobs] = useState(null); // null = loading
  const [jobsFailed, setJobsFailed] = useState(false);
  const [thread, setThread] = useState(null); // { items, pending_review }
  const [threadFailed, setThreadFailed] = useState(false);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [sentText, setSentText] = useState(null); // shown at once, before the answer
  const [turnFailed, setTurnFailed] = useState(null); // the error message, or null
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState(null);
  const [dialog, setDialog] = useState(null); // 'edit' | 'reject' | null
  const [creating, setCreating] = useState(false);
  const [models, setModels] = useState(null); // { models, usage_url } for the picker
  const [modelBusy, setModelBusy] = useState(false);
  const endRef = useRef(null);
  const job = jobs?.find((j) => j.id === id);
  useDocumentTitle(`${job?.title ?? 'Hiring Assistant'} · CandiVue AI`);

  // Load all jobs for the thread list (also refreshes their stage lines).
  const loadJobs = useCallback(async () => {
    setJobsFailed(false);
    try {
      setJobs(await apiGet('/jobs'));
    } catch {
      setJobsFailed(true);
    }
  }, []);

  // Load the open job's chat thread.
  const loadThread = useCallback(async (jobIdToLoad) => {
    setThread(null);
    setThreadFailed(false);
    try {
      setThread(await apiGet(`/assistant/jobs/${jobIdToLoad}/thread`));
    } catch {
      setThreadFailed(true);
    }
  }, []);

  // Re-read the thread without the loading placeholder (after a failed AI
  // turn, to show what was already saved, e.g. an approval).
  const refreshThread = useCallback(async (jobIdToLoad) => {
    try {
      setThread(await apiGet(`/assistant/jobs/${jobIdToLoad}/thread`));
    } catch {
      // keep what is on screen; the error banner already explains
    }
  }, []);

  // Load the AI models and today's usage (refreshed after every AI turn).
  const loadModels = useCallback(async () => {
    try {
      setModels(await apiGet('/ai/models'));
    } catch {
      // the picker just stays hidden; the chat still works
    }
  }, []);

  useEffect(() => {
    loadJobs();
    loadModels();
  }, [loadJobs, loadModels]);

  useEffect(() => {
    setSentText(null);
    setTurnFailed(null);
    setReviewError(null);
    if (id) loadThread(id);
  }, [id, loadThread]);

  // Keep the newest message in view.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [thread, sentText, sending, turnFailed]);

  // Start a new job and open its (empty) chat.
  async function newJob() {
    setCreating(true);
    try {
      const job = await apiPost('/jobs');
      await loadJobs();
      navigate(`/assistant/${job.id}`);
    } catch (error) {
      notifyError('The job wasn’t created.', error);
    } finally {
      setCreating(false);
    }
  }

  // Send the typed message; the assistant answers (may call tools first).
  async function send() {
    const text = draft.trim();
    setDraft('');
    setSentText(text);
    setSending(true);
    setTurnFailed(null);
    try {
      setThread(await apiPostAi(`/assistant/jobs/${id}/messages`, { text }));
      setSentText(null);
      loadJobs();
    } catch (error) {
      setTurnFailed(error.message); // the message is saved; "Try again" continues
      await refreshThread(id);
      setSentText(null);
      loadJobs();
    } finally {
      setSending(false);
      loadModels();
    }
  }

  // Continue a turn that failed (the backend kept the message).
  async function retryTurn() {
    setSending(true);
    setTurnFailed(null);
    try {
      setThread(await apiPostAi(`/assistant/jobs/${id}/retry`));
      setSentText(null);
      loadJobs();
    } catch (error) {
      setTurnFailed(error.message);
    } finally {
      setSending(false);
      loadModels();
    }
  }

  // Post the approved JD again (after a failure or once the form link is added).
  async function postAgain() {
    setSending(true);
    setReviewError(null);
    try {
      setThread(await apiPostAi(`/assistant/jobs/${id}/post`));
      loadJobs();
    } catch (error) {
      setReviewError(error.message);
    } finally {
      setSending(false);
    }
  }

  // Switch the AI model for every AI call (counts and limits are per model).
  async function chooseModel(name) {
    setModelBusy(true);
    try {
      setModels(await apiPut('/ai/model', { name }));
    } catch (error) {
      setReviewError(error.message);
    } finally {
      setModelBusy(false);
    }
  }

  // Send a decision the paused graph waits for: the JD review (approve,
  // edit, reject), the posting question (post, skip) or the interviews
  // (confirm, cancel).
  async function decide(path, decision) {
    setReviewBusy(true);
    setReviewError(null);
    try {
      setThread(await apiPostAi(`/assistant/jobs/${id}/${path}`, decision));
      setDialog(null);
      loadJobs();
    } catch (error) {
      setDialog(null);
      if (error.status === 503) {
        // The decision was saved; only the assistant's answer failed.
        setTurnFailed(error.message);
        await refreshThread(id);
        loadJobs();
      } else {
        setReviewError(error.message);
      }
    } finally {
      setReviewBusy(false);
      loadModels();
    }
  }

  // The JD review: approve, edit or reject.
  const review = (decision) => decide('review', decision);

  if (jobsFailed) {
    return (
      <div style={{ padding: 24 }}>
        <ErrorBanner title="We couldn’t load your jobs." onRetry={loadJobs}>
          Check your connection and try again.
        </ErrorBanner>
      </div>
    );
  }

  const pending = thread?.pending_review ?? null;
  const pendingJd = thread?.items.find((item) => item.kind === 'jd' && item.jd.id === pending?.jd_id)?.jd;
  const isEmpty = thread && thread.items.length === 0 && !sentText;
  // What locks the chat box (and the hint shown above it), if anything.
  const lockedHint = pending && LOCKED_HINTS[pending.kind];

  return (
    <div className={classes.layout}>
      <ThreadList
        jobs={jobs ?? []}
        activeId={id}
        onNewJob={newJob}
        creating={creating}
        className={id ? classes.hideOnPhone : ''}
      />

      <section className={`${classes.chat} ${id ? '' : classes.hideOnPhone}`}>
        {!id || (jobs && !job) ? (
          <EmptyState
            icon={IconSparkles}
            title={id ? 'This job no longer exists' : 'Choose a job or start a new one'}
            action={
              <Button leftSection={<IconPlus size={16} />} onClick={newJob} loading={creating}>
                New job
              </Button>
            }
          >
            Each job has its own chat. Describe the role and the assistant drafts the profile and
            the job description for you to approve.
          </EmptyState>
        ) : (
          <>
            {job && <JobProgressBar job={job} />}
            <div className={classes.messages}>
              {threadFailed && (
                <ErrorBanner title="We couldn’t load this chat." onRetry={() => loadThread(id)}>
                  Check your connection and try again.
                </ErrorBanner>
              )}
              {!thread && !threadFailed && <ChatSkeleton />}
              {isEmpty && (
                <EmptyState
                  icon={IconSparkles}
                  title="Describe the role you’re hiring for"
                  action={
                    <div className={classes.chips}>
                      {STARTERS.map((text) => (
                        <button key={text} type="button" className={classes.chip} onClick={() => setDraft(text)}>
                          {text}
                        </button>
                      ))}
                    </div>
                  }
                >
                  Mention must-have skills, minimum experience and anything nice to have. I’ll turn
                  it into a job profile and a job description for you to approve.
                </EmptyState>
              )}
              {thread && (
                <ChatRows
                  items={thread.items}
                  profile={job?.profile}
                  pending={pending}
                  reviewBusy={reviewBusy}
                  onApprove={() => review({ action: 'approve' })}
                  onEdit={() => setDialog('edit')}
                  onReject={() => setDialog('reject')}
                  onPost={postAgain}
                  postBusy={sending}
                />
              )}
              {pending?.kind === 'post_confirmation' && (
                <AssistantRow>
                  <PostConfirmCard
                    question={pending}
                    busy={reviewBusy}
                    onDecide={(action) => decide('post-decision', { action })}
                  />
                </AssistantRow>
              )}
              {pending?.kind === 'invitation_confirmation' && (
                <AssistantRow>
                  <InvitationConfirmCard
                    key={JSON.stringify(pending.items)} // a new plan starts a fresh card
                    plan={pending}
                    busy={reviewBusy}
                    onDecide={(decision) => decide('invitation-decision', decision)}
                  />
                </AssistantRow>
              )}
              {sentText && <UserBubble text={sentText} />}
              {sending && <WorkingLine />}
              {turnFailed && (
                <ErrorBanner title="I couldn’t answer just now." onRetry={retryTurn}>
                  {turnFailed} Your message is saved.
                </ErrorBanner>
              )}
              {reviewError && <ErrorBanner title="That didn’t work.">{reviewError}</ErrorBanner>}
              <div ref={endRef} />
            </div>
            <ChatComposer
              value={draft}
              onChange={setDraft}
              onSend={send}
              sending={sending}
              locked={lockedHint}
              footer={
                models && (
                  <ModelPicker
                    models={models.models}
                    usageUrl={models.usage_url}
                    onChange={chooseModel}
                    busy={modelBusy || sending || reviewBusy}
                  />
                )
              }
            />
          </>
        )}
      </section>

      {pendingJd && job && dialog === 'edit' && (
        <JdEditModal
          opened
          onClose={() => setDialog(null)}
          jd={pendingJd}
          job={job}
          busy={reviewBusy}
          onSave={(content) => review({ action: 'edit', content })}
        />
      )}
      <RejectModal
        opened={dialog === 'reject'}
        onClose={() => setDialog(null)}
        busy={reviewBusy}
        onSend={(feedback) => review({ action: 'reject', feedback })}
      />
    </div>
  );
}
