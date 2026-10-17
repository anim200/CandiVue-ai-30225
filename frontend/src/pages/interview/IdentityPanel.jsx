// Who is in the call? (F7, interviewer only; design: Live Interview
// IdentityPanel.) The transcriber service compares the candidate's camera
// with the face reference they gave with consent and pushes each result
// here (data channel "identity"); the panel also asks the backend now and
// then, so nothing depends on the push. The profile shows only on a
// confident match; identity is never assumed.

import { Button, Loader } from '@mantine/core';
import { useDataChannel } from '@livekit/components-react';
import {
  IconBan,
  IconEyeOff,
  IconRefresh,
  IconUserCheck,
  IconUserQuestion,
  IconUserX,
} from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';

import { apiGet, apiPost } from '../../api/client';
import StatusBadge from '../../components/StatusBadge';
import { formatElapsed } from './callTime';
import classes from './IdentityPanel.module.css';

const CHECK_EVERY_MS = 10000; // the push does the fast work; this is the fallback
const BADGES = {
  matched: { tone: 'success', icon: IconUserCheck, text: 'Confident match' },
  low_confidence: { tone: 'warning', icon: IconUserQuestion, text: 'Low confidence' },
  no_match: { tone: 'danger', icon: IconUserX, text: 'No match' },
  no_face: { tone: 'warning', icon: IconEyeOff, text: 'No face in view' },
  several_faces: { tone: 'warning', icon: IconEyeOff, text: 'Several faces' },
  camera_off: { tone: 'neutral', icon: IconEyeOff, text: 'Camera off' },
  checking: { tone: 'info', icon: null, text: 'Checking…' },
  no_reference: { tone: 'neutral', icon: IconBan, text: 'No reference' },
  off: { tone: 'neutral', icon: IconBan, text: 'Not set up' },
};

// The profile shown on a confident match only.
function Profile({ profile }) {
  return (
    <div className={classes.profile}>
      <b className={classes.name}>{profile.name}</b>
      {profile.headline && <span className={classes.headline}>{profile.headline}</span>}
      {profile.score != null && (
        <span className={classes.score}>
          CV score <b>{Math.round(profile.score)}</b>
          {profile.rank && ` · rank ${profile.rank} of ${profile.ranked_count}`}
        </span>
      )}
      {profile.skills.length > 0 && (
        <div className={classes.skills}>
          {profile.skills.map((skill) => (
            <span key={skill}>{skill}</span>
          ))}
        </div>
      )}
      {profile.probe.length > 0 && (
        <div className={classes.probe}>
          <span>Areas to probe</span>
          <ul>
            {profile.probe.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function IdentityPanel({ interviewId }) {
  const [identity, setIdentity] = useState(null);
  const [checking, setChecking] = useState(false);

  const load = useCallback(() => {
    apiGet(`/interviews/${interviewId}/identity`)
      .then(setIdentity)
      .catch(() => {}); // the next round tries again
  }, [interviewId]);

  useEffect(() => {
    load();
    const timer = setInterval(load, CHECK_EVERY_MS);
    return () => clearInterval(timer);
  }, [load]);

  // A new result from the call: read the full view (with the profile).
  useDataChannel('identity', load);

  // "Check again": start with fresh pictures.
  async function recheck() {
    setChecking(true);
    try {
      setIdentity(await apiPost(`/interviews/${interviewId}/identity/recheck`));
    } finally {
      setChecking(false);
    }
  }

  if (!identity) return null;
  const badge = BADGES[identity.state] ?? BADGES.checking;
  const Icon = badge.icon;
  const similarity = identity.similarity;
  const active = !['no_reference', 'off'].includes(identity.state);

  return (
    <section className={classes.panel} aria-label="Identity check">
      <div className={classes.top}>
        <span className={classes.title}>Identity check</span>
        <StatusBadge tone={badge.tone} icon={Icon ? <Icon size={13} /> : <Loader size={10} color="currentColor" />}>
          {badge.text}
        </StatusBadge>
      </div>
      <p className={classes.text}>{identity.text}</p>
      {similarity != null && (
        <div className={classes.meter} title="Face similarity to the reference (a match needs about 40 or more)">
          <span>Face</span>
          <div className={classes.bar}>
            <div className={classes[badge.tone]} style={{ width: `${Math.max(0, similarity) * 100}%` }} />
          </div>
          <b>{Math.round(Math.max(0, similarity) * 100)}</b>
        </div>
      )}
      {identity.state === 'matched' && identity.profile && <Profile profile={identity.profile} />}
      {active && (
        <div className={classes.foot}>
          <span>
            {identity.state === 'matched' && identity.confirmed_at_ms != null
              ? `Confirmed at ${formatElapsed(identity.confirmed_at_ms / 1000)} · reference given with consent`
              : 'Compared every few seconds with the reference given with consent'}
          </span>
          <Button size="compact-xs" variant="subtle" leftSection={<IconRefresh size={13} />} onClick={recheck} loading={checking}>
            Check again
          </Button>
        </div>
      )}
    </section>
  );
}
