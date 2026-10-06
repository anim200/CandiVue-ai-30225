// The frame around every interviewer page: header on top, menu on the left,
// the current page in the middle (<Outlet />).
// Responsive: on phones and small tablets (below "sm", 768px) the menu is
// hidden and opens from the burger button in the header.

import { AppShell, Box, Burger, Group, NavLink } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Fragment } from 'react';
import { Link, Outlet, useLocation, useMatches } from 'react-router';

import BackendStatus from '../components/BackendStatus';
import Logo from '../components/Logo';
import UserMenu from '../components/UserMenu';
import classes from './AppLayout.module.css';
import { NAV_ITEMS } from './navigation';

// Page frame for interviewers: header, left menu and the current page.
export default function AppLayout() {
  const { pathname } = useLocation();
  // Pages marked fullBleed (the Hiring Assistant) fill the area without padding.
  const fullBleed = useMatches().some((match) => match.handle?.fullBleed);
  const [menuOpen, { toggle: toggleMenu, close: closeMenu }] = useDisclosure(false);

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !menuOpen } }}
    >
      <AppShell.Header px={{ base: 12, sm: 20 }}>
        <Group h="100%" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={menuOpen}
              onClick={toggleMenu}
              hiddenFrom="sm"
              size="sm"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            />
            <Logo />
          </Group>
          <Group gap="md" wrap="nowrap">
            <BackendStatus />
            <UserMenu />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar px={12} py={16} style={{ gap: 2 }}>
        {NAV_ITEMS.map(({ path, label, icon: Icon, dividerBefore }) => (
          <Fragment key={path}>
            {dividerBefore && <div className={classes.divider} />}
            <NavLink
              component={Link}
              to={path}
              label={label}
              leftSection={<Icon size={19} stroke={1.6} />}
              active={pathname.startsWith(path)}
              classNames={{ root: classes.navLink, section: classes.navIcon }}
              onClick={closeMenu} // on phones, close the menu after choosing
            />
          </Fragment>
        ))}
      </AppShell.Navbar>

      <AppShell.Main bg="#F5F7F8">
        <Box px={fullBleed ? 0 : { base: 16, sm: 32 }} py={fullBleed ? 0 : { base: 16, sm: 24 }}>
          <Outlet />
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}
