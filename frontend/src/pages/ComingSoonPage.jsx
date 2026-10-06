// Placeholder for a menu item whose screen is built in a later module.

import { Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconTools } from '@tabler/icons-react';

export default function ComingSoonPage({ title, description }) {
  return (
    <Stack gap="lg">
      <Title order={1} fz={26}>
        {title}
      </Title>
      <Paper withBorder radius="md" p="xl">
        <Stack align="center" gap="xs" py="xl">
          <ThemeIcon variant="light" size={48} radius="xl">
            <IconTools size={26} />
          </ThemeIcon>
          <Text fw={600}>This screen is not built yet</Text>
          <Text c="dimmed" ta="center" maw={420}>
            {description}
          </Text>
        </Stack>
      </Paper>
    </Stack>
  );
}
