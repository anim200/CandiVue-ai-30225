// Light or dark appearance (design: UserMenu "Appearance", and a toggle icon
// on the login and candidate pages). Mantine remembers the choice in this
// browser ("candivue-theme") and all open tabs follow it.

import { ActionIcon, SegmentedControl, Tooltip, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { IconMoon, IconSun } from '@tabler/icons-react';

// The current appearance and a way to change it.
function useAppearance() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme('light');
  return [scheme, setColorScheme];
}

// In the user menu: "Appearance" with Light / Dark.
export function AppearanceSwitch() {
  const [scheme, setScheme] = useAppearance();
  return (
    <SegmentedControl
      fullWidth
      size="xs"
      value={scheme}
      onChange={setScheme}
      aria-label="Appearance"
      data={[
        { value: 'light', label: 'Light' },
        { value: 'dark', label: 'Dark' },
      ]}
    />
  );
}

// On pages without the user menu: one button that switches the appearance.
export default function ThemeToggle({ className }) {
  const [scheme, setScheme] = useAppearance();
  const dark = scheme === 'dark';
  const label = dark ? 'Switch to light appearance' : 'Switch to dark appearance';
  return (
    <Tooltip label={label} withArrow>
      <ActionIcon
        variant="default"
        radius="xl"
        size="lg"
        className={className}
        aria-label={label}
        onClick={() => setScheme(dark ? 'light' : 'dark')}
      >
        {dark ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}
