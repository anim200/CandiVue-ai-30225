// The CandiVue AI logo, drawn from simple shapes (Style Guide, section 4).

import { Group, Text } from '@mantine/core';
import { useId } from 'react';

import classes from './Logo.module.css';

// The mark: an eye (ring + pupil) with a small spark. The numbers come from
// the 88px design; viewBox scales the drawing to any size.
// glance: the pupil moves now and then (login screen only, as designed).
// onDark: slightly brighter gradient, as on the login brand panel.
export function LogoMark({ size = 30, glance = false, onDark = false }) {
  // Each logo needs its own gradient ids: with shared ids, a logo would use
  // the gradient of another (possibly hidden) logo and render blank.
  const id = useId();
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 88 88"
      aria-hidden="true"
      style={{
        flex: 'none',
        filter: onDark
          ? 'drop-shadow(0 6px 18px rgba(0,0,0,.25))'
          : 'drop-shadow(0 1px 2px rgba(16,40,50,.25))',
      }}
    >
      <defs>
        <linearGradient id={`${id}-bg`} x1="0.25" y1="0.07" x2="0.75" y2="0.93">
          <stop offset="0" stopColor={onDark ? '#3AA0AB' : '#2E8F9A'} />
          <stop offset="0.55" stopColor="#1B5E66" />
          <stop offset="1" stopColor="#123F45" />
        </linearGradient>
        {/* thin light edge along the top, like a soft highlight */}
        <linearGradient id={`${id}-shine`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.24" />
          <stop offset="0.03" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="88" height="88" rx="25" fill={`url(#${id}-bg)`} />
      <rect width="88" height="88" rx="25" fill={`url(#${id}-shine)`} />
      <circle cx="44" cy="44" r="21.75" fill="none" stroke="#fff" strokeWidth="7.5" />
      <circle
        cx="48.4"
        cy="39.6"
        r="9"
        fill="#BDEDF1"
        className={glance ? classes.glance : undefined}
      />
      <circle cx="66.2" cy="16.9" r="8.5" fill="#123F45" />
      <circle cx="66.2" cy="16.9" r="5.5" fill="#F2C46D" />
    </svg>
  );
}

// Sizes from the design: header lockup (md) and login brand panel (lg).
const SIZES = {
  md: { mark: 30, word: 17, chip: 9, chipPad: '3px 5px', gap: 10, innerGap: 6 },
  lg: { mark: 44, word: 24, chip: 12, chipPad: '3px 6px', gap: 12, innerGap: 8 },
};

// Colours for a light background (header) and a dark one (login brand panel).
const COLORS = {
  light: { word: 'var(--cv-text)', vue: 'var(--cv-primary-text)', chip: 'var(--cv-primary-text-strong)', chipBg: 'var(--cv-primary-tint)', chipBorder: 'var(--cv-primary-border)' },
  dark: {
    word: '#FFFFFF',
    vue: '#7FD0D8',
    chip: '#BDEDF1',
    chipBg: 'rgba(255,255,255,.1)',
    chipBorder: 'rgba(255,255,255,.2)',
  },
};

// Mark + "CandiVue" + "AI" chip.
export default function Logo({ size = 'md', onDark = false, glance = false }) {
  const s = SIZES[size];
  const color = onDark ? COLORS.dark : COLORS.light;
  return (
    <Group gap={s.gap} wrap="nowrap">
      <LogoMark size={s.mark} onDark={onDark} glance={glance} />
      <Group gap={s.innerGap} wrap="nowrap">
        <Text fz={s.word} fw={700} lh={1} c={color.word} style={{ letterSpacing: '-0.025em' }}>
          Candi
          <Text span inherit c={color.vue}>
            Vue
          </Text>
        </Text>
        <Text
          span
          ff="monospace"
          fz={s.chip}
          fw={600}
          lh={1}
          c={color.chip}
          bg={color.chipBg}
          style={{
            padding: s.chipPad,
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
