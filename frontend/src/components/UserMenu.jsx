// The signed-in interviewer in the header, with "Sign out" (design:
// Jobs.dc.html, UserMenu). Phones show only the initials; the menu itself
// always shows name and email.
// Not yet in the menu: "Appearance" (comes with dark mode) and "Help".

import { Avatar, Box, Group, Menu, Text, UnstyledButton } from '@mantine/core';
import { IconChevronDown, IconLogout } from '@tabler/icons-react';
import { useNavigate } from 'react-router';

import { clearSession, loadSession } from '../auth/session';

function initialsOf(name) {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

export default function UserMenu() {
  const navigate = useNavigate();
  const user = loadSession()?.user;
  if (!user) return null;

  function signOut() {
    clearSession();
    navigate('/login', { replace: true });
  }

  return (
    <Menu
      position="bottom-end"
      width={260}
      styles={{
        dropdown: {
          borderColor: '#DEE3E6',
          borderRadius: 8,
          padding: 6,
          boxShadow: '0 10px 30px rgba(26,34,39,.12)',
        },
      }}
    >
      <Menu.Target>
        <UnstyledButton aria-label="Account menu" px={8} py={4} style={{ borderRadius: 6 }}>
          <Group gap={10} wrap="nowrap">
            <Avatar
              size={30}
              radius="xl"
              styles={{ placeholder: { background: '#D5E9EB', color: '#1C5D65', fontSize: 12, fontWeight: 700 } }}
            >
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
            <IconChevronDown size={16} color="#66717A" />
          </Group>
        </UnstyledButton>
      </Menu.Target>

      <Menu.Dropdown>
        <Box px={10} pt={8} pb={10}>
          <Text fz={14} fw={600}>
            {user.name}
          </Text>
          <Text fz={12} c="dimmed">
            {user.email}
          </Text>
        </Box>
        <Menu.Divider />
        <Menu.Item
          h={36}
          fz={14}
          leftSection={<IconLogout size={17} />}
          onClick={signOut}
          styles={{ item: { color: '#932E24' } }}
        >
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
