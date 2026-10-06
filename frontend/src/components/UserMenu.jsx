// The signed-in interviewer in the header, with "Sign out" (design:
// Jobs.dc.html, UserMenu and frame 2d "User menu open"). Phones show only
// the initials; the menu itself always shows name and email.
// Not yet in the menu: "Appearance" (comes with dark mode) and "Help"
// (no help page yet).

import { Avatar, Box, Group, Menu, Text, UnstyledButton } from '@mantine/core';
import { IconChevronDown, IconChevronUp, IconLogout } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { clearSession, loadSession } from '../auth/session';
import classes from './UserMenu.module.css';

// Opening animation from the design ("cvpop", 0.2s ease-out).
const POP = {
  in: { opacity: 1, transform: 'none' },
  out: { opacity: 0, transform: 'scale(.97) translateY(8px)' },
  common: { transformOrigin: 'top right' },
  transitionProperty: 'opacity, transform',
};

// Turn a name into up to two initials, e.g. "Interviewer A" -> "IA".
function initialsOf(name) {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

// Avatar button in the header that opens the account menu.
export default function UserMenu() {
  const navigate = useNavigate();
  const [opened, setOpened] = useState(false);
  const user = loadSession()?.user;
  if (!user) return null;

  // Sign out of this tab and go to the login page.
  function signOut() {
    clearSession();
    navigate('/login', { replace: true });
  }

  const Chevron = opened ? IconChevronUp : IconChevronDown;

  return (
    <Menu
      opened={opened}
      onChange={setOpened}
      position="bottom-end"
      width={260}
      transitionProps={{ transition: POP, duration: 200, timingFunction: 'ease-out' }}
      classNames={{ dropdown: classes.dropdown, item: classes.item }}
    >
      <Menu.Target>
        <UnstyledButton aria-label="Account menu" className={classes.target}>
          <Group gap={10} wrap="nowrap">
            <Avatar size={30} radius="xl" classNames={{ placeholder: classes.avatar }}>
              {initialsOf(user.name)}
            </Avatar>
            <Box visibleFrom="sm" style={{ lineHeight: 1.2 }}>
              <Text fz={14} fw={600} lh={1.2}>
                {user.name}
              </Text>
              <Text fz={12} c="dimmed" lh={1.2}>
                {user.email}
              </Text>
            </Box>
            <Chevron size={16} color="#66717A" />
          </Group>
        </UnstyledButton>
      </Menu.Target>

      <Menu.Dropdown>
        <div className={classes.who}>
          <Text fz={14} fw={600}>
            {user.name}
          </Text>
          <Text fz={12} c="dimmed">
            {user.email}
          </Text>
        </div>
        <Menu.Item
          className={classes.signOut}
          leftSection={<IconLogout size={17} />}
          onClick={signOut}
        >
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
