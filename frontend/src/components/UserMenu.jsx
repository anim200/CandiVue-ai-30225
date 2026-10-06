// The signed-in interviewer in the header, with "Sign out".
// Phones show only the initials; the menu itself always shows name and email.

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
    <Menu position="bottom-end" width={240} shadow="md">
      <Menu.Target>
        <UnstyledButton aria-label="Account menu">
          <Group gap={8} wrap="nowrap">
            <Avatar size={30} radius="xl" color="harbor">
              {initialsOf(user.name)}
            </Avatar>
            <Box visibleFrom="sm">
              <Text fz={14} fw={600} lh={1.2}>
                {user.name}
              </Text>
              <Text fz={12} c="dimmed" lh={1.2}>
                {user.email}
              </Text>
            </Box>
            <IconChevronDown size={14} />
          </Group>
        </UnstyledButton>
      </Menu.Target>

      <Menu.Dropdown>
        <Box px="sm" py={6}>
          <Text fz={14} fw={600}>
            {user.name}
          </Text>
          <Text fz={12} c="dimmed">
            {user.email}
          </Text>
        </Box>
        <Menu.Divider />
        <Menu.Item color="red" leftSection={<IconLogout size={16} />} onClick={signOut}>
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
