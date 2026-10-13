// The Hiring Assistant in the interview room (§4B-10): interview questions
// from the question bank, from the candidate's CV, or its own suggestions.
// Interviewer only: the candidate never sees it (N9). Its own chat per
// interview (LangGraph 1 in room mode), so it can be prepared before the call.
// - Quick actions send a ready-made request.
// - Questions made from the CV appear on a card and are saved for this
//   interview (asking again shows the same set; "New set" makes another).
// - Without a question bank the assistant suggests its own questions; a hint
//   says how to add one (opens in a new tab, so the call is not left).
// - The AI model can be switched under the chat (quota shown).

import { Tooltip } from '@mantine/core';
import {
  IconBook2,
  IconCheck,
  IconCopy,
  IconFileText,
  IconRefresh,
  IconSparkles,
  IconTargetArrow,
  IconUsers,
} from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { apiGet, apiPostAi, apiPut } from '../../api/client';
import { ErrorBanner } from '../../components/Feedback';
import { notifyError } from '../../components/notify';
import ChatComposer from '../assistant/ChatComposer';
import { AssistantRow, AssistantText, StepLines, UserBubble, WorkingLine } from '../assistant/ChatItems';
import ModelPicker from '../assistant/ModelPicker';
import classes from './RoomPanels.module.css';

// Ready-made requests (shown as buttons).
const QUICK_ACTIONS = [
  { label: 'From the CV', icon: IconFileText, text: 'Suggest interview questions based on this candidate’s CV.' },
  { label: 'Question bank', icon: IconBook2, text: 'Suggest questions from the question bank for this role.' },
  {
    label: 'Check gaps',
    icon: IconTargetArrow,
    text: 'Suggest questions to check the job requirements the candidate only partly meets or misses.',
  },
  { label: 'Warm-up', icon: IconUsers, text: 'Suggest two short warm-up questions to start the interview.' },
];

// Copy a text; the icon turns into a tick for a moment.
function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      notifyError('Couldn’t copy.', { message: 'The browser blocked the clipboard. Select the text instead.' });
    }
  }
  return (
    <Tooltip label={copied ? 'Copied' : label} withArrow>
      <button type="button" className={classes.iconButton} onClick={copy} aria-label={label}>
        {copied ? <IconCheck size={15} /> : <IconCopy size={15} />}
      </button>
    </Tooltip>
  );
}

// Questions made from the CV, numbered, each with what it checks.
function QuestionsCard({ card, onNewSet, busy }) {
  return (
    <div className={classes.questions}>
      <div className={classes.questionsHead}>
        <span>
          <IconFileText size={15} /> From the CV{card.focus ? ` · ${card.focus}` : ''}
        </span>
        {card.saved && <span className={classes.savedTag}>Saved for this interview</span>}
      </div>
      <ol className={classes.questionList}>
        {card.questions.map((q, index) => (
          <li key={index}>
            <div className={classes.questionText}>
              {q.question}
              <CopyButton text={q.question} label="Copy question" />
            </div>
            <div className={classes.questionWhy}>
              <span className={classes.topic}>{q.topic}</span> {q.why}
            </div>
          </li>
        ))}
      </ol>
      {onNewSet && (
        <button type="button" className={classes.linkButton} onClick={onNewSet} disabled={busy}>
          <IconRefresh size={14} /> Make a new set
        </button>
      )}
    </div>
  );
}

// The chat items in order; consecutive steps are grouped.
function Items({ items, onNewSet, busy }) {
  const blocks = [];
  items.forEach((item, index) => {
    const last = blocks.at(-1);
    if (item.kind === 'step' && last?.kind === 'steps') last.steps.push(item.text);
    else if (item.kind === 'step') blocks.push({ kind: 'steps', steps: [item.text], key: index });
    else blocks.push({ ...item, key: index });
  });
  const lastCard = blocks.findLastIndex((b) => b.kind === 'questions');
  return blocks.map((block, index) => {
    if (block.kind === 'user') return <UserBubble key={block.key} text={block.text} />;
    if (block.kind === 'steps')
      return (
        <AssistantRow key={block.key}>
          <StepLines steps={block.steps} />
        </AssistantRow>
      );
    if (block.kind === 'questions')
      return (
        <AssistantRow key={block.key}>
          <QuestionsCard card={block} onNewSet={index === lastCard ? onNewSet : null} busy={busy} />
        </AssistantRow>
      );
    if (block.kind === 'assistant')
      return (
        <AssistantRow key={block.key}>
          <div className={classes.answer}>
            <AssistantText text={block.text} />
            <CopyButton text={block.text} />
          </div>
        </AssistantRow>
      );
    return null;
  });
}

export default function RoomAssistant({ interviewId }) {
  const [thread, setThread] = useState(null);
  const [models, setModels] = useState(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState(null);
  const listRef = useRef(null);
  const base = `/assistant/interviews/${interviewId}`;

  const loadModels = useCallback(() => {
    apiGet('/ai/models')
      .then(setModels)
      .catch(() => {}); // the picker is optional; the chat works without it
  }, []);

  useEffect(() => {
    apiGet(`${base}/thread`)
      .then(setThread)
      .catch((error) => setFailed(error.message));
    loadModels();
  }, [base, loadModels]);

  // Keep the newest answer in view.
  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: 'smooth' });
  }, [thread, sending]);

  // Send a message (typed or a quick action) and show the answer.
  async function ask(message) {
    if (!message.trim() || sending) return;
    setSending(true);
    setFailed(null);
    // Show the question at once; the answer replaces the whole thread.
    setThread((old) => old && { ...old, items: [...old.items, { kind: 'user', text: message }] });
    setText('');
    try {
      setThread(await apiPostAi(`${base}/messages`, { text: message }));
    } catch (error) {
      setFailed(error.message);
    } finally {
      setSending(false);
      loadModels();
    }
  }

  // Continue the turn that failed (the message was saved).
  async function retry() {
    setSending(true);
    setFailed(null);
    try {
      setThread(await apiPostAi(`${base}/retry`));
    } catch (error) {
      setFailed(error.message);
    } finally {
      setSending(false);
      loadModels();
    }
  }

  async function chooseModel(name) {
    try {
      setModels(await apiPut('/ai/model', { name }));
    } catch (error) {
      notifyError('The model wasn’t changed.', error);
    }
  }

  const noBank = thread && thread.question_bank_documents === 0;

  return (
    <div className={classes.assistant}>
      <div className={classes.assistantList} ref={listRef}>
        {thread && thread.items.length === 0 && !sending && (
          <div className={classes.empty}>
            <span className={classes.emptyIcon}>
              <IconSparkles size={22} />
            </span>
            <b>Need a question?</b>
            Pick one of the buttons below or ask in your own words, e.g. “two questions about Docker in production”.
          </div>
        )}
        {thread && <Items items={thread.items} busy={sending} onNewSet={() => ask('Make a new set of questions from the CV.')} />}
        {sending && <WorkingLine />}
        {failed && (
          <ErrorBanner title="The assistant couldn’t answer just now." onRetry={thread ? retry : undefined}>
            {failed}
          </ErrorBanner>
        )}
      </div>

      <div className={classes.quick}>
        {QUICK_ACTIONS.map(({ label, icon: Icon, text: request }) => (
          <button key={label} type="button" className={classes.chip} onClick={() => ask(request)} disabled={sending}>
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>
      {noBank && (
        <div className={classes.hint}>
          No question bank yet: the assistant suggests its own questions.{' '}
          <a href="/knowledge-base" target="_blank" rel="noopener noreferrer">
            Add one in the knowledge base
          </a>
          .
        </div>
      )}

      <div className={classes.assistantComposer}>
        <ChatComposer
          value={text}
          onChange={setText}
          onSend={() => ask(text)}
          sending={sending}
          locked={null}
          footer={
            models && (
              <ModelPicker models={models.models} usageUrl={models.usage_url} onChange={chooseModel} busy={sending} />
            )
          }
        />
      </div>
    </div>
  );
}
