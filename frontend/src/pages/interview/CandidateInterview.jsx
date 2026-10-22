// The candidate's interview after the private link was accepted (design:
// Candidate Join: JoinWelcome, DeviceCheck, WaitingRoom, in call; arranged
// as one waiting-room screen on the user's request, 13-10-2026).
// - Check-in first (F7, §4B-15: only when set up, the application photo is
//   usable and not decided yet): consent → pictures → done, or skip it
//   (IdentityCheckIn).
// - Waiting room: camera preview with a microphone level, device choice,
//   the interview details, a required notice tick, then "Join waiting
//   room". The page then tells the backend every few seconds that the
//   candidate is waiting; the call starts by itself once the interviewer
//   lets them in (the backend refuses the ticket before that).
// - In the call: the video (16:9), and beside it the chat with the
//   interviewer and the interview details. Never the transcript, scores,
//   CV, identity check or assistant (N9).
// - After a reload (or a crashed tab) the candidate goes straight back into
//   the call, without being let in again (remembered in this tab).

import { Button, Checkbox, Select } from '@mantine/core';
import { LiveKitRoom } from '@livekit/components-react';
import {
  IconAlertTriangle,
  IconBriefcase,
  IconCalendarEvent,
  IconClock,
  IconHeadphones,
  IconInfoCircle,
  IconMessageCircle,
  IconMicrophone,
  IconMicrophoneOff,
  IconPlugConnected,
  IconShieldLock,
  IconSun,
  IconUser,
  IconVideo,
  IconVideoOff,
} from '@tabler/icons-react';
import { DisconnectReason } from 'livekit-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import { apiGet, apiPost } from '../../api/client';
import { HELP_EMAIL } from '../../config';
import { whenText } from '../../utils/dates';
import { formatElapsed, startsIn, useElapsed, useNow } from './callTime';
import CallView, { CallConnection, onDeviceFailure } from './CallView';
import classes from './CandidateInterview.module.css';
import { liveKitUrl } from './liveKit';
import IdentityCheckIn, { IdentityChoice } from './IdentityCheckIn';
import RoomChat from './RoomChat';

const IN_CALL = 'candivue-in-call'; // this tab was let in (sessionStorage)
const WAITING_BEAT_MS = 3000;
const NOTICE = 'The call is not recorded. Only a written transcript is kept for the interviewer.';
const TIPS = [
  { icon: IconSun, text: 'Sit somewhere quiet and well lit, facing the light.' },
  { icon: IconHeadphones, text: 'Headphones avoid echo for both of you.' },
  { icon: IconPlugConnected, text: 'If the connection drops, you are reconnected to the same interview automatically.' },
  { icon: IconMessageCircle, text: 'Use the chat in the call to share a link or spell something out.' },
];

// Remember (or forget) that this tab was let into the call, so a reload rejoins.
function rememberInCall(inCall) {
  try {
    if (inCall) sessionStorage.setItem(IN_CALL, '1');
    else sessionStorage.removeItem(IN_CALL);
  } catch {
    // storage blocked: a reload then shows the waiting room again
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

// Camera + microphone preview with a level meter and device choice.
// Returns the chosen devices and switches through onChange.
function DevicePreview({ devices, onChange }) {
  const videoRef = useRef(null);
  const meterRef = useRef(null);
  const [state, setState] = useState('checking'); // checking | ok | blocked
  const [cameras, setCameras] = useState([]);
  const [mics, setMics] = useState([]);

  useEffect(() => {
    let stream;
    let audio;
    let frame;
    let stopped = false;
    const constraints = {
      video: devices.cameraId ? { deviceId: { exact: devices.cameraId } } : true,
      audio: devices.micId ? { deviceId: { exact: devices.micId } } : true,
    };
    navigator.mediaDevices
      .getUserMedia(constraints)
      .then(async (media) => {
        if (stopped) return media.getTracks().forEach((track) => track.stop());
        stream = media;
        if (videoRef.current) videoRef.current.srcObject = media;
        setState('ok');
        // The device names are only readable after permission was given.
        const list = await navigator.mediaDevices.enumerateDevices();
        const option = (d, i, kind) => ({ value: d.deviceId, label: d.label || `${kind} ${i + 1}` });
        setCameras(list.filter((d) => d.kind === 'videoinput').map((d, i) => option(d, i, 'Camera')));
        setMics(list.filter((d) => d.kind === 'audioinput').map((d, i) => option(d, i, 'Microphone')));
        // Microphone level: the bar grows with the loudness.
        audio = new AudioContext();
        const analyser = audio.createAnalyser();
        analyser.fftSize = 512;
        audio.createMediaStreamSource(media).connect(analyser);
        const samples = new Uint8Array(analyser.fftSize);
        const draw = () => {
          analyser.getByteTimeDomainData(samples);
          let peak = 0;
          for (const value of samples) peak = Math.max(peak, Math.abs(value - 128));
          if (meterRef.current) meterRef.current.style.width = `${Math.min(100, (peak / 64) * 100)}%`;
          frame = requestAnimationFrame(draw);
        };
        draw();
      })
      .catch(() => !stopped && setState('blocked'));
    // Free the camera and microphone for the call itself.
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      audio?.close();
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [devices.cameraId, devices.micId]);

  return (
    <div className={classes.previewCard}>
      <div className={classes.previewStage}>
        <video
          ref={videoRef}
          className={`${classes.preview} ${devices.cameraOn ? '' : classes.hidden}`}
          autoPlay
          muted
          playsInline
        />
        {(!devices.cameraOn || state !== 'ok') && (
          <div className={classes.previewOff}>
            {state === 'blocked' ? (
              <>
                <IconAlertTriangle size={26} />
                The browser blocked the camera or microphone. Allow them (the icon in the address bar), then reload
                this page.
              </>
            ) : state === 'checking' ? (
              'Starting your camera…'
            ) : (
              <>
                <IconVideoOff size={26} />
                Your camera is off
              </>
            )}
          </div>
        )}
        <div className={classes.previewControls}>
          <button
            type="button"
            className={`${classes.round} ${devices.micOn ? '' : classes.roundOff}`}
            onClick={() => onChange({ micOn: !devices.micOn })}
            aria-label={devices.micOn ? 'Join with the microphone off' : 'Join with the microphone on'}
          >
            {devices.micOn ? <IconMicrophone size={19} /> : <IconMicrophoneOff size={19} />}
          </button>
          <button
            type="button"
            className={`${classes.round} ${devices.cameraOn ? '' : classes.roundOff}`}
            onClick={() => onChange({ cameraOn: !devices.cameraOn })}
            aria-label={devices.cameraOn ? 'Join with the camera off' : 'Join with the camera on'}
          >
            {devices.cameraOn ? <IconVideo size={19} /> : <IconVideoOff size={19} />}
          </button>
        </div>
      </div>
      <div className={classes.level} aria-hidden="true">
        <IconMicrophone size={15} />
        <span className={classes.levelTrack}>
          <span ref={meterRef} className={classes.levelFill} />
        </span>
      </div>
      {state === 'ok' && (
        <div className={classes.devices}>
          <Select
            size="sm"
            label="Camera"
            data={cameras}
            value={devices.cameraId ?? cameras[0]?.value ?? null}
            onChange={(cameraId) => cameraId && onChange({ cameraId })}
            allowDeselect={false}
            comboboxProps={{ withinPortal: true }}
          />
          <Select
            size="sm"
            label="Microphone"
            data={mics}
            value={devices.micId ?? mics[0]?.value ?? null}
            onChange={(micId) => micId && onChange({ micId })}
            allowDeselect={false}
            comboboxProps={{ withinPortal: true }}
          />
        </div>
      )}
    </div>
  );
}

// The interview's details: role, interviewer, time, length.
function InterviewFacts({ interview }) {
  return (
    <ul className={classes.facts}>
      <li>
        <IconBriefcase size={17} />
        <span>
          <small>Role</small>
          {interview.job_title}
        </span>
      </li>
      <li>
        <IconUser size={17} />
        <span>
          <small>Interviewer</small>
          {interview.interviewer_name ?? 'CandiVue interviewer'}
        </span>
      </li>
      <li>
        <IconCalendarEvent size={17} />
        <span>
          <small>When</small>
          {whenText(interview.scheduled_at)}
        </span>
      </li>
      <li>
        <IconClock size={17} />
        <span>
          <small>Length</small>
          about {interview.duration_minutes} minutes
        </span>
      </li>
    </ul>
  );
}

// The waiting room: preview, details, notice, then waiting to be let in.
function WaitingRoom({ interview, onInterview, devices, onDevices, waiting, onWait, onStopWaiting, error }) {
  const [agreed, setAgreed] = useState(waiting);
  const now = useNow(30000);
  const until = startsIn(interview.scheduled_at, now);
  const present = interview.lobby.interviewer_present;

  return (
    <div className={classes.lobby}>
      <div className={classes.lobbyIntro}>
        <span className={classes.kicker}>Your interview</span>
        <h1 className={classes.headline}>{interview.job_title}</h1>
        <p className={classes.sub}>
          {until ? `Scheduled ${until}, ${whenText(interview.scheduled_at)}.` : `Scheduled for ${whenText(interview.scheduled_at)}.`}{' '}
          Check how you look and sound, then join the waiting room.
        </p>
      </div>

      <div className={classes.lobbyGrid}>
        <DevicePreview devices={devices} onChange={onDevices} />

        <div className={classes.side}>
          <div className={classes.card}>
            <InterviewFacts interview={interview} />
          </div>

          <div className={`${classes.card} ${classes.statusCard}`}>
            {waiting ? (
              <>
                <div className={classes.waitingLine}>
                  <span className={classes.dots} aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  <b>{present ? 'The interviewer knows you’re here' : 'You’re in the waiting room'}</b>
                </div>
                <p className={classes.statusText}>
                  {present
                    ? 'They will let you in shortly. Keep this tab open; the call starts here by itself.'
                    : 'The interviewer hasn’t started yet. Keep this tab open; the call starts here as soon as they let you in.'}
                </p>
                <button type="button" className={classes.textButton} onClick={onStopWaiting}>
                  Leave the waiting room
                </button>
              </>
            ) : (
              <>
                <Checkbox
                  checked={agreed}
                  onChange={(event) => setAgreed(event.currentTarget.checked)}
                  label="I understand that the call is not recorded and that a written transcript is kept for the interviewer."
                  classNames={{ label: classes.consent }}
                />
                <Button size="md" fullWidth radius="md" disabled={!agreed} onClick={onWait}>
                  Join the waiting room
                </Button>
              </>
            )}
            {error && <div className={classes.error}>{error}</div>}
            <IdentityChoice identity={interview.identity} onChange={onInterview} />
          </div>

          <ul className={classes.tips}>
            {TIPS.slice(0, 3).map(({ icon: Icon, text }) => (
              <li key={text}>
                <Icon size={16} />
                {text}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

// The call with the chat and the interview details beside it.
function InCall({ interview, onLeave }) {
  const [tab, setTab] = useState('chat');
  const [unread, setUnread] = useState(0);
  const elapsed = useElapsed(interview.started_at);
  const interviewer = interview.interviewer_name ?? 'The interviewer';

  return (
    <div className={classes.inCall}>
      <header className={classes.callBar}>
        <span className={classes.callTitle}>
          <b>{interview.job_title}</b>
          <span>with {interviewer}</span>
        </span>
        <span className={classes.callTimer}>{formatElapsed(elapsed)}</span>
        <span className={classes.notRecorded}>
          <IconShieldLock size={14} /> Not recorded
        </span>
        <span className={classes.spacer} />
        <CallConnection />
      </header>
      <div className={classes.callGrid}>
        <main className={classes.callMain}>
          <CallView
            role="candidate"
            otherName={interviewer}
            waiting={<span>{interviewer} will appear here. The call is open; they may be away for a moment.</span>}
            onFinish={onLeave}
          />
        </main>
        <aside className={classes.callSide}>
          <div className={classes.tabs} role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'chat'}
              className={`${classes.tab} ${tab === 'chat' ? classes.tabActive : ''}`}
              onClick={() => setTab('chat')}
            >
              <IconMessageCircle size={16} /> Chat
              {unread > 0 && <span className={classes.unread}>{unread}</span>}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'info'}
              className={`${classes.tab} ${tab === 'info' ? classes.tabActive : ''}`}
              onClick={() => setTab('info')}
            >
              <IconInfoCircle size={16} /> Interview
            </button>
          </div>
          <div className={classes.tabPanel} hidden={tab !== 'chat'}>
            <RoomChat
              path="/candidate/messages"
              me="candidate"
              otherName={interviewer}
              active={tab === 'chat'}
              onUnread={setUnread}
            />
          </div>
          <div className={`${classes.tabPanel} ${classes.info}`} hidden={tab !== 'info'}>
            <InterviewFacts interview={interview} />
            <p className={classes.infoNote}>
              <IconShieldLock size={16} /> {NOTICE}
            </p>
            <ul className={classes.tips}>
              {TIPS.map(({ icon: Icon, text }) => (
                <li key={text}>
                  <Icon size={16} />
                  {text}
                </li>
              ))}
            </ul>
            <p className={classes.help}>
              Need help? <a href={`mailto:${HELP_EMAIL}`}>{HELP_EMAIL}</a>
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

// A small card for the states around the call (left, another tab).
function StateCard({ title, children, action }) {
  return (
    <div className={classes.stateWrap}>
      <div className={classes.stateCard}>
        <b>{title}</b>
        <p>{children}</p>
        {action}
      </div>
    </div>
  );
}

// The steps: waiting room → call → left (rejoin) / another tab / ended.
export default function CandidateInterview({ onEnded }) {
  const [interview, setInterview] = useState(null);
  const [step, setStep] = useState('lobby'); // lobby | call | left | elsewhere
  const [waiting, setWaiting] = useState(false);
  const [token, setToken] = useState(null);
  const [error, setError] = useState(null);
  const [devices, setDevices] = useState({ micOn: true, cameraOn: true, micId: null, cameraId: null });

  // The interview is over (or the link no longer works): the ended message.
  const finished = useCallback(() => {
    rememberInCall(false);
    onEnded();
  }, [onEnded]);

  // Get a ticket and join the call; not let in yet → keep waiting.
  const join = useCallback(async () => {
    try {
      setToken((await apiPost('/candidate/room')).token);
      rememberInCall(true);
      setStep('call');
    } catch (e) {
      if (e.status === 410 || e.status === 401) finished();
      else if (e.status === 409) setWaiting(true);
      else setError(e.message);
    }
  }, [finished]);

  // The interview's details; after a reload during the call, straight back in.
  useEffect(() => {
    apiGet('/candidate/interview')
      .then((details) => {
        if (details.status === 'ended' || details.status === 'cancelled') return finished();
        setInterview(details);
        if (wasInCall()) join();
      })
      .catch((e) => (e.status === 401 ? finished() : setError(e.message)));
  }, [join, finished]);

  // While waiting: tell the backend every few seconds; join once let in.
  useEffect(() => {
    if (!waiting || step !== 'lobby') return undefined;
    let current = true;
    const beat = async () => {
      try {
        const details = await apiPost('/candidate/waiting');
        if (!current) return;
        if (details.status === 'ended' || details.status === 'cancelled') return finished();
        setInterview(details);
        setError(null);
        if (details.lobby.admitted) join();
      } catch (e) {
        if (e.status === 401 || e.status === 410) finished();
        else if (current) setError('Connection problem: trying again…');
      }
    };
    beat();
    const timer = setInterval(beat, WAITING_BEAT_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [waiting, step, join, finished]);

  if (step === 'call' && token) {
    return (
      <LiveKitRoom
        serverUrl={liveKitUrl()}
        token={token}
        connect
        audio={devices.micOn ? (devices.micId ? { deviceId: devices.micId } : true) : false}
        video={devices.cameraOn ? (devices.cameraId ? { deviceId: devices.cameraId } : true) : false}
        className={classes.callWrap}
        onMediaDeviceFailure={onDeviceFailure}
        onDisconnected={(reason) => {
          if (reason === DisconnectReason.ROOM_DELETED) finished(); // the interviewer ended it
          if (reason === DisconnectReason.DUPLICATE_IDENTITY) {
            setStep('elsewhere');
            setToken(null);
          }
        }}
      >
        <InCall
          interview={interview}
          onLeave={() => {
            rememberInCall(false);
            setToken(null);
            setStep('left');
          }}
        />
      </LiveKitRoom>
    );
  }

  if (step === 'left') {
    return (
      <StateCard title="You left the interview" action={<Button onClick={join}>Rejoin</Button>}>
        You can rejoin with the same link until the interviewer ends the interview.
      </StateCard>
    );
  }
  if (step === 'elsewhere') {
    return (
      <StateCard title="You’re connected in another tab or device" action={<Button onClick={join}>Use this tab instead</Button>}>
        Only one connection is allowed. Close the other one, or continue here.
      </StateCard>
    );
  }
  if (!interview) {
    return error ? (
      <StateCard title="We couldn’t load your interview">{error}</StateCard>
    ) : (
      <div className={classes.stateWrap}>
        <span className={classes.spinner} />
      </div>
    );
  }
  if (interview.identity.available && interview.identity.consent === null) {
    return <IdentityCheckIn identity={interview.identity} onDone={setInterview} />;
  }
  return (
    <WaitingRoom
      interview={interview}
      onInterview={setInterview}
      devices={devices}
      onDevices={(change) => setDevices((old) => ({ ...old, ...change }))}
      waiting={waiting}
      onWait={() => setWaiting(true)}
      onStopWaiting={() => setWaiting(false)}
      error={error}
    />
  );
}
