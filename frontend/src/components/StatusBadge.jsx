// A status badge in the design's colours (handoff README, "Semantic" and
// "Badges"): colour + icon + word, never colour alone. Used for run status,
// connection status, review status and so on.

import { Badge } from '@mantine/core';

// Tint background and text colour per tone, from the design tokens.
export const TONES = {
  neutral: { bg: '#EEF1F3', color: '#3E484F' },
  info: { bg: '#E7EEF9', color: '#234E8B' },
  success: { bg: '#E7F3EC', color: '#245F3E' },
  warning: { bg: '#FBF0D9', color: '#7A5000' },
  danger: { bg: '#FBE9E7', color: '#932E24' },
  harbor: { bg: '#EDF5F6', color: '#1C5D65' },
};

// A rounded status badge with an icon, in the tone's design colours.
export default function StatusBadge({ tone = 'neutral', icon, children, ...props }) {
  const { bg, color } = TONES[tone];
  return (
    <Badge
      h={22}
      radius="xl"
      tt="none"
      fz={12}
      fw={600}
      leftSection={icon}
      styles={{ root: { background: bg, color } }}
      {...props}
    >
      {children}
    </Badge>
  );
}
