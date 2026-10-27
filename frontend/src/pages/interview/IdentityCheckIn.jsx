// Check-in before the interview (F7, §4B-15; design: Candidate Join,
// Enrolment: Consent → Photo → Done). After the emailed code, the candidate
// can confirm it is them: three pictures from the camera are compared with
// the photo they sent with their application. They decide freely: "Skip"
// has no effect on the interview. The pictures are not stored, and the
// candidate never sees the result (only the interviewer does). If a picture
// cannot be used (two people, no face, too far, too dark), they are told
// what to change and try again; after too many tries they simply continue.

import { Button, Checkbox, Stepper } from '@mantine/core';
import {
  IconCamera,
  IconCheck,
  IconEyeOff,
  IconPhoto,
  IconShieldLock,
  IconTrash,
  IconUserCheck,
} from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';

import { apiDelete, apiGet, apiUpload } from '../../api/client';
import classes from './IdentityCheckIn.module.css';

const PICTURES = 3;
const GAP_MS = 400; // between the pictures, so they differ a little
const GIVE_UP = 'after several tries'; // the backend's "continue without" message

// Take one JPEG picture from the playing video.
function snapshot(video) {
  if (!video.videoWidth) throw new Error('The camera isn’t ready yet. Please try again in a moment.');
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
}

// Step 1: what happens, who sees what, for how long.
function ConsentStep({ retentionDays, onAgree, onSkip, busy }) {
  const [agreed, setAgreed] = useState(false);
  return (
    <div className={classes.card}>
      <h2 className={classes.title}>Confirm it’s you</h2>
      <p className={classes.lead}>
        To make sure the right person joins, CandiVue compares a few pictures from your camera with the photo you sent
        with your application. It takes a few seconds, and it’s your choice.
      </p>
      <ul className={classes.facts}>
        <li>
          <IconPhoto size={18} />
          <span>
            <b>What happens:</b> three pictures are compared with your application photo on our server. The pictures
            are not stored.
          </span>
        </li>
        <li>
          <IconEyeOff size={18} />
          <span>
            <b>Who sees what:</b> only the interviewer sees the result. It is never used for scoring.
          </span>
        </li>
        <li>
          <IconShieldLock size={18} />
          <span>
            <b>How long:</b> the face data from your application photo is encrypted and deleted {retentionDays} days
            after the interview, or right away if you skip.
          </span>
        </li>
      </ul>
      <Checkbox
        checked={agreed}
        onChange={(event) => setAgreed(event.currentTarget.checked)}
        label="I agree that my face is compared with my application photo for this interview."
        mt="md"
      />
      <div className={classes.actions}>
        <Button variant="default" onClick={onSkip} loading={busy}>
          Skip the check
        </Button>
        <Button disabled={!agreed} onClick={onAgree}>
          Continue
        </Button>
      </div>
    </div>
  );
}

// Step 2: the camera with an oval guide; three pictures in a row.
function PhotoStep({ onDone, onBack, onGiveUp }) {
  const videoRef = useRef(null);
  const [camera, setCamera] = useState('starting'); // starting | ready | blocked
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [gaveUp, setGaveUp] = useState(false);

  useEffect(() => {
    let stream;
    let stopped = false;
    navigator.mediaDevices
      .getUserMedia({ video: { width: 1280, height: 720 }, audio: false })
      .then((media) => {
        if (stopped) return media.getTracks().forEach((track) => track.stop());
        stream = media;
        videoRef.current.srcObject = media; // "ready" once it plays (onPlaying)
      })
      .catch(() => !stopped && setCamera('blocked'));
    return () => {
      stopped = true;
      stream?.getTracks().forEach((track) => track.stop()); // free it for the call
    };
  }, []);

  // Take the pictures and send them; the backend says what to change.
  async function capture() {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      for (let i = 0; i < PICTURES; i += 1) {
        if (i) await new Promise((wait) => setTimeout(wait, GAP_MS));
        form.append('pictures', await snapshot(videoRef.current), `picture-${i + 1}.jpg`);
      }
      onDone(await apiUpload('/candidate/identity', form));
    } catch (e) {
      setError(e.message);
      if (e.message.includes(GIVE_UP)) setGaveUp(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={classes.card}>
      <h2 className={classes.title}>Look at the camera</h2>
      <p className={classes.lead}>Keep your face inside the oval, in good light, with nobody else in view.</p>
      <div className={classes.stage}>
        <video ref={videoRef} className={classes.video} autoPlay muted playsInline onPlaying={() => setCamera('ready')} />
        <div className={`${classes.oval} ${busy ? classes.ovalBusy : ''}`} aria-hidden="true" />
        {camera !== 'ready' && (
          <div className={classes.cameraNote}>
            {camera === 'blocked'
              ? 'The browser blocked the camera. Allow it (the icon in the address bar) and reload this page, or skip the check.'
              : 'Starting your camera…'}
          </div>
        )}
      </div>
      {error && (
        <div className={classes.error} role="alert">
          {error}
        </div>
      )}
      <div className={classes.actions}>
        {gaveUp ? (
          <Button onClick={onGiveUp}>Continue to the waiting room</Button>
        ) : (
          <>
            <Button variant="default" onClick={onBack} disabled={busy}>
              Back
            </Button>
            <Button onClick={capture} loading={busy} disabled={camera !== 'ready'} leftSection={<IconCamera size={16} />}>
              {error ? 'Try again' : 'Take the pictures'}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

// The whole step: consent → pictures → done (then the waiting room).
export default function IdentityCheckIn({ identity, onDone }) {
  const [step, setStep] = useState(0);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // "Skip the check": recorded, no effect on the interview.
  async function skip() {
    setBusy(true);
    try {
      onDone(await apiDelete('/candidate/identity'));
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  // After the last allowed try the backend records the check-in as failed
  // (the interviewer sees why); the candidate simply continues.
  async function continueWithout() {
    try {
      onDone(await apiGet('/candidate/interview'));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className={classes.wrap}>
      <Stepper active={step} size="sm" className={classes.stepper} allowNextStepsSelect={false}>
        <Stepper.Step label="Consent" />
        <Stepper.Step label="Pictures" />
        <Stepper.Step label="Done" />
      </Stepper>
      {step === 0 && (
        <ConsentStep retentionDays={identity.retention_days} onAgree={() => setStep(1)} onSkip={skip} busy={busy} />
      )}
      {step === 1 && (
        <PhotoStep
          onBack={() => setStep(0)}
          onGiveUp={continueWithout}
          onDone={(details) => {
            setResult(details);
            setStep(2);
          }}
        />
      )}
      {step === 2 && (
        <div className={`${classes.card} ${classes.done}`}>
          <span className={classes.doneIcon}>
            <IconCheck size={26} />
          </span>
          <h2 className={classes.title}>You’re checked in</h2>
          <p className={classes.lead}>Thank you. The interviewer will let you in from the waiting room.</p>
          <Button onClick={() => onDone(result)} leftSection={<IconUserCheck size={16} />}>
            Continue to the waiting room
          </Button>
        </div>
      )}
      {error && (
        <div className={classes.error} role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

// In the waiting room: the choice made, and how to withdraw it.
export function IdentityChoice({ identity, onChange }) {
  const [busy, setBusy] = useState(false);
  if (!identity.available || identity.consent === null) return null;

  // Withdraw: the result and the face data of the application photo are
  // deleted at once.
  async function withdraw() {
    setBusy(true);
    try {
      onChange(await apiDelete('/candidate/identity'));
    } finally {
      setBusy(false);
    }
  }

  return identity.consent === 'given' ? (
    <div className={classes.choice}>
      <IconUserCheck size={16} />
      <span>You’re checked in with your camera.</span>
      <button type="button" className={classes.linkButton} onClick={withdraw} disabled={busy}>
        <IconTrash size={14} /> Withdraw
      </button>
    </div>
  ) : (
    <div className={classes.choice}>
      <IconEyeOff size={16} />
      <span>You continued without the face check.</span>
    </div>
  );
}
