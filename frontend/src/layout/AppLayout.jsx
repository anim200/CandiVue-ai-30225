// The frame around every interviewer page: header on top, menu on the left,
// the current page in the middle (<Outlet />).
// Responsive: on phones and tablets (below "md", 992px) the menu is hidden
// and opens from the burger button, so pages get the full width.
// Menu style (deliberate change from the design, user 07-10-2026): section
// titles, a teal bar on the active item, a count of jobs that need the
// interviewer, and a reminder card at the bottom.
// Pages may ask for an icon rail (64px) or no menu at all ("immersive": the
// live interview, whose left column shows the CV; the burger still opens
// the menu on phones and tablets).

import { AppShell, Box, Burger, Group, NavLink, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconShieldCheck } from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { Link, Outlet, useLocation, useMatches } from 'react-router';

import { apiGet } from '../api/client';
import BackendStatus from '../components/BackendStatus';
import Logo from '../components/Logo';
import UserMenu from '../components/UserMenu';
import { STAGES } from '../pages/assistant/labels';
import classes from './AppLayout.module.css';
import { NAV_ITEMS } from './navigation';

// The menu items grouped by section, in menu order: [["Workspace", [...]], ...]
const GROUPS = Object.entries(Object.groupBy(NAV_ITEMS, (item) => item.group));

// How many jobs wait for the interviewer (JD to approve, post to confirm,
// posting failed). Re-checked whenever the page changes.
function useJobsNeedingAttention(pathname) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let current = true;
    apiGet('/jobs')
      .then((jobs) => current && setCount(jobs.filter((job) => STAGES[job.stage]?.attention).length))
      .catch(() => {}); // the badge is a hint only; the page shows its own errors
    return () => {
      current = false;
    };
  }, [pathname]);
  return count;
}

// Page frame for interviewers: header, left menu and the current page.
export default function AppLayout() {
  const { pathname } = useLocation();
  // Pages marked fullBleed (the Hiring Assistant) fill the area without padding.
  const matches = useMatches();
  const fullBleed = matches.some((match) => match.handle?.fullBleed);
  const [menuOpen, { toggle: toggleMenu, close: closeMenu }] = useDisclosure(false);
  // Icons only (rail) on pages that ask for it, unless the phone menu is open.
  const rail = matches.some((match) => match.handle?.rail) && !menuOpen;
  const immersive = matches.some((match) => match.handle?.immersive);
  const waiting = useJobsNeedingAttention(pathname);

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: rail ? 64 : 240, breakpoint: 'md', collapsed: { mobile: !menuOpen, desktop: immersive } }}
    >
      <AppShell.Header px={{ base: 12, sm: 20 }}>
        <Group h="100%" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={menuOpen}
              onClick={toggleMenu}
              hiddenFrom="md"
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

      <AppShell.Navbar className={`${classes.navbar} ${rail ? classes.rail : ''}`}>
        <nav className={classes.menu} aria-label="Main menu">
          {GROUPS.map(([group, items]) => (
            <div key={group} className={classes.group}>
              {!rail && <div className={classes.sectionTitle}>{group}</div>}
              {items.map(({ path, label, icon: Icon }) => {
                const count = path === '/assistant' && !rail ? waiting : 0;
                return (
                  <Tooltip key={path} label={label} position="right" disabled={!rail}>
                    <NavLink
                      component={Link}
                      to={path}
                      label={rail ? null : label}
                      aria-label={label}
                      leftSection={<Icon size={19} stroke={1.6} />}
                      rightSection={
                        count > 0 && (
                          <span className={classes.count} title={`${count} job(s) need you`}>
                            {count}
                          </span>
                        )
                      }
                      active={path === '/' ? pathname === '/' : pathname.startsWith(path)}
                      classNames={{ root: classes.navLink, section: classes.navIcon }}
                      onClick={closeMenu} // on phones, close the menu after choosing
                    />
                  </Tooltip>
                );
              })}
            </div>
          ))}
        </nav>

        {!rail && (
          <div className={classes.footerCard}>
            <IconShieldCheck size={18} className={classes.footerIcon} />
            <div>
              <div className={classes.footerTitle}>You stay in control</div>
              Nothing is posted or sent until you confirm. Candidates never see scores or
              reports.
            </div>
          </div>
        )}
      </AppShell.Navbar>

      <AppShell.Main bg="var(--cv-page)">
        <Box px={fullBleed ? 0 : { base: 16, sm: 32 }} py={fullBleed ? 0 : { base: 16, sm: 24 }}>
          <Outlet />
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}
