// Badge in the header showing whether the backend can be reached.
// Checks when the page opens and then every 30 seconds.

import { Box, Loader, Tooltip } from '@mantine/core';
import { IconCheck, IconPlugConnectedX } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import { getHealth } from '../api/client';
import StatusBadge from './StatusBadge';

const CHECK_EVERY_MS = 30000;

// What the badge shows for each status. "hint" appears as a tooltip.
const STATES = {
  checking: {
    tone: 'neutral',
    icon: <Loader size={10} color="var(--cv-text-body)" />,
    label: 'Checking connection',
    hint: 'Checking whether the CandiVue server can be reached.',
  },
  connected: {
    tone: 'success',
    icon: <IconCheck size={13} />,
    label: 'Connected',
    hint: 'The CandiVue server can be reached.',
  },
  unavailable: {
    tone: 'danger',
    icon: <IconPlugConnectedX size={13} />,
    label: 'Server unavailable',
    hint: 'The server is not responding. Your data is safe. This check repeats every 30 seconds.',
  },
};

// Header badge: Checking / Connected / Server unavailable.
export default function BackendStatus() {
  const [status, setStatus] = useState('checking'); // checking | connected | unavailable

  useEffect(() => {
    let active = true; // stops updates after the component is removed

    // Ask the backend for its health once and update the badge.
    async function check() {
      try {
        await getHealth(); // fails if the backend or its database is down
        if (active) setStatus('connected');
      } catch {
        if (active) setStatus('unavailable');
      }
    }

    check();
    const timer = setInterval(check, CHECK_EVERY_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const { tone, icon, label, hint } = STATES[status];

  return (
    <Tooltip label={hint} multiline w={260}>
      <StatusBadge tone={tone} icon={icon} aria-label={label}>
        {/* On phones only the icon fits; aria-label and the tooltip keep the meaning. */}
        <Box component="span" visibleFrom="xs">
          {label}
        </Box>
      </StatusBadge>
    </Tooltip>
  );
}
