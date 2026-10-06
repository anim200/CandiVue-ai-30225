// The CandiVue AI logo, drawn from simple shapes (Style Guide, section 4).

import { Group, Text } from '@mantine/core';
import { useId } from 'react';

// The mark: an eye (ring + pupil) with a small spark. The numbers come from
// the 88px design; viewBox scales the drawing to any size.
export function LogoMark({ size = 30 }) {
  // Each logo needs its own gradient id: with a shared id, a logo would use
  // the gradient of another (possibly hidden) logo and render blank.
  const gradientId = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 88 88" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0.25" y1="0.07" x2="0.75" y2="0.93">
          <stop offset="0" stopColor="#2E8F9A" />
          <stop offset="0.55" stopColor="#1B5E66" />
          <stop offset="1" stopColor="#123F45" />
        </linearGradient>
      </defs>
      <rect width="88" height="88" rx="25" fill={`url(#${gradientId})`} />
      <circle cx="44" cy="44" r="21.75" fill="none" stroke="#fff" strokeWidth="7.5" />
      <circle cx="48.4" cy="39.6" r="9" fill="#BDEDF1" />
      <circle cx="66.2" cy="16.9" r="8.5" fill="#123F45" />
      <circle cx="66.2" cy="16.9" r="5.5" fill="#F2C46D" />
    </svg>
  );
}

// Colours for a light background (header) and a dark one (login brand panel).
const COLORS = {
  light: { word: '#1A2227', vue: '#23717A', chip: '#1C5D65', chipBg: '#EDF5F6', chipBorder: '#CFE5E8' },
  dark: {
    word: '#FFFFFF',
    vue: '#7FD0D8',
    chip: '#BDEDF1',
    chipBg: 'rgba(255,255,255,.1)',
    chipBorder: 'rgba(255,255,255,.2)',
  },
};

// Mark + "CandiVue" + "AI" chip, as used in the header.
export default function Logo({ onDark = false }) {
  const color = onDark ? COLORS.dark : COLORS.light;
  return (
    <Group gap={10} wrap="nowrap">
      <LogoMark size={30} />
      <Group gap={6} wrap="nowrap">
        <Text fz={17} fw={700} lh={1} c={color.word} style={{ letterSpacing: '-0.025em' }}>
          Candi
          <Text span inherit c={color.vue}>
            Vue
          </Text>
        </Text>
        <Text
          span
          ff="monospace"
          fz={9}
          fw={600}
          lh={1}
          c={color.chip}
          bg={color.chipBg}
          px={5}
          py={3}
          style={{
            border: `1px solid ${color.chipBorder}`,
            borderRadius: 4,
            letterSpacing: '0.08em',
          }}
        >
          AI
        </Text>
      </Group>
    </Group>
  );
}
