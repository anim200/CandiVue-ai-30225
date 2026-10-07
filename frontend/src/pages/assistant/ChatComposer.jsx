// Message box at the bottom of the chat (design: ChatComposer, restyled on
// the user's request: see Composer.module.css). While a JD waits for
// review, or a post waits for confirmation, it is locked, because that
// decision comes first. `locked`: the hint text, or null. `footer`: the AI
// model picker. Enter sends; Shift+Enter starts a new line.

import { Textarea } from '@mantine/core';
import { IconArrowUp, IconEye, IconLock } from '@tabler/icons-react';

import classes from './Composer.module.css';

const MAX_LENGTH = 2000; // same limit as the backend
const SHOW_COUNT_FROM = 1700; // the character count appears near the limit

// The input card with its round Send button, the hint and the footer.
export default function ChatComposer({ value, onChange, onSend, sending, locked, footer }) {
  const canSend = value.trim().length > 0 && !sending && !locked;

  // Enter sends; Shift+Enter (or typing in an input method) adds a new line.
  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) onSend();
    }
  }

  return (
    <form
      className={classes.composer}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend();
      }}
    >
      {locked && (
        <div className={classes.hint}>
          <IconEye size={15} />
          {locked}
        </div>
      )}

      <div className={`${classes.card} ${locked ? classes.locked : ''}`}>
        <Textarea
          variant="unstyled"
          style={{ flex: 1 }}
          classNames={{ input: classes.textarea }}
          autosize
          minRows={1}
          maxRows={6}
          placeholder={locked ? 'Finish the step above to continue…' : 'Message the Hiring Assistant…'}
          value={value}
          onChange={(event) => onChange(event.currentTarget.value)}
          onKeyDown={handleKeyDown}
          disabled={Boolean(locked)}
          maxLength={MAX_LENGTH}
          aria-label="Message"
        />
        <div className={classes.actions}>
          {canSend && (
            // fades in while typing (desktop only)
            <span className={classes.keyHint}>
              <span className={classes.kbd}>Enter</span> send ·{' '}
              <span className={classes.kbd}>Shift+Enter</span> new line
            </span>
          )}
          {value.length >= SHOW_COUNT_FROM && (
            <span className={`${classes.charCount} ${value.length >= MAX_LENGTH ? classes.charCountHigh : ''}`}>
              {value.length}/{MAX_LENGTH}
            </span>
          )}
          <button
            type="submit"
            // key: the button is new when it becomes ready, so the pop replays
            key={canSend ? 'ready' : 'idle'}
            className={`${classes.send} ${canSend || sending ? classes.ready : ''}`}
            disabled={!canSend}
            aria-label={sending ? 'Sending' : 'Send'}
          >
            {sending ? (
              <span className={classes.spinner} />
            ) : locked ? (
              <IconLock size={17} />
            ) : (
              <IconArrowUp size={19} stroke={2.2} className={classes.sendIcon} />
            )}
          </button>
        </div>
      </div>

      {footer && <div className={classes.footer}>{footer}</div>}
    </form>
  );
}
