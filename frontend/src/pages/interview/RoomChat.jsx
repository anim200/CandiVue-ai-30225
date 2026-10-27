// Chat between the interviewer and the candidate during the call, for things
// that are easier to type than to say (a link, a spelling, a code snippet).
// Used by both sides; must sit inside <LiveKitRoom>.
// - Every message goes through the backend (checked and saved), which then
//   has LiveKit push it to both pages at once (topic "chat").
// - The page also asks the backend every few seconds, so nothing is missed
//   if a push is lost (e.g. while reconnecting); ids prevent duplicates.
// - Text is shown as plain text (never HTML); http(s) links are clickable
//   and open in a new tab, so the call is never left by accident.
// path: "/interviews/12/messages" or "/candidate/messages". me: "interviewer"
// or "candidate". active: the chat is on screen (unread count resets).
// onUnread(count): new messages from the other side while not on screen.

import { Textarea } from '@mantine/core';
import { useDataChannel } from '@livekit/components-react';
import { IconArrowUp, IconMessages } from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { apiGet, apiPost } from '../../api/client';
import { notifyError } from '../../components/notify';
import classes from './RoomPanels.module.css';

const MAX_LENGTH = 1000; // same limit as the backend
const CHECK_EVERY_MS = 5000;
const LINK = /(https?:\/\/[^\s<>"']+)/g;

// "14:05"
function timeText(iso) {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

// Plain text with http(s) links made clickable (everything else stays text).
function MessageText({ text }) {
  return text.split(LINK).map((part, index) =>
    index % 2 === 1 ? (
      <a key={index} href={part} target="_blank" rel="noopener noreferrer" className={classes.link}>
        {part}
      </a>
    ) : (
      part
    ),
  );
}

export default function RoomChat({ path, me, otherName, active = true, onUnread }) {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [unread, setUnread] = useState(0);
  const seen = useRef(new Set());
  const lastId = useRef(0);
  const listRef = useRef(null);
  const activeRef = useRef(active);
  activeRef.current = active;

  // Add new messages (ignoring ones already shown).
  const add = useCallback(
    (incoming, countUnread = true) => {
      const fresh = incoming.filter((m) => !seen.current.has(m.id));
      if (fresh.length === 0) return;
      fresh.forEach((m) => seen.current.add(m.id));
      lastId.current = Math.max(lastId.current, ...fresh.map((m) => m.id));
      setMessages((old) => [...old, ...fresh].sort((a, b) => a.id - b.id));
      const theirs = fresh.filter((m) => m.sender !== me).length;
      if (countUnread && theirs && !activeRef.current) setUnread((n) => n + theirs);
    },
    [me],
  );

  // History first, then a check every few seconds (in case a push was lost).
  useEffect(() => {
    let current = true;
    const check = (first) =>
      apiGet(`${path}?after=${lastId.current}`)
        .then((list) => current && add(list, !first))
        .catch(() => {}); // the next check tries again
    check(true);
    const timer = setInterval(() => check(false), CHECK_EVERY_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [path, add]);

  // Messages pushed by LiveKit arrive at once.
  useDataChannel('chat', (data) => {
    try {
      add([JSON.parse(new TextDecoder().decode(data.payload))]);
    } catch {
      // not a chat message: ignore it
    }
  });

  // Seen: the unread count goes back to zero.
  useEffect(() => {
    if (active) setUnread(0);
  }, [active]);
  useEffect(() => {
    onUnread?.(unread);
  }, [unread, onUnread]);

  // Keep the newest message in view.
  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: 'smooth' });
  }, [messages, active]);

  async function send() {
    const message = text.trim();
    if (!message || sending) return;
    setSending(true);
    try {
      add([await apiPost(path, { text: message })], false);
      setText('');
    } catch (error) {
      notifyError('Your message wasn’t sent.', error);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={classes.chat}>
      <div className={classes.chatList} ref={listRef} aria-live="polite">
        {messages.length === 0 ? (
          <div className={classes.empty}>
            <span className={classes.emptyIcon}>
              <IconMessages size={22} />
            </span>
            <b>No messages yet</b>
            Type here to share a link, spell a name or paste a short code snippet with {otherName}.
          </div>
        ) : (
          messages.map((m, index) => {
            const mine = m.sender === me;
            const first = index === 0 || messages[index - 1].sender !== m.sender;
            return (
              <div key={m.id} className={`${classes.msgRow} ${mine ? classes.mine : ''}`}>
                {first && <div className={classes.msgMeta}>{mine ? 'You' : otherName} · {timeText(m.sent_at)}</div>}
                <div className={classes.bubble}>
                  <MessageText text={m.text} />
                </div>
              </div>
            );
          })
        )}
      </div>

      <form
        className={classes.chatComposer}
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <Textarea
          variant="unstyled"
          classNames={{ input: classes.chatInput }}
          style={{ flex: 1 }}
          autosize
          minRows={1}
          maxRows={4}
          maxLength={MAX_LENGTH}
          placeholder={`Message ${otherName}…`}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              send();
            }
          }}
          aria-label={`Message ${otherName}`}
        />
        <button
          type="submit"
          className={`${classes.sendButton} ${text.trim() ? classes.sendReady : ''}`}
          disabled={!text.trim() || sending}
          aria-label="Send message"
        >
          <IconArrowUp size={18} stroke={2.2} />
        </button>
      </form>
    </div>
  );
}
