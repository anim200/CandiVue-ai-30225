// Shown inside the app frame when no page matches the address.

import { Button, Stack, Text, Title } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import { Link } from 'react-router';

// Shown when no page matches the address.
export default function NotFoundPage() {
  useDocumentTitle('Page not found · CandiVue AI');
  return (
    <Stack align="flex-start" gap="sm">
      <Title order={1} fz={27}>
        Page not found
      </Title>
      <Text c="dimmed">The address may be wrong, or the page has moved.</Text>
      <Button component={Link} to="/jobs">
        Go to Jobs
      </Button>
    </Stack>
  );
}
