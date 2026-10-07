// Colours and fonts from the design handoff
// (docs/design_handoff_candivue_ui/README.md, "Design Tokens").
// Deliberate change (user, 07-10-2026): every font size is 1px larger than
// the design for easier reading.

import { createTheme, rem } from '@mantine/core';

// The brand colour "harbor", from lightest (0) to darkest (9).
const harbor = [
  '#EDF5F6', '#D5E9EB', '#A9D2D6', '#7CBAC1', '#4FA2AB',
  '#2F8A94', '#23717A', '#1C5D65', '#164A51', '#103A40',
];

export const theme = createTheme({
  primaryColor: 'harbor',
  primaryShade: { light: 6, dark: 4 },
  colors: { harbor },
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
// the design uses a darker grey (contrast 4.9:1).
export const cssVariablesResolver = () => ({
  variables: {},
  light: { '--mantine-color-dimmed': '#66717A' },
  dark: {},
});
