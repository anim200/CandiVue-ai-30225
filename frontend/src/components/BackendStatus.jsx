// Badge in the header showing whether the backend can be reached.
// Checks when the page opens and then every 30 seconds.

import { Badge, Loader, Tooltip } from '@mantine/core';
import { IconCheck, IconPlugConnectedX } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import { getHealth } from '../api/client';

const CHECK_EVERY_MS = 30000;

export default function BackendStatus() {
  const [status, setStatus] = useState('checking'); // checking | connected | unavailable

  useEffect(() => {
    let active = true; // stops updates after the component is removed

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

  if (status === 'checking') {
    return (
      <Badge variant="light" color="gray" tt="none" leftSection={<Loader size={10} color="gray" />}>
        Checking connection
      </Badge>
    );
  }

  if (status === 'connected') {
    return (
      <Badge variant="light" color="green" tt="none" leftSection={<IconCheck size={14} />}>
        Connected
      </Badge>
    );
  }

  return (
    <Tooltip label="The server is not responding. Your data is safe. This check repeats every 30 seconds.">
      <Badge variant="light" color="red" tt="none" leftSection={<IconPlugConnectedX size={14} />}>
        Server unavailable
      </Badge>
    </Tooltip>
  );
}
