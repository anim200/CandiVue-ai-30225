// "Are you sure?" dialog for actions that can't be undone (remove an
// applicant, remove a document), so they all look and behave the same.
// Opens with the design's "pop" animation, also used by the other dialogs.

import { Button, Group, Modal, Text } from '@mantine/core';

// Opening animation from the design ("cvpop", 0.25s).
export const POP_TRANSITION = {
  transition: {
    in: { opacity: 1, transform: 'none' },
    out: { opacity: 0, transform: 'scale(.97) translateY(8px)' },
    transitionProperty: 'opacity, transform',
  },
  duration: 250,
  timingFunction: 'ease-out',
};

// The dialog: a question as the title, what will happen, a "keep as is"
// button (Cancel unless cancelLabel says otherwise) and a red confirm button.
export default function ConfirmModal({
  opened,
  onClose,
  title,
  children,
  confirmLabel,
  onConfirm,
  busy,
  cancelLabel = 'Cancel',
}) {
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size={440}
      radius="md"
      centered
      transitionProps={POP_TRANSITION}
      title={
        <Text fz={18} fw={600}>
          {title}
        </Text>
      }
    >
      <Text fz={15} c="#48535B" lh={1.55}>
        {children}
      </Text>
      <Group justify="flex-end" gap={8} mt="lg">
        <Button variant="default" onClick={onClose}>
          {cancelLabel}
        </Button>
        <Button color="#B03A2E" loading={busy} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
