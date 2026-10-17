// Live transcript in the interviewer's room (design: LiveTranscript): every
// turn with its time from the start (mono), the speaker in their colour, and
// the text. Interviewer only; the candidate never sees it (N9).
// - useTranscript gets the text two ways: the transcriber pushes it over the
//   call's data channel to the interviewer only (topic "transcript": words
//   still being recognised, shown grey while they are spoken, and every
//   saved turn at once), and the page asks the backend every 2.5 s for turns
//   new or changed since its last answer (a fallback and the status). Turns
//   are merged by id; nothing re-renders when nothing changed. One source
//   feeds both views:
// - TranscriptView "card": the compact card under the call, with an expand
//   button; "full": the Transcript tab beside the call (full height, larger
//   text, lines of one speaker grouped, Copy).
// - Keeps the newest line in view, unless the interviewer scrolled up to
//   read: then a "New lines" button jumps back down.
// - Shows whether speech-to-text works (Listening / Starting / Not running /
//   the problem, e.g. a refused Deepgram key) and pauses while the call
//   reconnects. After the interview the transcript stays as saved.
// TranscriptView must sit inside <LiveKitRoom> (call connection state).

import { Tooltip } from '@mantine/core';
import { useConnectionState, useDataChannel } from '@livekit/components-react';
import { IconArrowDown, IconArrowsMaximize, IconCheck, IconCopy, IconTextCaption } from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiGet } from '../../api/client';
import { notifyError } from '../../components/notify';
import { formatElapsed } from './callTime';
import { mergeTurns } from './transcriptMerge';
import classes from './Transcript.module.css';

const CHECK_EVERY_MS = 2500; // the push does the fast work; this is the fallback
const LIVE_WORDS_MS = 6000; // live words without an update for this long fade
const SPEAKERS = ['interviewer', 'candidate'];
export const TRANSCRIPT_STATUS = {
  waiting: { text: 'Waiting for the call', tone: classes.idle },
  starting: { text: 'Starting…', tone: classes.busy },
  listening: { text: 'Listening', tone: classes.live },
  off: { text: 'Not running', tone: classes.bad },
  problem: { text: 'Not transcribing', tone: classes.bad },
  ended: { text: 'Saved', tone: classes.idle },
};

// The transcript of one interview, kept up to date:
// { turns, live: [{ speaker, text }], status, problem }. Must be used inside
// <LiveKitRoom> (for the pushed text).
export function useTranscript(interviewId) {
  const [turns, setTurns] = useState(() => new Map());
  const [live, setLive] = useState({}); // speaker → { text, at }
  const [status, setStatus] = useState(null);
  const [problem, setProblem] = useState(null);
  const since = useRef(null);

  // New and changed turns since the last answer, merged by id.
  const check = useCallback(async () => {
    const query = since.current ? `?since=${encodeURIComponent(since.current)}` : '';
    const answer = await apiGet(`/interviews/${interviewId}/transcript${query}`);
    since.current = answer.server_time;
    setStatus(answer.status);
    setProblem(answer.problem);
    if (answer.turns.length > 0) setTurns((old) => mergeTurns(old, answer.turns));
    return answer.status;
  }, [interviewId]);

  // Pushed by the transcriber: live words, or a saved turn (which replaces
  // that speaker's live words).
  useDataChannel('transcript', (packet) => {
    let message;
    try {
      message = JSON.parse(new TextDecoder().decode(packet.payload));
    } catch {
      return; // not ours
    }
    if (message.kind === 'turn' && message.turn) {
      setTurns((old) => mergeTurns(old, [message.turn]));
      setLive((old) => ({ ...old, [message.turn.speaker]: null }));
    } else if (message.kind === 'interim' && SPEAKERS.includes(message.speaker)) {
      const words = message.text ? { text: message.text, at: Date.now() } : null;
      setLive((old) => ({ ...old, [message.speaker]: words }));
    }
  });

  // Live words that stopped updating (e.g. a lost push) fade away.
  useEffect(() => {
    const timer = setInterval(() => {
      setLive((old) => {
        const stale = SPEAKERS.filter((s) => old[s] && Date.now() - old[s].at > LIVE_WORDS_MS);
        if (stale.length === 0) return old;
        const next = { ...old };
        stale.forEach((s) => {
          next[s] = null;
        });
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    let current = true;
    let timer;
    const loop = async () => {
      let state = null;
      try {
        state = await check();
      } catch {
        // the next check tries again
      }
      // After the end one last check is enough: nothing changes any more.
      if (current && state !== 'ended') timer = setTimeout(loop, CHECK_EVERY_MS);
    };
    loop();
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [check]);

  const ordered = useMemo(
    () => [...turns.values()].sort((a, b) => a.start_ms - b.start_ms || a.id - b.id),
    [turns],
  );
  const speaking = useMemo(
    () => SPEAKERS.filter((s) => live[s]?.text).map((s) => ({ speaker: s, text: live[s].text })),
    [live],
  );
  return { turns: ordered, live: speaking, status, problem };
}

// The transcript as plain text, e.g. "[00:12] Interviewer: Hello."
function asText(turns, label) {
  return turns.map((t) => `[${formatElapsed(t.start_ms / 1000)}] ${label(t.speaker)}: ${t.text}`).join('\n');
}

// One view of the transcript. variant: "card" (under the call) or "full"
// (the Transcript tab). onExpand: opens the full view (card only).
export function TranscriptView({ data, candidateName, variant = 'card', onExpand, className }) {
  const { turns, live, status, problem } = data;
  const [atBottom, setAtBottom] = useState(true);
  const [copied, setCopied] = useState(false);
  const listRef = useRef(null);
  const connection = useConnectionState();
  const reconnecting = connection === 'reconnecting' || connection === 'signalReconnecting';
  const full = variant === 'full';
  const firstName = candidateName.split(' ')[0] || 'Candidate';
  const label = (speaker) => (speaker === 'interviewer' ? 'Interviewer' : firstName);
  const chip = TRANSCRIPT_STATUS[status] ?? TRANSCRIPT_STATUS.starting;

  // Follow the newest line while the interviewer is at the bottom.
  useEffect(() => {
    const list = listRef.current;
    if (list && atBottom) list.scrollTop = list.scrollHeight;
  }, [turns, live, atBottom]);

  function onScroll() {
    const list = listRef.current;
    setAtBottom(list.scrollHeight - list.scrollTop - list.clientHeight < 40);
  }

  function jumpDown() {
    const list = listRef.current;
    list.scrollTo({ top: list.scrollHeight, behavior: 'smooth' });
    setAtBottom(true);
  }

  async function copyAll() {
    try {
      await navigator.clipboard.writeText(asText(turns, label));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      notifyError('Couldn’t copy.', { message: 'The browser blocked the clipboard. Select the text instead.' });
    }
  }

  return (
    <section className={`${classes.panel} ${full ? classes.full : ''} ${className ?? ''}`} aria-label="Live transcript">
      <div className={classes.head}>
        {!full && (
          <>
            <IconTextCaption size={16} />
            Live transcript
            <span className={classes.private}>Only you see this</span>
          </>
        )}
        <span className={`${classes.status} ${chip.tone}`}>{chip.text}</span>
        {full && (
          <>
            <span className={classes.count}>{turns.length === 1 ? '1 turn' : `${turns.length} turns`}</span>
            <Tooltip label={copied ? 'Copied' : 'Copy the whole transcript'} withArrow>
              <button
                type="button"
                className={classes.iconButton}
                onClick={copyAll}
                disabled={turns.length === 0}
                aria-label="Copy the whole transcript"
              >
                {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              </button>
            </Tooltip>
          </>
        )}
        {onExpand && (
          <Tooltip label="Open the transcript beside the call" withArrow>
            <button type="button" className={classes.iconButton} onClick={onExpand} aria-label="Expand the transcript">
              <IconArrowsMaximize size={16} />
            </button>
          </Tooltip>
        )}
      </div>

      {reconnecting && <div className={classes.notice}>Paused while the call reconnects…</div>}
      {status === 'problem' && problem && <div className={classes.problem}>{problem}</div>}
      {status === 'off' && (
        <div className={classes.problem}>
          Speech-to-text isn’t running. Check that the transcriber service is up (docker compose ps).
        </div>
      )}

      <div className={classes.list} ref={listRef} onScroll={onScroll} aria-live="polite">
        {turns.length === 0 && live.length === 0 ? (
          <div className={classes.empty}>
            {status === 'ended'
              ? 'Nothing was transcribed in this interview.'
              : 'The transcript appears here as soon as someone speaks.'}
          </div>
        ) : full ? (
          // Full view: the speaker and time once per run of their lines.
          turns.map((turn, index) => {
            const first = index === 0 || turns[index - 1].speaker !== turn.speaker;
            const tone = turn.speaker === 'interviewer' ? classes.interviewer : classes.candidate;
            return (
              <div key={turn.id} className={`${classes.fullTurn} ${first ? classes.newSpeaker : ''}`}>
                {first && (
                  <div className={classes.meta}>
                    <span className={`${classes.speaker} ${tone}`}>{label(turn.speaker)}</span>
                    <span className={classes.time}>{formatElapsed(turn.start_ms / 1000)}</span>
                  </div>
                )}
                <div className={classes.text}>{turn.text}</div>
              </div>
            );
          })
        ) : (
          turns.map((turn) => (
            <div key={turn.id} className={classes.turn}>
              <span className={classes.time}>{formatElapsed(turn.start_ms / 1000)}</span>
              <span
                className={`${classes.speaker} ${turn.speaker === 'interviewer' ? classes.interviewer : classes.candidate}`}
              >
                {label(turn.speaker)}
              </span>
              <span className={classes.text}>{turn.text}</span>
            </div>
          ))
        )}
        {/* Words being spoken right now (not saved yet), grey. */}
        {live.map(({ speaker, text }) => {
          const tone = speaker === 'interviewer' ? classes.interviewer : classes.candidate;
          const dots = (
            <span className={classes.typing} aria-label="speaking">
              <i />
              <i />
              <i />
            </span>
          );
          return (
            <div key={speaker} className={`${full ? classes.fullTurn : classes.turn} ${classes.speaking}`}>
              {full ? (
                <div className={classes.meta}>
                  <span className={`${classes.speaker} ${tone}`}>{label(speaker)}</span>
                  {dots}
                </div>
              ) : (
                <>
                  {dots}
                  <span className={`${classes.speaker} ${tone}`}>{label(speaker)}</span>
                </>
              )}
              <span className={classes.text}>{text}</span>
            </div>
          );
        })}
      </div>

      {!atBottom && turns.length > 0 && (
        <button type="button" className={classes.jump} onClick={jumpDown}>
          <IconArrowDown size={14} /> New lines
        </button>
      )}
    </section>
  );
}
