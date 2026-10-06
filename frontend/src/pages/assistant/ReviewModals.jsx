// The two review dialogs (design frames 3a and 3b). Both open with the
// design's "pop" animation (0.25s).

import { Button, Group, Modal, Stack, Text, Textarea, TextInput } from '@mantine/core';
import { IconDeviceFloppy, IconHistory, IconLock } from '@tabler/icons-react';
import { useState } from 'react';

import classes from './Assistant.module.css';
import { LEVELS } from './labels';

// Opening animation from the design ("cvpop").
const POP = {
  in: { opacity: 1, transform: 'none' },
  out: { opacity: 0, transform: 'scale(.97) translateY(8px)' },
  transitionProperty: 'opacity, transform',
};
const TRANSITION = { transition: POP, duration: 250, timingFunction: 'ease-out' };

// "Mandatory: PostgreSQL" chips for the locked requirements.
function requirementChips(profile) {
  return LEVELS.flatMap(([level, label]) =>
    (profile?.requirements ?? [])
      .filter((r) => r.level === level)
      .map((r) => `${label}: ${r.text}`),
  );
}

// Edit dialog: title, about and responsibilities; requirements stay locked.
export function JdEditModal({ opened, onClose, jd, job, onSave, busy }) {
  const [title, setTitle] = useState(jd.content.title);
  const [about, setAbout] = useState(jd.content.about);
  const [lines, setLines] = useState(jd.content.responsibilities.join('\n'));
  const responsibilities = lines.split('\n').map((line) => line.trim()).filter(Boolean);
  const valid = title.trim().length >= 2 && about.trim().length >= 20 && responsibilities.length > 0;

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size={760}
      radius="md"
      transitionProps={TRANSITION}
      title={
        <div>
          <Text fz={18} fw={600}>
            Edit job description
          </Text>
          <Text fz={13} c="dimmed">
            {job.title} · version {jd.version} → {jd.version + 1}
          </Text>
        </div>
      }
    >
      <Stack gap={14}>
        <TextInput label="Job title" value={title} onChange={(e) => setTitle(e.currentTarget.value)} maxLength={120} />
        <Textarea
          label="About the role"
          autosize
          minRows={3}
          value={about}
          onChange={(e) => setAbout(e.currentTarget.value)}
          maxLength={2000}
        />
        <Textarea
          label="Responsibilities"
          description="One per line"
          autosize
          minRows={4}
          value={lines}
          onChange={(e) => setLines(e.currentTarget.value)}
        />
        <div>
          <Group gap={6} mb={6}>
            <Text fz={14} fw={500}>
              Requirements
            </Text>
            <IconLock size={14} color="#66717A" />
          </Group>
          <div className={classes.lockedChips}>
            {requirementChips(job.profile).map((chip) => (
              <span key={chip} className={classes.lockedChip}>
                {chip}
              </span>
            ))}
          </div>
          <div className={classes.hint} style={{ marginTop: 6 }}>
            Requirements come from the job profile, so screening stays consistent. Change them by
            asking in chat.
          </div>
        </div>
        <Group justify="space-between" mt={4}>
          <Text fz={13} c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <IconHistory size={15} />
            Version {jd.version} is kept in the history
          </Text>
          <Group gap={8}>
            <Button variant="subtle" onClick={onClose}>
              Cancel
            </Button>
            <Button
              leftSection={<IconDeviceFloppy size={16} />}
              disabled={!valid}
              loading={busy}
              onClick={() => onSave({ title: title.trim(), about: about.trim(), responsibilities })}
            >
              Save as version {jd.version + 1}
            </Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  );
}

// Reject dialog: the feedback tells the assistant what to change.
export function RejectModal({ opened, onClose, onSend, busy }) {
  const [feedback, setFeedback] = useState('');

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size={440}
      radius="md"
      transitionProps={TRANSITION}
      title={
        <Text fz={17} fw={600}>
          Reject this draft
        </Text>
      }
    >
      <Stack gap={12}>
        <Text fz={14} c="#48535B" lh={1.5}>
          Tell the assistant what to change. It writes a new version for you to review.
        </Text>
        <Textarea
          autosize
          minRows={3}
          placeholder="e.g. Too long. Mention hybrid work."
          value={feedback}
          onChange={(e) => setFeedback(e.currentTarget.value)}
          maxLength={1000}
          aria-label="Feedback"
          data-autofocus
        />
        <Group justify="flex-end" gap={8}>
          <Button variant="subtle" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!feedback.trim()} loading={busy} onClick={() => onSend(feedback.trim())}>
            Send feedback
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
