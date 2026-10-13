// The video call itself, shared by the interviewer's room and the candidate's
// page (design: VideoTile ×2, CallControls). It must sit inside
// <LiveKitRoom>, which connects to the LiveKit server with the ticket from
// the backend. LiveKit reconnects by itself after a dropped connection; the
// stage then says "Reconnecting…".
// - The stage fills the column: 16:9 when there is room, wider on short
//   screens. The other person's video is always shown whole and sharp in
//   the middle; a blurred copy of it fills the sides (like Meet or Zoom),
//   so the stage never shows empty bands.
// - The controls float over the bottom of the stage (below it on phones).
// - Full screen: the icon in the stage's top-right corner (Esc leaves it).
// - Screen sharing: the shared screen fills the stage and the cameras move
//   to a strip; your own shared screen is not shown back to you (it would
//   repeat itself endlessly), only a note with "Stop sharing".
// - A ring shows who is speaking.

import { Tooltip } from '@mantine/core';
import {
  RoomAudioRenderer,
  VideoTrack,
  isTrackReference,
  useConnectionState,
  useIsSpeaking,
  useLocalParticipant,
  useTracks,
} from '@livekit/components-react';
import {
  IconMaximize,
  IconMicrophone,
  IconMicrophoneOff,
  IconMinimize,
  IconPhoneOff,
  IconScreenShare,
  IconScreenShareOff,
  IconUser,
  IconVideo,
  IconVideoOff,
  IconWifiOff,
} from '@tabler/icons-react';
import { Track } from 'livekit-client';
import { useEffect, useRef, useState } from 'react';

import ConfirmModal from '../../components/ConfirmModal';
import { notifyError } from '../../components/notify';
import classes from './Call.module.css';

// Screen sharing needs getDisplayMedia (not on phones and tablets).
const CAN_SHARE = typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getDisplayMedia);

// Full screen for one element: [isFull, toggle]. The browser decides when it
// ends too (Esc), so the state follows its "fullscreenchange" event.
function useFullScreen(ref) {
  const [isFull, setIsFull] = useState(false);
  useEffect(() => {
    const follow = () => setIsFull(document.fullscreenElement === ref.current);
    document.addEventListener('fullscreenchange', follow);
    return () => document.removeEventListener('fullscreenchange', follow);
  }, [ref]);
  const toggle = () => (isFull ? document.exitFullscreen() : ref.current?.requestFullscreen());
  return [isFull, toggle];
}

// What to do when the browser cannot use a device, in plain words.
// what: "microphone", "camera" or "screen".
export function deviceProblem(error, what) {
  switch (error?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return `The browser blocked the ${what}. Click the icon left of the address bar, set ${
        what === 'camera' ? 'Camera' : 'Microphone'
      } to Allow, then reload the page. On Windows also check Settings → Privacy & security → ${
        what === 'camera' ? 'Camera' : 'Microphone'
      }.`;
    case 'NotFoundError':
    case 'OverconstrainedError':
      return `No ${what} was found. Plug one in (or choose another in the browser settings), then try again.`;
    case 'NotReadableError':
    case 'AbortError':
      return `Another app (e.g. Teams or Zoom) or another browser window is using the ${what}. Close it, then try again.`;
    default:
      return `Try again. If it keeps failing, reload the page; you rejoin the same interview.`;
  }
}

// For <LiveKitRoom onMediaDeviceFailure>: the microphone or camera could
// not be turned on when joining (e.g. blocked by the browser).
const FAILURE_NAMES = { PermissionDenied: 'NotAllowedError', NotFound: 'NotFoundError', DeviceInUse: 'NotReadableError' };
export function onDeviceFailure(failure, kind) {
  const what = kind === 'videoinput' ? 'camera' : 'microphone';
  notifyError(`Your ${what} couldn’t be turned on.`, {
    message: deviceProblem({ name: FAILURE_NAMES[failure] }, what),
  });
}

// Initials for a camera-off tile, e.g. "Alex Strong" → "AS".
function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

// One person's camera, or their initials while the camera is off.
// backdrop: a blurred copy of the video fills the space around it (the same
// stream shown twice; nothing extra is downloaded).
function CameraTile({ trackRef, label, className, backdrop = false }) {
  const participant = trackRef.participant;
  const speaking = useIsSpeaking(participant);
  const showVideo = isTrackReference(trackRef) && !trackRef.publication.isMuted;
  return (
    <div className={`${classes.tile} ${className} ${speaking ? classes.speaking : ''}`}>
      {showVideo && backdrop && <VideoTrack trackRef={trackRef} className={classes.backdrop} aria-hidden="true" />}
      {showVideo ? (
        <VideoTrack trackRef={trackRef} className={participant.isLocal ? classes.mirror : classes.video} />
      ) : (
        <div className={classes.cameraOff}>
          <span className={classes.initials}>{initials(label === 'You' ? participant.name : label)}</span>
          <span className={classes.offText}>Camera off</span>
        </div>
      )}
      <span className={classes.nameTag}>
        {participant.isMicrophoneEnabled ? (
          <IconMicrophone size={13} />
        ) : (
          <IconMicrophoneOff size={13} className={classes.mutedIcon} />
        )}
        {label}
      </span>
    </div>
  );
}

// A round control button with a tooltip. off: red (e.g. microphone muted);
// on: teal (e.g. sharing the screen now).
export function ControlButton({ label, off, on, onClick, children, disabled }) {
  return (
    <Tooltip label={label} withArrow openDelay={300}>
      <button
        type="button"
        className={`${classes.control} ${off ? classes.controlOff : ''} ${on ? classes.controlOn : ''}`}
        onClick={onClick}
        aria-label={label}
        disabled={disabled}
      >
        {children}
      </button>
    </Tooltip>
  );
}

const STATES = {
  connecting: 'Connecting…',
  reconnecting: 'Reconnecting…',
  signalReconnecting: 'Reconnecting…',
  disconnected: 'Connection lost',
};

// The call: stage, controls and the "are you sure" dialog.
// role: "interviewer" (End interview) or "candidate" (Leave).
// otherName: the person on the other side. waiting: what the stage shows
// while they are not in the call. banner: shown over the top of the stage
// (e.g. "… is waiting · Let in"). extraControls: more buttons (e.g. chat).
export default function CallView({ role, otherName, waiting, banner, extraControls, onFinish, finishing }) {
  const tracks = useTracks(
    [
      { source: Track.Source.Camera, withPlaceholder: true },
      { source: Track.Source.ScreenShare, withPlaceholder: false },
    ],
    { onlySubscribed: false },
  );
  const cameras = tracks.filter((t) => t.source === Track.Source.Camera);
  const own = cameras.find((t) => t.participant.isLocal);
  const other = cameras.find((t) => !t.participant.isLocal);
  const shares = tracks.filter((t) => t.source === Track.Source.ScreenShare && isTrackReference(t));
  const share = shares.find((t) => !t.participant.isLocal) ?? shares.find((t) => t.participant.isLocal);
  const connection = useConnectionState();
  const { localParticipant, isMicrophoneEnabled, isCameraEnabled, isScreenShareEnabled } = useLocalParticipant();
  const [confirming, setConfirming] = useState(false);
  const interviewer = role === 'interviewer';
  const callRef = useRef(null);
  const [isFull, toggleFull] = useFullScreen(callRef);
  const otherLabel = other?.participant.name || otherName;

  // Switch a device; a busy or blocked device gets a plain message.
  async function toggle(action, what) {
    try {
      await action();
    } catch (error) {
      // Closing the screen-share picker is a choice, not an error.
      if (what === 'screen' && error?.name === 'NotAllowedError') return;
      notifyError(`Your ${what} couldn’t be turned on.`, { message: deviceProblem(error, what) });
    }
  }

  // The "are you sure" dialog opens outside the call, so leave full screen
  // first or it would be hidden behind it.
  async function askToFinish() {
    if (document.fullscreenElement) await document.exitFullscreen();
    setConfirming(true);
  }

  // The large area: a shared screen, the other person, or the waiting text.
  let main;
  if (share?.participant.isLocal) {
    main = (
      <div className={classes.presenting}>
        <IconScreenShare size={34} />
        <div>You are sharing your screen</div>
        <button type="button" className={classes.stopShare} onClick={() => toggle(() => localParticipant.setScreenShareEnabled(false), 'screen')}>
          Stop sharing
        </button>
      </div>
    );
  } else if (share) {
    main = (
      <div className={`${classes.tile} ${classes.mainTile}`}>
        <VideoTrack trackRef={share} className={classes.screen} />
        <span className={classes.nameTag}>
          <IconScreenShare size={13} /> {otherLabel}’s screen
        </span>
      </div>
    );
  } else if (other) {
    main = <CameraTile trackRef={other} label={otherLabel} className={classes.mainTile} backdrop />;
  } else {
    main = (
      <div className={classes.waiting}>
        <span className={classes.waitingIcon}>
          <IconUser size={26} />
        </span>
        {waiting}
      </div>
    );
  }

  return (
    <div className={`${classes.call} ${isFull ? classes.full : ''}`} ref={callRef}>
      <div className={classes.stage}>
        {main}

        {/* While a screen is shared, both cameras sit in a strip. */}
        <div className={`${classes.strip} ${share ? classes.stripShare : ''}`}>
          {share && other && <CameraTile trackRef={other} label={otherLabel} className={classes.thumb} />}
          {own && <CameraTile trackRef={own} label="You" className={classes.thumb} />}
        </div>

        {document.fullscreenEnabled && ( // not on every phone (e.g. iPhone Safari)
          <Tooltip label={isFull ? 'Exit full screen' : 'Full screen'} withArrow>
            <button
              type="button"
              className={classes.fullButton}
              onClick={toggleFull}
              aria-label={isFull ? 'Exit full screen' : 'Full screen'}
            >
              {isFull ? <IconMinimize size={18} /> : <IconMaximize size={18} />}
            </button>
          </Tooltip>
        )}
        {banner && <div className={classes.banner}>{banner}</div>}
        {STATES[connection] && connection !== 'connecting' && (
          <div className={classes.overlay} role="status">
            <IconWifiOff size={26} />
            {connection === 'disconnected'
              ? 'The connection was lost. Reload the page to rejoin the same interview.'
              : 'Reconnecting… You’ll be back in the same interview automatically.'}
          </div>
        )}
      </div>

      <div className={classes.controls}>
        <ControlButton
          label={isMicrophoneEnabled ? 'Mute microphone' : 'Unmute microphone'}
          off={!isMicrophoneEnabled}
          onClick={() => toggle(() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled), 'microphone')}
        >
          {isMicrophoneEnabled ? <IconMicrophone size={20} /> : <IconMicrophoneOff size={20} />}
        </ControlButton>
        <ControlButton
          label={isCameraEnabled ? 'Turn camera off' : 'Turn camera on'}
          off={!isCameraEnabled}
          onClick={() => toggle(() => localParticipant.setCameraEnabled(!isCameraEnabled), 'camera')}
        >
          {isCameraEnabled ? <IconVideo size={20} /> : <IconVideoOff size={20} />}
        </ControlButton>
        {CAN_SHARE && (
          <ControlButton
            label={isScreenShareEnabled ? 'Stop sharing your screen' : 'Share your screen'}
            on={isScreenShareEnabled}
            onClick={() =>
              toggle(() => localParticipant.setScreenShareEnabled(!isScreenShareEnabled, { audio: false }), 'screen')
            }
          >
            {isScreenShareEnabled ? <IconScreenShareOff size={20} /> : <IconScreenShare size={20} />}
          </ControlButton>
        )}
        {extraControls}
        <button type="button" className={classes.finish} onClick={askToFinish}>
          <IconPhoneOff size={19} />
          {interviewer ? 'End interview' : 'Leave'}
        </button>
      </div>

      {/* Plays the other person's voice. */}
      <RoomAudioRenderer />

      <ConfirmModal
        opened={confirming}
        onClose={() => setConfirming(false)}
        title={interviewer ? 'End the interview?' : 'Leave the interview?'}
        confirmLabel={interviewer ? 'End interview' : 'Leave'}
        cancelLabel={interviewer ? 'Cancel' : 'Stay'}
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

// "Connected" / "Reconnecting…" for a page's header (call connection).
export function CallConnection() {
  const connection = useConnectionState();
  const text = connection === 'connected' ? 'Call connected' : (STATES[connection] ?? 'Connecting…');
  const tone = connection === 'connected' ? classes.ok : connection === 'disconnected' ? classes.bad : classes.busy;
  return <span className={`${classes.connection} ${tone}`}>{text}</span>;
}
