// Colours and fonts from the design handoff
// (docs/design_handoff_candivue_ui/README.md, "Design Tokens").

import { createTheme } from '@mantine/core';

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
  headings: { fontWeight: '600' },
});

// Mantine's default grey for c="dimmed" is too light to read comfortably;
// the design uses a darker grey (contrast 4.9:1).
export const cssVariablesResolver = () => ({
  variables: {},
  light: { '--mantine-color-dimmed': '#66717A' },
  dark: {},
});
