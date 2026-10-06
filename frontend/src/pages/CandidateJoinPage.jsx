// Where the private link in the invitation email leads: /join/<link token>.
// Swaps the link for a candidate session in this tab. The real candidate
// screens (consent, device check, the call) are built with F3/F7.
// No account, no scores: candidates only ever see their own interview (N9).

import { Alert, Box, Center, Loader, Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconAlertTriangle, IconCheck } from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router';

import { apiPost } from '../api/client';
import { clearSession, saveSession } from '../auth/session';
import Logo from '../components/Logo';

export default function CandidateJoinPage() {
  const { linkToken } = useParams();
  const [result, setResult] = useState({ status: 'checking' }); // checking | joined | failed

  useEffect(() => {
    let active = true; // ignore the answer if the page was left meanwhile
    clearSession(); // a link always starts a fresh candidate session
    apiPost('/auth/candidate', { link_token: linkToken })
      .then((answer) => {
        if (!active) return;
        saveSession({ token: answer.access_token, user: answer.user });
        setResult({ status: 'joined' });
      })
      .catch((error) => {
        if (active) setResult({ status: 'failed', message: error.message });
      });
    return () => {
      active = false;
    };
  }, [linkToken]);

  return (
    <Box mih="100vh" bg="#F5F7F8">
      <Box bg="white" px={{ base: 'md', sm: 'xl' }} py="md" style={{ borderBottom: '1px solid #DEE3E6' }}>
        <Logo />
      </Box>

      <Center px="md" py={{ base: 'xl', sm: 64 }}>
        <Paper withBorder radius="md" p={{ base: 'lg', sm: 'xl' }} w="100%" maw={620}>
          {result.status === 'checking' && (
            <Stack align="center" gap="sm" py="lg">
              <Loader />
              <Text c="dimmed">Checking your interview link…</Text>
            </Stack>
          )}

          {result.status === 'joined' && (
            <Stack align="center" gap="sm" ta="center" py="lg">
              <ThemeIcon size={48} radius="xl" color="green" variant="light">
                <IconCheck size={26} />
              </ThemeIcon>
              <Title order={1} fz={24}>
                Your interview link works
              </Title>
              <Text c="dimmed" maw={460}>
                On the day of your interview, this page will help you check your camera and
                microphone and join the call. You don&apos;t need an account.
              </Text>
            </Stack>
          )}

          {result.status === 'failed' && (
            <Stack gap="md">
              <Title order={1} fz={24}>
                We couldn&apos;t open your interview
              </Title>
              <Alert color="red" icon={<IconAlertTriangle size={18} />}>
                {result.message}
              </Alert>
              <Text c="dimmed" fz={14}>
                If you think this is a mistake, contact the person who invited you.
              </Text>
            </Stack>
          )}
        </Paper>
      </Center>
    </Box>
  );
}
