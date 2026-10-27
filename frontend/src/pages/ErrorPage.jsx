// Shown when a page crashes. Plain language only: no error codes, stack
// traces or file paths reach the user (N12, N25).

import { Button, Center, Stack, Text, Title } from '@mantine/core';

// Friendly full-page message when a page crashes, with a reload button.
export default function ErrorPage() {
  return (
    <Center h="100vh" bg="var(--cv-page)">
      <Stack align="center" gap="sm" maw={440} ta="center">
        <Title order={1} fz={27}>
          Something went wrong
        </Title>
        <Text c="dimmed">
          This page could not be shown. Your data is safe. Reload the page to try again.
        </Text>
        <Button onClick={() => window.location.reload()}>Reload page</Button>
      </Stack>
    </Center>
  );
}
