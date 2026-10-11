// The two review dialogs (design frames 3a and 3b). Both open with the
// design's "pop" animation (0.25s).

import { Button, Group, Modal, Stack, Text, Textarea, TextInput } from '@mantine/core';
import { IconDeviceFloppy, IconHistory, IconLock } from '@tabler/icons-react';
import { useState } from 'react';

import { POP_TRANSITION } from '../../components/ConfirmModal';
import classes from './Assistant.module.css';
import { LEVELS } from './labels';

// "Mandatory: PostgreSQL" chips for the locked requirements.
function requirementChips(profile) {
  return LEVELS.flatMap(([level, label]) =>
    (profile?.requirements ?? [])
      .filter((r) => r.level === level)
      .map((r) => `${label}: ${r.text}`),
  );
}

// Split a "one per line" text into a list of non-empty lines.
function toLines(text) {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

// Edit dialog: every written section; requirements stay locked.
export function JdEditModal({ opened, onClose, jd, job, onSave, busy }) {
  const { content } = jd;
  const [title, setTitle] = useState(content.title);
  const [about, setAbout] = useState(content.about);
  const [lines, setLines] = useState(content.responsibilities.join('\n'));
  const [arrangement, setArrangement] = useState(content.work_arrangement ?? '');
  const [offer, setOffer] = useState((content.what_we_offer ?? []).join('\n'));
  const [equality, setEquality] = useState(content.equal_opportunity ?? '');
  const responsibilities = toLines(lines);
  const valid = title.trim().length >= 2 && about.trim().length >= 20 && responsibilities.length > 0;

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size={760}
      radius="md"
      transitionProps={POP_TRANSITION}
      title={
        <div>
          <Text fz={19} fw={600}>
            Edit job description
          </Text>
          <Text fz={14} c="dimmed">
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
          label="Key responsibilities"
          description="One per line"
          autosize
          minRows={4}
          value={lines}
          onChange={(e) => setLines(e.currentTarget.value)}
        />
        <Textarea
          label="Work arrangement"
          autosize
          minRows={2}
          value={arrangement}
          onChange={(e) => setArrangement(e.currentTarget.value)}
          maxLength={800}
        />
        <Textarea
          label="What we offer"
          description="One per line"
          autosize
          minRows={3}
          value={offer}
          onChange={(e) => setOffer(e.currentTarget.value)}
        />
        <Textarea
          label="Equal opportunity"
          autosize
          minRows={2}
          value={equality}
          onChange={(e) => setEquality(e.currentTarget.value)}
          maxLength={800}
        />
        <div>
          <Group gap={6} mb={6}>
            <Text fz={15} fw={500}>
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
          <Text fz={14} c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
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
              onClick={() =>
                onSave({
                  title: title.trim(),
                  about: about.trim(),
                  responsibilities,
                  work_arrangement: arrangement.trim(),
                  what_we_offer: toLines(offer).slice(0, 8),
                  equal_opportunity: equality.trim(),
                })
              }
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
      transitionProps={POP_TRANSITION}
      title={
        <Text fz={18} fw={600}>
          Reject this draft
        </Text>
      }
    >
      <Stack gap={12}>
        <Text fz={15} c="#48535B" lh={1.5}>
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
