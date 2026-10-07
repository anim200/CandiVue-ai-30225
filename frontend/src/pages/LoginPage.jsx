// Interviewer sign-in, built from the design (Login.dc.html: frame 1a and the
// states in section 2). Candidates never sign in here: they use the private
// link in their invitation email.
// Left out on purpose (decided for #646482): "Forgot password?" and
// "Keep me signed in". The light/dark switch comes with dark mode later.

import { Anchor, Box, Button, PasswordInput, TextInput } from '@mantine/core';
import {
  IconAlertCircle,
  IconCheck,
  IconCircleCheck,
  IconCloudOff,
  IconInfoCircle,
  IconLink,
  IconLock,
  IconMail,
  IconQuote,
  IconUserCheck,
} from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router';

import { apiPost } from '../api/client';
import { clearSession, loadSession, saveSession } from '../auth/session';
import Logo from '../components/Logo';
import classes from './LoginPage.module.css';

// Placeholder positioning from the design; to be replaced by the trainee's
// own positioning statement (product naming deliverable, E6).
const HEADLINE = 'Hiring decisions, backed by evidence.';
const INTRO =
  'CandiVue AI screens CVs, captures interviews and drafts assessments. ' +
  'You review every result and make every decision.';
const PRINCIPLES = [
  { icon: IconQuote, text: 'Every score links to a CV excerpt or transcript moment' },
  { icon: IconUserCheck, text: 'Nobody is hired or rejected automatically' },
  { icon: IconLock, text: 'Candidates join by private link and never see scores' },
];

// Messages from the design's state frames (section 2).
const WRONG_LOGIN = 'That email and password don’t match. Check them and try again.';
const SERVICE_DOWN = 'We can’t sign you in right now. Please try again in a few minutes.';
const SESSION_ENDED = 'You were signed out because your session ended. Sign in to continue.';
const EMAIL_HINT = 'Enter a full email address, like name@example.com';

// Breathing rings: size, line opacity and start delay, from the design.
const RINGS = [
  { size: 520, opacity: 0.08, delay: '0s' },
  { size: 780, opacity: 0.06, delay: '1.5s' },
  { size: 1040, opacity: 0.04, delay: '3s' },
];

const SHOW_SIGNED_IN_MS = 600; // briefly show "Signed in" before opening Jobs

// Left side of the login page: logo, animated rings, evidence chips and the headline.
function BrandPanel() {
  return (
    <div className={classes.brand}>
      {RINGS.map((ring) => (
        <div
          key={ring.size}
          className={classes.ring}
          style={{
            width: ring.size,
            height: ring.size,
            border: `1px solid rgba(255,255,255,${ring.opacity})`,
            animationDelay: ring.delay,
          }}
        />
      ))}
      <div className={classes.glow} />

      <div className={classes.logoRow}>
        <Logo size="lg" onDark glance />
      </div>

      {/* Synthetic examples of the evidence CandiVue links to. */}
      <div className={classes.chips} aria-hidden="true">
        <div className={classes.chip}>
          <span className={classes.timestamp}>02:47</span>
          “added pagination and an index…”
        </div>
        <div className={classes.chip} style={{ marginRight: 46, animationDuration: '8s', animationDelay: '1.2s' }}>
          <span className={classes.met}>
            <IconCheck size={12} />
            Met
          </span>
          Python web framework
        </div>
        <div
          className={classes.chip}
          style={{ marginRight: 12, gap: 12, animationDuration: '7.5s', animationDelay: '2.4s' }}
        >
          <span className={classes.score}>82</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span className={classes.scoreLabel}>Candidate C · screening</span>
            <div className={classes.scoreTrack}>
              <div className={classes.scoreBar} />
            </div>
          </div>
        </div>
      </div>

      <div className={classes.story}>
        <h1 className={classes.headline}>{HEADLINE}</h1>
        <p className={classes.intro}>{INTRO}</p>
        <div className={classes.principles}>
          {PRINCIPLES.map(({ icon: Icon, text }, index) => (
            <div key={text} className={classes.principle} style={{ animationDelay: `${0.35 + index * 0.1}s` }}>
              <span className={classes.principleIcon}>
                <Icon size={17} />
              </span>
              {text}
            </div>
          ))}
        </div>
      </div>

      <div className={classes.demoNote}>Demo environment · synthetic sample data only</div>
    </div>
  );
}

// Interviewer sign-in page (brand panel + sign-in form).
export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailError, setEmailError] = useState(null);
  const [error, setError] = useState(null); // { text, serviceDown }
  const [errorKey, setErrorKey] = useState(0); // restarts the shake on each new error
  const [stage, setStage] = useState('idle'); // idle | signingIn | signedIn
  const goTo = location.state?.from ?? '/jobs';

  // After "Signed in" has been visible for a moment, open the app.
  useEffect(() => {
    if (stage !== 'signedIn') return undefined;
    const timer = setTimeout(() => navigate(goTo, { replace: true }), SHOW_SIGNED_IN_MS);
    return () => clearTimeout(timer);
  }, [stage, goTo, navigate]);

  // Already signed in as an interviewer: nothing to do here.
  if (stage === 'idle' && loadSession()?.user.role === 'interviewer') {
    return <Navigate to="/jobs" replace />;
  }

  // Check the email, sign in with the backend and show the result.
  async function handleSubmit(event) {
    event.preventDefault();
    if (stage !== 'idle') return; // already signing in: ignore extra clicks
    if (!email.includes('@')) {
      setEmailError(EMAIL_HINT);
      return;
    }
    setEmailError(null);
    setError(null);
    setStage('signingIn');
    clearSession(); // signing in replaces any older session in this tab
    try {
      const result = await apiPost('/auth/login', { email, password });
      saveSession({ token: result.access_token, user: result.user });
      setStage('signedIn');
    } catch (err) {
      // 401 = wrong email or password; anything else = we could not check.
      setError(err.status === 401 ? { text: WRONG_LOGIN } : { text: SERVICE_DOWN, serviceDown: true });
      setErrorKey((key) => key + 1);
      setStage('idle');
    }
  }

  const showExpired = searchParams.get('expired') && !error && stage === 'idle';

  return (
    <div className={classes.page}>
      <BrandPanel />

      <div className={classes.formSide}>
        <form className={classes.form} onSubmit={handleSubmit} noValidate>
          {/* On wide screens the logo is in the brand panel. */}
          <Box hiddenFrom="md">
            <Logo />
          </Box>

          <div>
            <h2 className={classes.title}>Welcome back</h2>
            <div className={classes.subtitle}>Sign in to your interviewer account</div>
          </div>

          {showExpired && (
            <div className={`${classes.message} ${classes.info}`} role="status">
              <IconInfoCircle size={18} />
              {SESSION_ENDED}
            </div>
          )}
          {error && (
            <div key={errorKey} className={`${classes.message} ${classes.error}`} role="alert">
              {error.serviceDown ? <IconCloudOff size={18} /> : <IconAlertCircle size={18} />}
              {error.text}
            </div>
          )}

          <TextInput
            label="Email"
            type="email"
            autoComplete="email"
            placeholder="name@example.com"
            leftSection={<IconMail size={17} color="#8A949A" />}
            value={email}
            onChange={(event) => setEmail(event.currentTarget.value)}
            error={emailError}
            classNames={{ input: classes.input, label: classes.label, error: classes.fieldError }}
          />
          <PasswordInput
            label="Password"
            autoComplete="current-password"
            placeholder="Your password"
            leftSection={<IconLock size={17} color="#8A949A" />}
            value={password}
            onChange={(event) => setPassword(event.currentTarget.value)}
            classNames={{ input: classes.input, label: classes.label }}
          />

          <Button
            type="submit"
            className={classes.submit}
            fullWidth
            leftSection={
              stage === 'signingIn' ? (
                <span className={classes.buttonSpinner} />
              ) : stage === 'signedIn' ? (
                <IconCircleCheck size={18} className={classes.fadeIn} />
              ) : null
            }
          >
            {{ idle: 'Sign in', signingIn: 'Signing in…', signedIn: 'Signed in' }[stage]}
          </Button>
          {stage === 'signedIn' && (
            <div className={classes.signedIn}>
              Signed in.{' '}
              <Anchor component={Link} to={goTo} fw={600} fz={15}>
                Go to Jobs
              </Anchor>
            </div>
          )}

          <div className={classes.candidateNote}>
            <span className={classes.candidateIcon}>
              <IconLink size={17} />
            </span>
            <div>
              <b>Are you a candidate?</b> You don’t need an account. Join using the private link in
              your invitation email.
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
