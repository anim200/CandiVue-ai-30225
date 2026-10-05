// The frame around every interviewer page: header on top, menu on the left,
// the current page in the middle (<Outlet />).

import { AppShell, Box, Divider, Group, NavLink } from '@mantine/core';
import { Fragment } from 'react';
import { Link, Outlet, useLocation } from 'react-router';

import BackendStatus from '../components/BackendStatus';
import Logo from '../components/Logo';
import { NAV_ITEMS } from './navigation';

export default function AppLayout() {
  const { pathname } = useLocation();

  return (
    // Desktop-first (1280px+): below the "sm" breakpoint the menu is hidden.
    <AppShell header={{ height: 56 }} navbar={{ width: 240, breakpoint: 'sm' }}>
      <AppShell.Header px={20}>
        <Group h="100%" justify="space-between">
          <Logo />
          <BackendStatus />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar px={12} py={16}>
        {NAV_ITEMS.map(({ path, label, icon: Icon, dividerBefore }) => (
          <Fragment key={path}>
            {dividerBefore && <Divider my="sm" />}
            <NavLink
              component={Link}
              to={path}
              label={label}
              leftSection={<Icon size={19} stroke={1.6} />}
              active={pathname.startsWith(path)}
            />
          </Fragment>
        ))}
      </AppShell.Navbar>

      <AppShell.Main bg="#F5F7F8">
        <Box px={32} py={24}>
          <Outlet />
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}
