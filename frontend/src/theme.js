// Colours and fonts from the design handoff
// (docs/design_handoff_candivue_ui/README.md, "Design Tokens" and "Dark
// mode"). The colours of our own CSS are tokens in styles/tokens.css.
// Deliberate change (user, 07-10-2026): every font size is 1px larger than
// the design for easier reading.

import { createTheme, rem } from '@mantine/core';

// The brand colour "harbor", from lightest (0) to darkest (9).
const harbor = [
  '#EDF5F6', '#D5E9EB', '#A9D2D6', '#7CBAC1', '#4FA2AB',
  '#2F8A94', '#23717A', '#1C5D65', '#164A51', '#103A40',
];

// Mantine's greys for dark mode, from the design's dark colours: text
// (0-3), borders (4-5), surface (6), page (7) and deeper backgrounds.
const dark = [
  '#E6ECEE', '#C2CCD0', '#A3AFB4', '#8E9AA1', '#3A464C',
  '#2B353A', '#1A2226', '#12181B', '#0E1416', '#0B1012',
];

export const theme = createTheme({
  primaryColor: 'harbor',
  primaryShade: { light: 6, dark: 4 },
  colors: { harbor, dark },
  black: '#1A2227', // main text colour ("ink")
  fontFamily: "'Public Sans', system-ui, sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', monospace",
  defaultRadius: 'sm', // 4px for buttons and inputs; cards use radius="md"
  // Mantine's sizes (12/14/16/18/20) plus 1px; used by buttons, inputs, Text.
  fontSizes: { xs: rem(13), sm: rem(15), md: rem(17), lg: rem(19), xl: rem(21) },
  headings: {
    fontWeight: '600',
    sizes: {
      h1: { fontSize: rem(35) },
      h2: { fontSize: rem(27) },
      h3: { fontSize: rem(23) },
      h4: { fontSize: rem(19) },
      h5: { fontSize: rem(17) },
      h6: { fontSize: rem(15) },
    },
  },
});

// Mantine's default grey for c="dimmed" is too light to read comfortably;
// the design uses a darker grey (contrast 4.9:1). In dark mode: the
// design's dimmed text, page background and borders, and its teal tint for
// light buttons. Deliberate change: filled teal buttons keep the darker teal
// (harbor 6) in dark mode, because white text on the design's lighter dark
// teal (harbor 4) is too faint to read (about 3:1; 5.4:1 on harbor 6).
export const cssVariablesResolver = () => ({
  variables: {},
  light: { '--mantine-color-dimmed': '#66717A' },
  dark: {
    '--mantine-color-dimmed': '#A3AFB4',
    '--mantine-color-body': '#12181B',
    '--mantine-color-default-border': '#2B353A',
    '--mantine-color-harbor-filled': '#23717A',
    '--mantine-color-harbor-filled-hover': '#1C5D65',
    '--mantine-color-harbor-light': '#1C3A3E',
    '--mantine-color-harbor-light-hover': '#24474C',
    '--mantine-color-harbor-light-color': '#7FD0D8',
  },
});
