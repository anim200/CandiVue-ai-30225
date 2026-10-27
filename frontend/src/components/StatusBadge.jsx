// A status badge in the design's colours (handoff README, "Semantic" and
// "Badges"): colour + icon + word, never colour alone. Used for run status,
// connection status, review status and so on.

import { Badge } from '@mantine/core';

// Tint background and text colour per tone, from the design tokens.
export const TONES = {
  neutral: { bg: 'var(--cv-muted)', color: 'var(--cv-text-body)' },
  info: { bg: 'var(--cv-info-tint)', color: 'var(--cv-info-text-strong)' },
  success: { bg: 'var(--cv-success-tint)', color: 'var(--cv-success-text-strong)' },
  warning: { bg: 'var(--cv-warning-tint)', color: 'var(--cv-warning-text)' },
  danger: { bg: 'var(--cv-danger-tint)', color: 'var(--cv-danger-text-strong)' },
  harbor: { bg: 'var(--cv-primary-tint)', color: 'var(--cv-primary-text-strong)' },
};

// A rounded status badge with an icon, in the tone's design colours.
export default function StatusBadge({ tone = 'neutral', icon, children, ...props }) {
  const { bg, color } = TONES[tone];
  return (
    <Badge
      h={22}
      radius="xl"
      tt="none"
      fz={13}
      fw={600}
      leftSection={icon}
      styles={{ root: { background: bg, color } }}
      {...props}
    >
      {children}
    </Badge>
  );
}
