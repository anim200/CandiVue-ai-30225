// Who is in the call? (F7, §4B-15, interviewer only; design: Live Interview
// IdentityPanel.) Shows the photo the candidate sent with their application,
// so the interviewer can compare it with the video, and the result of the
// check-in: the candidate's camera pictures compared with that photo, with a
// match score (a fixed scale on the face similarity, not a probability).
// The profile shows only on a match; identity is never assumed. While the
// candidate has not checked in yet, the panel asks the backend now and then.

import { Loader, Tooltip } from '@mantine/core';
import { IconBan, IconPhotoOff, IconUserCheck, IconUserQuestion, IconUserX } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';

import { apiGet, apiGetFile } from '../../api/client';
import StatusBadge from '../../components/StatusBadge';
import classes from './IdentityPanel.module.css';

const CHECK_EVERY_MS = 8000; // until the candidate has checked in
const BADGES = {
  matched: { tone: 'success', icon: IconUserCheck, text: 'Match' },
  not_confirmed: { tone: 'warning', icon: IconUserQuestion, text: 'Not confirmed' },
  no_match: { tone: 'danger', icon: IconUserX, text: 'Different person' },
  other_applicant: { tone: 'danger', icon: IconUserX, text: 'Different person' },
  failed: { tone: 'warning', icon: IconUserQuestion, text: 'Check-in failed' },
  waiting: { tone: 'info', icon: null, text: 'Not checked in yet' },
  declined: { tone: 'neutral', icon: IconBan, text: 'Declined' },
  no_photo: { tone: 'neutral', icon: IconPhotoOff, text: 'No comparison' },
  off: { tone: 'neutral', icon: IconBan, text: 'Not set up' },
};
const SCALE_NOTE =
  'Match score: how alike the check-in pictures and the application photo are. ' +
  'From 60 % they match; below 40 % it is clearly another person. It is not a certainty.';

// The application photo (a small copy kept for the interviewer).
function ApplicationPhoto({ interviewId, available, reason }) {
  const [url, setUrl] = useState(null);

  useEffect(() => {
    if (!available) return undefined;
    let objectUrl;
    let stopped = false;
    apiGetFile(`/interviews/${interviewId}/identity/photo`)
      .then((blob) => {
        if (stopped) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {}); // shown as "no photo"
    return () => {
      stopped = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [interviewId, available]);

  if (available && url) {
    return <img className={classes.photo} src={url} alt="The photo sent with the application" />;
  }
  return (
    <Tooltip label={reason || 'Loading the application photo…'} withArrow multiline w={220}>
      <div className={classes.noPhoto} role="img" aria-label="No application photo">
        {available ? <Loader size={14} color="gray" /> : <IconPhotoOff size={22} />}
      </div>
    </Tooltip>
  );
}

// The match score as a bar with the 40 % and 60 % lines.
function ScoreBar({ score, tone }) {
  return (
    <Tooltip label={SCALE_NOTE} withArrow multiline w={260}>
      <div className={classes.meter}>
        <div className={classes.bar} aria-hidden="true">
          <div className={classes[tone]} style={{ width: `${score}%` }} />
          <i className={classes.mark} style={{ left: '40%' }} />
          <i className={classes.mark} style={{ left: '60%' }} />
        </div>
        <b aria-label={`Match score ${score} percent`}>{score}%</b>
      </div>
    </Tooltip>
  );
}

// The profile shown on a match only.
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

// "Checked in at 10:42 · compare the photo with the video".
function checkedText(checkedAt) {
  const time = new Date(checkedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `Checked in at ${time} · compare the photo with the video`;
}

export default function IdentityPanel({ interviewId }) {
  const [identity, setIdentity] = useState(null);

  const load = useCallback(() => {
    apiGet(`/interviews/${interviewId}/identity`)
      .then(setIdentity)
      .catch(() => {}); // the next round tries again
  }, [interviewId]);

  useEffect(() => {
    load();
  }, [load]);

  // Until the candidate checks in (or declines), look again now and then.
  const waiting = identity?.state === 'waiting';
  useEffect(() => {
    if (!waiting) return undefined;
    const timer = setInterval(load, CHECK_EVERY_MS);
    return () => clearInterval(timer);
  }, [waiting, load]);

  if (!identity) return null;
  const badge = BADGES[identity.state] ?? BADGES.waiting;
  const Icon = badge.icon;

  return (
    <section className={classes.panel} aria-label="Identity check">
      <div className={classes.top}>
        <span className={classes.title}>Identity check</span>
        <StatusBadge tone={badge.tone} icon={Icon ? <Icon size={13} /> : <Loader size={10} color="currentColor" />}>
          {badge.text}
        </StatusBadge>
      </div>
      <div className={classes.body}>
        <ApplicationPhoto
          interviewId={interviewId}
          available={identity.photo.available}
          reason={identity.photo.text && `No application photo: ${identity.photo.text}`}
        />
        <div className={classes.result}>
          <p className={classes.text}>{identity.text}</p>
          {identity.score != null && <ScoreBar score={identity.score} tone={badge.tone} />}
        </div>
      </div>
      {identity.state === 'matched' && identity.profile && <Profile profile={identity.profile} />}
      {identity.checked_at && <div className={classes.foot}>{checkedText(identity.checked_at)}</div>}
    </section>
  );
}
