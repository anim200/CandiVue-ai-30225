// Shown inside the app frame when no page matches the address.

import { Button, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';

export default function NotFoundPage() {
  return (
    <Stack align="flex-start" gap="sm">
      <Title order={1} fz={26}>
        Page not found
      </Title>
      <Text c="dimmed">The address may be wrong, or the page has moved.</Text>
      <Button component={Link} to="/jobs">
        Go to Jobs
      </Button>
    </Stack>
  );
}
