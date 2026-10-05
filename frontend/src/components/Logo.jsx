// The CandiVue AI logo, drawn from simple shapes (Style Guide, section 4).

import { Group, Text } from '@mantine/core';

// The mark: an eye (ring + pupil) with a small spark. The numbers come from
// the 88px design; viewBox scales the drawing to any size.
export function LogoMark({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 88 88" aria-hidden="true">
      <defs>
        <linearGradient id="cv-logo-bg" x1="0.25" y1="0.07" x2="0.75" y2="0.93">
          <stop offset="0" stopColor="#2E8F9A" />
          <stop offset="0.55" stopColor="#1B5E66" />
          <stop offset="1" stopColor="#123F45" />
        </linearGradient>
      </defs>
      <rect width="88" height="88" rx="25" fill="url(#cv-logo-bg)" />
      <circle cx="44" cy="44" r="21.75" fill="none" stroke="#fff" strokeWidth="7.5" />
      <circle cx="48.4" cy="39.6" r="9" fill="#BDEDF1" />
      <circle cx="66.2" cy="16.9" r="8.5" fill="#123F45" />
      <circle cx="66.2" cy="16.9" r="5.5" fill="#F2C46D" />
    </svg>
  );
}

// Mark + "CandiVue" + "AI" chip, as used in the header.
export default function Logo() {
  return (
    <Group gap={10} wrap="nowrap">
      <LogoMark size={30} />
      <Group gap={6} wrap="nowrap">
        <Text fz={17} fw={700} lh={1} style={{ letterSpacing: '-0.025em' }}>
          Candi
          <Text span inherit c="harbor.6">
            Vue
          </Text>
        </Text>
        <Text
          span
          ff="monospace"
          fz={9}
          fw={600}
          lh={1}
          c="harbor.7"
          bg="harbor.0"
          px={5}
          py={3}
          style={{ border: '1px solid #CFE5E8', borderRadius: 4, letterSpacing: '0.08em' }}
        >
          AI
        </Text>
      </Group>
    </Group>
  );
}
