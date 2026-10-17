// The identity check before the interview (F7; design: Candidate Join,
// Enrolment: Consent → Photo → Done). The candidate decides freely:
// "Continue without identification" has no effect on the interview. With
// consent, three pictures are taken from the camera; the backend keeps only
// an encrypted face description (no photo) and deletes it after the
// retention time, or at once if consent is withdrawn. Face only (no voice).

import { Button, Checkbox, Stepper } from '@mantine/core';
import { IconCamera, IconCheck, IconEyeOff, IconShieldLock, IconTrash, IconUserCheck } from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';

import { apiDelete, apiUpload } from '../../api/client';
import classes from './IdentityEnrolment.module.css';

const PICTURES = 3;
const GAP_MS = 400; // between the pictures, so they differ a little

// Take one JPEG picture from the playing video.
function snapshot(video) {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
}

// Step 1: what is captured, for how long, who sees what.
function ConsentStep({ retentionDays, onAgree, onDecline, busy }) {
  const [agreed, setAgreed] = useState(false);
  return (
    <div className={classes.card}>
      <h2 className={classes.title}>Confirm it’s you, with one look at the camera</h2>
      <p className={classes.lead}>
        To make sure the right person joins the interview, CandiVue can compare your face during the call with a
        reference you give now. It’s your choice.
      </p>
      <ul className={classes.facts}>
        <li>
          <IconCamera size={18} />
          <span>
            <b>What we keep:</b> three pictures are turned into a face description (numbers). The pictures
            themselves are not stored.
          </span>
        </li>
        <li>
          <IconShieldLock size={18} />
          <span>
            <b>How long:</b> encrypted, and deleted {retentionDays} days after the interview, or as soon as you
            withdraw.
          </span>
        </li>
        <li>
          <IconEyeOff size={18} />
          <span>
            <b>Who sees what:</b> the interviewer only sees whether the face matches. It is never used for scoring.
          </span>
        </li>
      </ul>
      <Checkbox
        checked={agreed}
        onChange={(event) => setAgreed(event.currentTarget.checked)}
        label="I agree that my face is used to confirm my identity in this interview."
        mt="md"
      />
      <div className={classes.actions}>
        <Button variant="default" onClick={onDecline} loading={busy}>
          Continue without identification
        </Button>
        <Button disabled={!agreed} onClick={onAgree}>
          Continue
        </Button>
      </div>
    </div>
  );
}

// Step 2: the camera with an oval guide; three pictures in a row.
function PhotoStep({ onSaved, onBack }) {
  const videoRef = useRef(null);
  const [camera, setCamera] = useState('starting'); // starting | ready | blocked
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let stream;
    let stopped = false;
    navigator.mediaDevices
      .getUserMedia({ video: { width: 640, height: 480 }, audio: false })
      .then((media) => {
        if (stopped) return media.getTracks().forEach((track) => track.stop());
        stream = media;
        videoRef.current.srcObject = media;
        setCamera('ready');
      })
      .catch(() => !stopped && setCamera('blocked'));
    return () => {
      stopped = true;
      stream?.getTracks().forEach((track) => track.stop()); // free it for the call
    };
  }, []);

  // Take the pictures and send them; the backend says if one is unusable.
  async function capture() {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      for (let i = 0; i < PICTURES; i += 1) {
        if (i) await new Promise((wait) => setTimeout(wait, GAP_MS));
        form.append('pictures', await snapshot(videoRef.current), `picture-${i + 1}.jpg`);
      }
      onSaved(await apiUpload('/candidate/identity', form));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={classes.card}>
      <h2 className={classes.title}>Look at the camera</h2>
      <p className={classes.lead}>Keep your face inside the oval, in good light, with nobody else in view.</p>
      <div className={classes.stage}>
        <video ref={videoRef} className={classes.video} autoPlay muted playsInline />
        <div className={`${classes.oval} ${busy ? classes.ovalBusy : ''}`} aria-hidden="true" />
        {camera !== 'ready' && (
          <div className={classes.cameraNote}>
            {camera === 'blocked'
              ? 'The browser blocked the camera. Allow it (the icon in the address bar), then reload this page.'
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
        <Button variant="default" onClick={onBack} disabled={busy}>
          Back
        </Button>
        <Button onClick={capture} loading={busy} disabled={camera !== 'ready'} leftSection={<IconCamera size={16} />}>
          Take the pictures
        </Button>
      </div>
    </div>
  );
}

// The whole step: consent → photo → done (then the waiting room).
export default function IdentityEnrolment({ identity, onDone }) {
  const [step, setStep] = useState(0);
  const [saved, setSaved] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // "Continue without identification": recorded, no effect on the interview.
  async function decline() {
    setBusy(true);
    try {
      onDone(await apiDelete('/candidate/identity'));
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div className={classes.wrap}>
      <Stepper active={step} size="sm" className={classes.stepper} allowNextStepsSelect={false}>
        <Stepper.Step label="Consent" />
        <Stepper.Step label="Photo" />
        <Stepper.Step label="Done" />
      </Stepper>
      {step === 0 && (
        <ConsentStep
          retentionDays={identity.retention_days}
          onAgree={() => setStep(1)}
          onDecline={decline}
          busy={busy}
        />
      )}
      {step === 1 && (
        <PhotoStep
          onBack={() => setStep(0)}
          onSaved={(details) => {
            setSaved(details);
            setStep(2);
          }}
        />
      )}
      {step === 2 && (
        <div className={`${classes.card} ${classes.done}`}>
          <span className={classes.doneIcon}>
            <IconCheck size={26} />
          </span>
          <h2 className={classes.title}>You’re all set</h2>
          <p className={classes.lead}>
            Your reference is saved. During the call it is compared with your camera now and then. You can withdraw
            any time before the interview ends.
          </p>
          <Button onClick={() => onDone(saved)} leftSection={<IconUserCheck size={16} />}>
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

  // Withdraw consent: the reference is deleted at once.
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
      <span>Identity check on: your face reference is saved.</span>
      <button type="button" className={classes.linkButton} onClick={withdraw} disabled={busy}>
        <IconTrash size={14} /> Withdraw
      </button>
    </div>
  ) : (
    <div className={classes.choice}>
      <IconEyeOff size={16} />
      <span>No identity check: you chose to continue without it.</span>
    </div>
  );
}
