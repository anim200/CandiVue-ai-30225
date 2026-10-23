// Where the private link in the invitation email leads: /join/<link token>.
// Opening it emails a one-time code to the candidate's address; the link
// with that code gives a candidate session in this tab (a forwarded link
// alone is not enough). A reload in the same tab keeps the session. Then
// the interview steps follow (CandidateInterview). Design: Candidate
// Join.dc.html, states 3a, 3e, 3i and 3j; the code step is an addition.
// No account, no scores: candidates only ever see their own interview (N9).

import { Anchor, Box, Button, PinInput, Stack, Text } from '@mantine/core';
import { useDocumentTitle } from '@mantine/hooks';
import {
  IconAlertCircle,
  IconCircleCheck,
  IconCloudOff,
  IconHelpCircle,
  IconMailOpened,
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router';

import { apiPost } from '../api/client';
import { clearSession, loadSession, saveSession } from '../auth/session';
import Logo from '../components/Logo';
import ThemeToggle from '../components/ThemeToggle';
import { HELP_EMAIL } from '../config';
import classes from './CandidateJoinPage.module.css';
import CandidateInterview from './interview/CandidateInterview';

// Icon circle colours from the design frames.
const RED = { bg: 'var(--cv-danger-tint)', color: 'var(--cv-danger-text)' };
const GREEN = { bg: 'var(--cv-success-tint)', color: 'var(--cv-success-text)' };
const TEAL = { bg: 'var(--cv-primary-tint)', color: 'var(--cv-primary-text)' };

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
    text: result.message || 'Check your internet connection and try again. Your interview slot is kept.',
    canRetry: true,
  };
}

// White card used for every state of the link page.
function StateCard({ children }) {
  return (
    <Box bg="var(--cv-surface)" w="100%" maw={420} px={24} py={28} style={{ border: '1px solid var(--cv-border)', borderRadius: 8 }}>
      <Stack align="center" gap={10} ta="center">
        {children}
      </Stack>
    </Box>
  );
}

// A round icon in a tint.
function StateIcon({ icon: Icon, tint }) {
  return (
    <Box
      w={48}
      h={48}
      bg={tint.bg}
      c={tint.color}
      style={{ borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <Icon size={24} />
    </Box>
  );
}

// "Enter the code we emailed": six digits, checked when complete.
function CodeStep({ linkToken, sent, onJoined, onResend }) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [wait, setWait] = useState(sent.resend_in);

  useEffect(() => setWait(sent.resend_in), [sent]);
  useEffect(() => {
    if (wait <= 0) return undefined;
    const timer = setTimeout(() => setWait((left) => left - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  // Send the code; a wrong one says how many tries are left.
  async function verify(value) {
    setBusy(true);
    setError(null);
    try {
      onJoined(await apiPost('/auth/candidate/verify', { link_token: linkToken, code: value }));
    } catch (e) {
      setError(e.message);
      setCode('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <StateCard>
      <StateIcon icon={IconMailOpened} tint={TEAL} />
      <Text fz={18} fw={600}>
        Check your email
      </Text>
      <Text fz={15} lh={1.55} c="var(--cv-text-secondary)">
        We sent a 6-digit code to <b>{sent.email_hint}</b>. Enter it to open your interview. This keeps your
        interview private, even if the link is forwarded.
      </Text>
      <PinInput
        length={6}
        type="number"
        oneTimeCode
        size="lg"
        value={code}
        onChange={setCode}
        onComplete={verify}
        disabled={busy}
        error={Boolean(error)}
        ariaLabel="Code from the email"
        mt={6}
      />
      {error && (
        <Text fz={14} c="var(--cv-danger-text-strong)" role="alert">
          {error}
        </Text>
      )}
      <Button variant="subtle" size="sm" disabled={wait > 0 || busy} onClick={onResend}>
        {wait > 0 ? `Send a new code in ${wait} s` : 'Send a new code'}
      </Button>
      <Text fz={13} c="var(--cv-text-dimmed)">
        The code works once, for 10 minutes. Not arrived? Check your spam folder.
      </Text>
    </StateCard>
  );
}

// Check the invitation link, ask for the emailed code, then the interview.
export default function CandidateJoinPage() {
  const { linkToken } = useParams();
  const [result, setResult] = useState({ status: 'checking' }); // checking | code | joined | failed
  const [attempt, setAttempt] = useState(0); // "Try again" checks the link once more
  // The interview ended: show the "has ended" message (one stable function,
  // so the interview steps do not restart on every render).
  const showEnded = useCallback(() => setResult({ status: 'failed', httpStatus: 410 }), []);
  useDocumentTitle('Your interview · CandiVue AI');

  // Ask the backend to email a code (again: a new one).
  const sendCode = useCallback(
    async (again = false) => {
      try {
        const sent = await apiPost('/auth/candidate', { link_token: linkToken, again });
        setResult({ status: 'code', sent });
      } catch (error) {
        setResult({ status: 'failed', httpStatus: error.status, message: error.status === 503 && error.message });
      }
    },
    [linkToken],
  );

  useEffect(() => {
    const session = loadSession();
    if (session?.user?.role === 'candidate' && session.link === linkToken) {
      setResult({ status: 'joined' }); // a reload in this tab: still signed in
      return;
    }
    clearSession(); // a new link always starts a fresh candidate session
    setResult({ status: 'checking' });
    sendCode();
  }, [linkToken, attempt, sendCode]);

  // The right code: keep the session for this tab and this link.
  function joined(answer) {
    saveSession({ token: answer.access_token, user: answer.user, link: linkToken });
    setResult({ status: 'joined' });
  }

  const message = result.status === 'failed' ? messageFor(result) : null;

  return (
    <Box mih="100vh" bg="var(--cv-page)">
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
          <ThemeToggle />
        </span>
      </header>

      {/* A working link: the waiting room and the call use the full width. */}
      {result.status === 'joined' ? (
        <CandidateInterview onEnded={showEnded} />
      ) : (
        <Box px={{ base: 16, sm: 24 }} py={40} style={{ display: 'flex', justifyContent: 'center' }}>
          {result.status === 'checking' && (
            <StateCard>
              <span className={classes.spinner} />
              <Text fz={17} fw={600}>
                Opening your interview…
              </Text>
            </StateCard>
          )}
          {result.status === 'code' && (
            <CodeStep linkToken={linkToken} sent={result.sent} onJoined={joined} onResend={() => sendCode(true)} />
          )}
          {message && (
            <StateCard>
              <StateIcon icon={message.icon} tint={message.tint} />
              <Text fz={18} fw={600}>
                {message.title}
              </Text>
              <Text fz={15} lh={1.55} c="var(--cv-text-secondary)">
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
      )}
    </Box>
  );
}
