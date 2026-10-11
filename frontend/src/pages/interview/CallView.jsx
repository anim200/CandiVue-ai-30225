// The video call itself, shared by the interviewer's room and the candidate's
// page (design: SessionBar, VideoTile ×2, CallControls). It must sit inside
// <LiveKitRoom>, which connects to the LiveKit server with the ticket from
// the backend. LiveKit reconnects by itself after a dropped connection; the
// bar then says "Reconnecting…".

import { Button } from '@mantine/core';
import {
  RoomAudioRenderer,
  VideoTrack,
  isTrackReference,
  useConnectionState,
  useLocalParticipant,
  useTracks,
} from '@livekit/components-react';
import { IconMicrophone, IconMicrophoneOff, IconPhoneOff, IconVideo, IconVideoOff } from '@tabler/icons-react';
import { Track } from 'livekit-client';
import { useEffect, useState } from 'react';

import ConfirmModal from '../../components/ConfirmModal';
import classes from './Call.module.css';

// "12:48" since the call opened on this screen.
function useElapsed() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`;
}

// One person's video, or their name while the camera is off / not joined.
function VideoTile({ trackRef, label, waiting, small }) {
  const participant = trackRef?.participant;
  const showVideo = isTrackReference(trackRef) && !trackRef.publication.isMuted;
  return (
    <div className={`${classes.tile} ${small ? classes.small : ''}`}>
      {showVideo ? (
        <VideoTrack trackRef={trackRef} className={classes.video} />
      ) : (
        <div className={classes.placeholder}>{participant ? `${label} · camera off` : waiting}</div>
      )}
      {participant && (
        <span className={classes.label}>
          {participant.isMicrophoneEnabled ? <IconMicrophone size={14} /> : <IconMicrophoneOff size={14} />}
          {label}
        </span>
      )}
    </div>
  );
}

const CONNECTION = {
  connected: { text: 'Connected', className: classes.ok },
  connecting: { text: 'Connecting…', className: classes.busy },
  reconnecting: { text: 'Reconnecting…', className: classes.busy },
  signalReconnecting: { text: 'Reconnecting…', className: classes.busy },
  disconnected: { text: 'Disconnected', className: classes.bad },
};

// The call: bar, the other person's video, own video, controls.
// role: "interviewer" (End session) or "candidate" (Leave).
// otherName: the person on the other side; onFinish: End / Leave confirmed.
export default function CallView({ role, title, otherName, notice, onFinish, finishing }) {
  const tracks = useTracks([{ source: Track.Source.Camera, withPlaceholder: true }], { onlySubscribed: false });
  const own = tracks.find((t) => t.participant.isLocal);
  const other = tracks.find((t) => !t.participant.isLocal);
  const connection = CONNECTION[useConnectionState()] ?? CONNECTION.connecting;
  const { localParticipant, isMicrophoneEnabled, isCameraEnabled } = useLocalParticipant();
  const [confirming, setConfirming] = useState(false);
  const elapsed = useElapsed();
  const interviewer = role === 'interviewer';

  return (
    <div className={classes.call}>
      <div className={classes.bar}>
        {interviewer && <span className={classes.live}>LIVE</span>}
        <span className={classes.title}>{title}</span>
        <span className={classes.timer}>{elapsed}</span>
        {notice && <span className={classes.notice}>{notice}</span>}
        <span className={`${classes.connection} ${connection.className}`}>{connection.text}</span>
      </div>

      <div className={classes.stage}>
        <VideoTile
          trackRef={other}
          label={other?.participant.name || otherName}
          waiting={`${otherName} hasn’t joined yet. They appear here as soon as they join.`}
        />
        <VideoTile trackRef={own} label="You" small />
        {connection.text === 'Reconnecting…' && (
          <div className={classes.overlay} role="status">
            Reconnecting… You’ll be back in the same interview automatically.
          </div>
        )}
      </div>

      <div className={classes.controls}>
        <Button
          variant={isMicrophoneEnabled ? 'default' : 'light'}
          color={isMicrophoneEnabled ? undefined : 'red'}
          leftSection={isMicrophoneEnabled ? <IconMicrophone size={17} /> : <IconMicrophoneOff size={17} />}
          onClick={() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
        >
          {isMicrophoneEnabled ? 'Mute' : 'Unmute'}
        </Button>
        <Button
          variant={isCameraEnabled ? 'default' : 'light'}
          color={isCameraEnabled ? undefined : 'red'}
          leftSection={isCameraEnabled ? <IconVideo size={17} /> : <IconVideoOff size={17} />}
          onClick={() => localParticipant.setCameraEnabled(!isCameraEnabled)}
        >
          {isCameraEnabled ? 'Camera off' : 'Camera on'}
        </Button>
        <Button color="#B03A2E" leftSection={<IconPhoneOff size={17} />} onClick={() => setConfirming(true)}>
          {interviewer ? 'End session' : 'Leave'}
        </Button>
      </div>

      {/* Plays the other person's voice. */}
      <RoomAudioRenderer />

      <ConfirmModal
        opened={confirming}
        onClose={() => setConfirming(false)}
        title={interviewer ? 'End the interview?' : 'Leave the interview?'}
        confirmLabel={interviewer ? 'End interview' : 'Leave'}
        busy={finishing}
        onConfirm={() => {
          setConfirming(false);
          onFinish();
        }}
      >
        {interviewer
          ? 'Everyone leaves the call and the candidate’s link stops working. An ended interview cannot be restarted.'
          : 'You can rejoin with the same link until the interviewer ends the interview.'}
      </ConfirmModal>
    </div>
  );
}
