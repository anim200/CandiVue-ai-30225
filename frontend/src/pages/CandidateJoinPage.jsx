// Where the private link in the invitation email leads: /join/<link token>.
// Swaps the link for a candidate session in this tab (design: Candidate
// Join.dc.html, states 3a, 3e, 3i and 3j); a working link opens the
// interview steps (welcome, device check, the call: CandidateInterview).
// No account, no scores: candidates only ever see their own interview (N9).

import { Anchor, Box, Button, Stack, Text } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import { IconAlertCircle, IconCircleCheck, IconCloudOff, IconHelpCircle } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router';

import { apiPost } from '../api/client';
import { clearSession, saveSession } from '../auth/session';
import Logo from '../components/Logo';
import { HELP_EMAIL } from '../config';
import classes from './CandidateJoinPage.module.css';
import CandidateInterview from './interview/CandidateInterview';

// Icon circle colours from the design frames.
const RED = { bg: '#FBE9E7', color: '#B03A2E' };
const GREEN = { bg: '#E7F3EC', color: '#2D7A4E' };

// What to show for each result of the link check (wording from the design).
function messageFor(result) {
  if (result.httpStatus === 404) {
    return {
      icon: IconAlertCircle,
      tint: RED,
      title: 'We don’t recognise this link',
      text: 'Open the link straight from your invitation email. Copying it by hand can miss characters.',
    };
  }
  if (result.httpStatus === 410) {
    return {
      icon: IconCircleCheck,
      tint: GREEN,
      title: 'The interview has ended',
      text: 'Thank you for your time. The team will contact you by email about next steps. You can close this tab.',
    };
  }
  return {
    icon: IconCloudOff,
    tint: RED,
    title: 'We couldn’t connect you',
    text: 'Check your internet connection and try again. Your interview slot is kept.',
    canRetry: true,
  };
}

// White card used for every state of the link page.
function StateCard({ children }) {
  return (
    <Box
      bg="white"
      w="100%"
      maw={400}
      px={24}
      py={28}
      style={{ border: '1px solid #DEE3E6', borderRadius: 8 }}
    >
      <Stack align="center" gap={10} ta="center">
        {children}
      </Stack>
    </Box>
  );
}

// Check the invitation link and show the result to the candidate.
export default function CandidateJoinPage() {
  const { linkToken } = useParams();
  const [result, setResult] = useState({ status: 'checking' }); // checking | joined | failed
  const [attempt, setAttempt] = useState(0); // "Try again" checks the link once more
  // The interview ended: show the "has ended" message (one stable function,
  // so the interview steps do not restart on every render).
  const showEnded = useCallback(() => setResult({ status: 'failed', httpStatus: 410 }), []);
  useDocumentTitle('Your interview · CandiVue AI');

  useEffect(() => {
    let active = true; // ignore the answer if the page was left meanwhile
    setResult({ status: 'checking' });
    clearSession(); // a link always starts a fresh candidate session
    apiPost('/auth/candidate', { link_token: linkToken })
      .then((answer) => {
        if (!active) return;
        saveSession({ token: answer.access_token, user: answer.user });
        setResult({ status: 'joined' });
      })
      .catch((error) => {
        if (active) setResult({ status: 'failed', httpStatus: error.status });
      });
    return () => {
      active = false;
    };
  }, [linkToken, attempt]);

  const message = result.status === 'checking' ? null : messageFor(result);
  const Icon = message?.icon;

  return (
    <Box mih="100vh" bg="#F5F7F8">
      <header className={classes.header}>
        <Logo />
        <span className={classes.help}>
          <Anchor href={`mailto:${HELP_EMAIL}`} fz={14} className={classes.helpShort}>
            <IconHelpCircle size={16} />
            Help
          </Anchor>
          <span className={classes.helpFull}>
            Need help?{' '}
            <Anchor href={`mailto:${HELP_EMAIL}`} fz={14}>
              {HELP_EMAIL}
            </Anchor>
          </span>
        </span>
      </header>

      <Box px={{ base: 16, sm: 24 }} py={40} style={{ display: 'flex', justifyContent: 'center' }}>
        {result.status === 'joined' ? (
          <CandidateInterview onEnded={showEnded} />
        ) : result.status === 'checking' ? (
          <StateCard>
            <span className={classes.spinner} />
            <Text fz={17} fw={600}>
              Opening your interview…
            </Text>
          </StateCard>
        ) : (
          <StateCard>
            <Box
              w={48}
              h={48}
              bg={message.tint.bg}
              c={message.tint.color}
              style={{ borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <Icon size={24} />
            </Box>
            <Text fz={18} fw={600}>
              {message.title}
            </Text>
            <Text fz={15} lh={1.55} c="#48535B">
              {message.text}
            </Text>
            {message.canRetry && (
              <Button mt={4} onClick={() => setAttempt((count) => count + 1)}>
                Try again
              </Button>
            )}
          </StateCard>
        )}
      </Box>
    </Box>
  );
}
