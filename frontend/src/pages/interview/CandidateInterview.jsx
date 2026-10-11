// The candidate's interview after the private link was accepted (design:
// Candidate Join, JoinWelcome → DeviceCheck → in call). Only the call: no
// transcript, scores, identity check or assistant (N9). The candidate can
// join any time until the interviewer ends the interview. LiveKit reconnects
// a dropped connection by itself; after a reload (or a crashed tab) the
// candidate goes straight back into the call (remembered in this tab).

import { Box, Button, Stack, Text } from '@mantine/core';
import { LiveKitRoom } from '@livekit/components-react';
import { IconAlertTriangle, IconCircleCheck, IconVideo } from '@tabler/icons-react';
import { DisconnectReason } from 'livekit-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import { apiGet, apiPost } from '../../api/client';
import { whenText } from '../../utils/dates';
import CallView from './CallView';
import classes from './CandidateInterview.module.css';
import { liveKitUrl } from './liveKit';

const NOTICE = 'Not recorded · a written transcript is kept';
const IN_CALL = 'candivue-in-call'; // this tab was in the call (sessionStorage)

// Remember (or forget) that this tab is in the call, so a reload rejoins.
function rememberInCall(inCall) {
  try {
    if (inCall) sessionStorage.setItem(IN_CALL, '1');
    else sessionStorage.removeItem(IN_CALL);
  } catch {
    // storage blocked: a reload then shows the welcome step again
  }
}

// True when this tab was in the call before a reload.
function wasInCall() {
  try {
    return sessionStorage.getItem(IN_CALL) === '1';
  } catch {
    return false;
  }
}

// A white card for the steps before and after the call.
function Card({ children }) {
  return (
    <Box className={classes.card}>
      <Stack gap={12}>{children}</Stack>
    </Box>
  );
}

// Camera and microphone preview before joining (design: DeviceCheck).
function DeviceCheck({ onJoin, joining }) {
  const videoRef = useRef(null);
  const [state, setState] = useState('checking'); // checking | ok | blocked

  useEffect(() => {
    let stream;
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: true })
      .then((media) => {
        stream = media;
        if (videoRef.current) videoRef.current.srcObject = media;
        setState('ok');
      })
      .catch(() => setState('blocked'));
    // Free the camera for the call itself.
    return () => stream?.getTracks().forEach((track) => track.stop());
  }, []);

  return (
    <Card>
      <Text fz={20} fw={600}>
        Check your camera and mic
      </Text>
      <video ref={videoRef} className={classes.preview} autoPlay muted playsInline />
      {state === 'ok' && (
        <Text c="#245F3E" fz={15} className={classes.line}>
          <IconCircleCheck size={17} /> Camera and microphone are working.
        </Text>
      )}
      {state === 'blocked' && (
        <Text c="#7A5000" fz={15} className={classes.line}>
          <IconAlertTriangle size={17} /> The browser blocked the camera or microphone. Allow them
          (the camera icon in the address bar), then reload this page.
        </Text>
      )}
      <Button size="md" leftSection={<IconVideo size={18} />} onClick={onJoin} loading={joining} disabled={state === 'checking'}>
        Join interview
      </Button>
    </Card>
  );
}

// The steps: welcome → devices → call → left (rejoin) or ended.
export default function CandidateInterview({ onEnded }) {
  const [interview, setInterview] = useState(null);
  const [step, setStep] = useState('welcome');
  const [token, setToken] = useState(null);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState(null);

  // Get a ticket for the call and join it.
  const join = useCallback(async () => {
    setJoining(true);
    setError(null);
    try {
      setToken((await apiPost('/candidate/room')).token);
      setStep('call');
      rememberInCall(true);
    } catch (e) {
      rememberInCall(false);
      if (e.status === 410) onEnded();
      else setError(e.message);
    } finally {
      setJoining(false);
    }
  }, [onEnded]);

  useEffect(() => {
    apiGet('/candidate/interview').then(setInterview).catch((e) => setError(e.message));
    if (wasInCall()) join(); // reloaded during the call: straight back in
  }, [join]);

  // Leave the call (the candidate can rejoin with the same link).
  function leave() {
    rememberInCall(false);
    setStep('left');
  }

  // The interviewer ended the interview.
  function ended() {
    rememberInCall(false);
    onEnded();
  }

  if (step === 'call' && token) {
    return (
      <LiveKitRoom
        serverUrl={liveKitUrl()}
        token={token}
        connect
        audio
        video
        className={classes.call}
        onDisconnected={(reason) => {
          if (reason === DisconnectReason.ROOM_DELETED) ended(); // the interviewer ended it
        }}
      >
        <CallView
          role="candidate"
          title={interview?.job_title ?? 'Your interview'}
          otherName="The interviewer"
          notice={NOTICE}
          onFinish={leave}
        />
      </LiveKitRoom>
    );
  }

  return (
    <div className={classes.page}>
      {error && (
        <Card>
          <Text c="#932E24">{error}</Text>
        </Card>
      )}
      {step === 'welcome' && interview && (
        <Card>
          <Text fz={22} fw={600}>
            Welcome to your interview
          </Text>
          <div className={classes.facts}>
            <span>Role</span>
            <b>{interview.job_title}</b>
            <span>When</span>
            <b>
              {whenText(interview.scheduled_at)} (about {interview.duration_minutes} minutes)
            </b>
          </div>
          <Text fz={15} c="#48535B" lh={1.6}>
            Take a minute to check your camera and microphone, then join. The call is not recorded;
            only a written transcript is kept for the interviewer.
          </Text>
          <Button size="md" onClick={() => setStep('devices')}>
            Check camera and mic
          </Button>
        </Card>
      )}
      {step === 'devices' && <DeviceCheck onJoin={join} joining={joining} />}
      {step === 'left' && (
        <Card>
          <Text fz={20} fw={600}>
            You left the interview
          </Text>
          <Text fz={15} c="#48535B">
            You can rejoin with the same link until the interviewer ends the interview.
          </Text>
          <Button size="md" onClick={join} loading={joining}>
            Rejoin
          </Button>
        </Card>
      )}
    </div>
  );
}
