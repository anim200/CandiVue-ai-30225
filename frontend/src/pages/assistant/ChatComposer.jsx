// Message box at the bottom of the chat (design: ChatComposer). While a JD
// waits for review, or a post waits for confirmation, it is locked, because
// that decision comes first. `footer`: the AI model picker.

import { Button, TextInput } from '@mantine/core';
import { IconEye, IconSend } from '@tabler/icons-react';

import classes from './Assistant.module.css';

// The input with its Send button; Enter sends too.
export default function ChatComposer({ value, onChange, onSend, sending, locked, footer }) {
  const canSend = value.trim().length > 0 && !sending && !locked;

  return (
    <form
      className={classes.composer}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend();
      }}
    >
      {locked && (
        <div className={classes.composerHint}>
          <IconEye size={14} />
          {locked}
        </div>
      )}
      <div className={classes.composerRow}>
        <TextInput
          style={{ flex: 1 }}
          size="md"
          placeholder="Message the Hiring Assistant…"
          value={value}
          onChange={(event) => onChange(event.currentTarget.value)}
          disabled={locked}
          maxLength={2000}
          aria-label="Message"
        />
        <Button type="submit" size="md" leftSection={<IconSend size={16} />} disabled={!canSend}>
          Send
        </Button>
      </div>
      {footer}
    </form>
  );
}
