// Interviewer sign-in (design: Login.dc.html). Candidates never sign in here:
// they use the private link in their invitation email.
// Responsive: phones and tablets show only the form; desktops also show the
// brand panel on the left.

import {
  Alert,
  Box,
  Button,
  Center,
  Group,
  Paper,
  PasswordInput,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconClock } from '@tabler/icons-react';
import { useState } from 'react';
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router';

import { apiPost } from '../api/client';
import { clearSession, loadSession, saveSession } from '../auth/session';
import Logo from '../components/Logo';

// Placeholder positioning from the design; to be replaced by the trainee's
// own positioning statement (product naming deliverable, E6).
const HEADLINE = 'Hiring decisions, backed by evidence.';
const INTRO =
  'CandiVue AI screens CVs, captures interviews and drafts assessments. ' +
  'You review every result and make every decision.';
const PRINCIPLES = [
  'Every score links to a CV excerpt or transcript moment',
  'Nobody is hired or rejected automatically',
  'Candidates join by private link and never see scores',
];

function BrandPanel() {
  return (
    <Stack
      visibleFrom="md"
      justify="space-between"
      p={48}
      style={{
        background: 'radial-gradient(120% 90% at 20% 0%, #1E6670 0%, #123F45 55%, #0B2A2F 100%)',
      }}
    >
      <Logo onDark />
      <Stack gap="lg" maw={460}>
        <Title order={1} fz={36} lh={1.2} c="white">
          {HEADLINE}
        </Title>
        <Text c="rgba(255,255,255,.75)" fz={16} lh={1.6}>
          {INTRO}
        </Text>
        <Stack gap="sm">
          {PRINCIPLES.map((principle) => (
            <Group key={principle} gap="sm" wrap="nowrap">
              <ThemeIcon size={22} radius="xl" color="rgba(255,255,255,.12)">
                <IconCheck size={14} color="#7FD0D8" />
              </ThemeIcon>
              <Text c="white" fz={14}>
                {principle}
              </Text>
            </Group>
          ))}
        </Stack>
      </Stack>
      <Text c="rgba(255,255,255,.55)" fz={12}>
        Demo environment · synthetic sample data only
      </Text>
    </Stack>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailError, setEmailError] = useState(null);
  const [error, setError] = useState(null);
  const [signingIn, setSigningIn] = useState(false);

  // Already signed in as an interviewer: nothing to do here.
  if (loadSession()?.user.role === 'interviewer') {
    return <Navigate to="/jobs" replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!email.includes('@')) {
      setEmailError('Enter a full email address, like name@example.com');
      return;
    }
    setEmailError(null);
    setError(null);
    setSigningIn(true);
    clearSession(); // signing in replaces any older session in this tab
    try {
      const result = await apiPost('/auth/login', { email, password });
      saveSession({ token: result.access_token, user: result.user });
      navigate(location.state?.from ?? '/jobs', { replace: true });
    } catch (err) {
      setError(err.message);
      setSigningIn(false);
    }
  }

  return (
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing={0} mih="100vh">
      <BrandPanel />

      <Center bg="white" px={{ base: 'md', sm: 'xl' }} py="xl">
        <Stack w="100%" maw={380} gap="lg">
          <Box hiddenFrom="md">
            <Logo />
          </Box>

          <div>
            <Title order={1} fz={26}>
              Welcome back
            </Title>
            <Text c="dimmed">Sign in to your interviewer account</Text>
          </div>

          {searchParams.get('expired') && !error && (
            <Alert color="blue" icon={<IconClock size={18} />}>
              Your session has expired. Please sign in again.
            </Alert>
          )}
          {error && (
            <Alert color="red" icon={<IconAlertTriangle size={18} />}>
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <Stack gap="md">
              <TextInput
                label="Email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.currentTarget.value)}
                error={emailError}
                required
              />
              <PasswordInput
                label="Password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.currentTarget.value)}
                required
              />
              <Button type="submit" size="md" fullWidth loading={signingIn}>
                Sign in
              </Button>
            </Stack>
          </form>

          <Paper withBorder radius="md" p="md" bg="#F5F7F8">
            <Text fz={14} fw={600}>
              Are you a candidate?
            </Text>
            <Text fz={14} c="dimmed">
              You don&apos;t need an account. Join using the private link in your invitation email.
            </Text>
          </Paper>
        </Stack>
      </Center>
    </SimpleGrid>
  );
}
