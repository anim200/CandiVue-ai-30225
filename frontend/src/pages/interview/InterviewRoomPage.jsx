// The interviewer's live interview. Changes from the design (Live Interview,
// option 1a), on the user's request (13-10-2026): the candidate's CV in the
// left column instead of the app menu; the call with the live transcript
// under it; on the right the Hiring Assistant, a chat with the candidate and
// the full transcript as tabs (the transcript tab hides the small card under
// the call, so the video gets the room). The identity check (F7) sits in the CV column until it
// is built.
// Waiting room: the candidate waits until "Let in" (the backend refuses
// their ticket before that). This page sends a heartbeat every few seconds,
// so the candidate sees that the interviewer is here, and shows a banner
// with a soft chime when someone is waiting.
// Interviewers only (route guard + backend). The interviewer joins from the
// Interviews page ("Join now"), any time until the interview is ended.

import { Button, Drawer, Tooltip } from '@mantine/core';
import { useDocumentTitle, useMediaQuery } from '@mantine/hooks';
import { IconArrowLeft, IconFileText, IconMessageCircle, IconSparkles, IconTextCaption } from '@tabler/icons-react';
import { LiveKitRoom } from '@livekit/components-react';
import { DisconnectReason } from 'livekit-client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { apiGet, apiPost } from '../../api/client';
import ConfirmModal from '../../components/ConfirmModal';
import { ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyDone, notifyError } from '../../components/notify';
import { formatElapsed, overText, useElapsed } from './callTime';
import CallView, { CallConnection, onDeviceFailure } from './CallView';
import CvPanel from './CvPanel';
import classes from './InterviewRoom.module.css';
import { liveKitUrl } from './liveKit';
import RoomAssistant from './RoomAssistant';
import RoomChat from './RoomChat';
import { TranscriptView, useTranscript } from './TranscriptPanel';

const HEARTBEAT_MS = 4000;
// The check-in result in the "Let in" banner (F7, §4B-15): short label and
// colour; the full sentence is in the tooltip.
const CHECK_IN = {
  matched: ['ok', 'Photo match'],
  not_confirmed: ['warn', 'Not confirmed'],
  no_match: ['bad', 'Different person'],
  other_applicant: ['bad', 'Different person'],
  failed: ['warn', 'Check-in failed'],
  waiting: ['plain', 'Not checked in'],
  declined: ['plain', 'Skipped the face check'],
  no_photo: ['plain', 'No photo to compare'],
};

// The candidate's check-in result, before letting them in.
function CheckInChip({ identity }) {
  const shown = identity && CHECK_IN[identity.state];
  if (!shown) return null;
  const [tone, label] = shown;
  return (
    <Tooltip label={identity.text} withArrow multiline w={260}>
      <span className={`${classes.checkIn} ${classes[`checkIn_${tone}`]}`}>
        {label}
        {identity.score != null && ` · ${identity.score}%`}
      </span>
    </Tooltip>
  );
}

// A short, soft two-note chime (no sound file needed).
function chime() {
  try {
    const audio = new AudioContext();
    [660, 880].forEach((frequency, index) => {
      const tone = audio.createOscillator();
      const volume = audio.createGain();
      const start = audio.currentTime + index * 0.16;
      tone.frequency.value = frequency;
      volume.gain.setValueAtTime(0.0001, start);
      volume.gain.exponentialRampToValueAtTime(0.12, start + 0.02);
      volume.gain.exponentialRampToValueAtTime(0.0001, start + 0.3);
      tone.connect(volume).connect(audio.destination);
      tone.start(start);
      tone.stop(start + 0.32);
    });
    setTimeout(() => audio.close(), 1000);
  } catch {
    // no sound: the banner is still shown
  }
}

// The waiting room from the interviewer's side: a heartbeat every few
// seconds; chimes when the candidate starts waiting. Returns [lobby, admit].
function useLobby(interviewId, onTick) {
  const [lobby, setLobby] = useState(null);
  const wasWaiting = useRef(false);

  const beat = useCallback(async () => {
    try {
      const next = await apiPost(`/interviews/${interviewId}/presence`);
      if (next.candidate_waiting && !wasWaiting.current) chime();
      wasWaiting.current = next.candidate_waiting;
      setLobby(next);
      onTick?.();
    } catch {
      // the next heartbeat tries again
    }
  }, [interviewId, onTick]);

  useEffect(() => {
    beat();
    const timer = setInterval(beat, HEARTBEAT_MS);
    return () => clearInterval(timer);
  }, [beat]);

  async function admit() {
    try {
      setLobby(await apiPost(`/interviews/${interviewId}/admit`));
      wasWaiting.current = false;
    } catch (error) {
      notifyError('The candidate wasn’t let in.', error);
    }
  }
  return [lobby, admit];
}

const LONG_HOURS = 3; // live this long: probably never ended

// Timer with "+12 min over" once the planned length has passed, and a hint
// when an interview has been live for hours (often: never ended).
function Timer({ interview }) {
  const elapsed = useElapsed(interview.started_at);
  const over = elapsed / 60 - interview.duration_minutes;
  const long = elapsed >= LONG_HOURS * 3600;
  return (
    <span className={classes.timer}>
      {formatElapsed(elapsed)}
      {over >= 1 && (
        <span
          className={`${classes.over} ${long ? classes.overLong : ''}`}
          title={long ? `Live for over ${LONG_HOURS} hours. If the interview has finished, end it.` : undefined}
        >
          {overText(over)}
          {long && ' · end it if finished'}
        </span>
      )}
    </span>
  );
}

// Everything inside the call (it needs the LiveKit room).
function Room({ interview, interviewId, onInterview, onEnd, ending }) {
  const navigate = useNavigate();
  const refreshStart = useCallback(() => {
    // The start time is saved when the first person joins (webhook).
    if (!interview.started_at) apiGet(`/interviews/${interviewId}`).then(onInterview).catch(() => {});
  }, [interview.started_at, interviewId, onInterview]);
  const [lobby, admit] = useLobby(interviewId, refreshStart);
  const transcript = useTranscript(interviewId); // one poll for both views
  const [tab, setTab] = useState('assistant');
  const [unread, setUnread] = useState(0);
  const [cvOpen, setCvOpen] = useState(true);
  const [cvDrawer, setCvDrawer] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const narrow = useMediaQuery('(max-width: 75em)'); // CV as a drawer below ~1200px
  const name = interview.candidate_name;
  const waitingNow = lobby?.candidate_waiting;
  useDocumentTitle(`${waitingNow ? '● Waiting · ' : ''}Interview: ${name} · CandiVue AI`);

  const banner = waitingNow && (
    <div className={classes.lobbyBanner} role="status">
      <span className={classes.pulse} />
      <span>
        <b>{name}</b> is waiting to join
      </span>
      <CheckInChip identity={lobby.identity} />
      <Button size="compact-sm" radius="xl" onClick={admit}>
        Let in
      </Button>
    </div>
  );
  const waiting = lobby?.admitted ? (
    <span>
      <b>{name}</b> was let in and appears here once connected. If they left, they can rejoin with their link.
    </span>
  ) : (
    <span>
      Waiting for <b>{name}</b>. When they open their invitation link, they wait in the waiting room until you let them
      in.
    </span>
  );
  const cv = <CvPanel interviewId={interviewId} onCollapse={narrow ? () => setCvDrawer(false) : () => setCvOpen(false)} />;
  const showCvColumn = cvOpen && !narrow;

  return (
    <div className={classes.room}>
      <header className={classes.topbar}>
        <button type="button" className={classes.back} onClick={() => setLeaving(true)}>
          <IconArrowLeft size={16} /> Interviews
        </button>
        <span className={classes.live}>LIVE</span>
        <span className={classes.title}>
          <b>{name}</b>
          <span className={classes.job}>{interview.job_title}</span>
        </span>
        <Timer interview={interview} />
        <span className={classes.spacer} />
        {(narrow || !cvOpen) && (
          <Button
            size="compact-sm"
            variant="light"
            leftSection={<IconFileText size={15} />}
            onClick={() => (narrow ? setCvDrawer(true) : setCvOpen(true))}
          >
            CV
          </Button>
        )}
        <CallConnection />
      </header>

      <div className={`${classes.layout} ${showCvColumn ? classes.withCv : ''}`}>
        {showCvColumn && <aside className={classes.cvColumn}>{cv}</aside>}

        <main className={classes.center}>
          <CallView
            role="interviewer"
            otherName={name}
            waiting={waiting}
            banner={banner}
            onFinish={onEnd}
            finishing={ending}
          />
          {tab !== 'transcript' && (
            <TranscriptView
              data={transcript}
              candidateName={name}
              onExpand={() => setTab('transcript')}
              className={classes.transcript}
            />
          )}
        </main>

        <aside className={classes.side}>
          <div className={classes.tabs} role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'assistant'}
              className={`${classes.tab} ${tab === 'assistant' ? classes.tabActive : ''}`}
              onClick={() => setTab('assistant')}
              title="Only you see the assistant; the candidate never does"
            >
              <IconSparkles size={16} /> Assistant
            </button>
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
              aria-selected={tab === 'transcript'}
              className={`${classes.tab} ${tab === 'transcript' ? classes.tabActive : ''}`}
              onClick={() => setTab('transcript')}
              title="Only you see the transcript; the candidate never does"
            >
              <IconTextCaption size={16} /> Transcript
              {transcript.status === 'listening' && <span className={classes.liveDot} title="Listening" />}
            </button>
          </div>
          {/* Both stay mounted, so neither loses its messages when hidden. */}
          <div className={classes.tabPanel} hidden={tab !== 'assistant'}>
            <RoomAssistant interviewId={interviewId} />
          </div>
          <div className={classes.tabPanel} hidden={tab !== 'chat'}>
            <RoomChat
              path={`/interviews/${interviewId}/messages`}
              me="interviewer"
              otherName={name}
              active={tab === 'chat'}
              onUnread={setUnread}
            />
          </div>
          <div className={classes.tabPanel} hidden={tab !== 'transcript'}>
            <TranscriptView data={transcript} candidateName={name} variant="full" />
          </div>
        </aside>
      </div>

      <Drawer opened={narrow && cvDrawer} onClose={() => setCvDrawer(false)} withCloseButton={false} size={360} padding={0}>
        <div className={classes.drawerCv}>{cv}</div>
      </Drawer>

      <ConfirmModal
        opened={leaving}
        onClose={() => setLeaving(false)}
        title="Leave the call?"
        confirmLabel="Leave the call"
        cancelLabel="Stay"
        onConfirm={() => navigate('/interviews')}
      >
        The interview stays live: the candidate stays connected and you can rejoin from the Interviews page. To finish
        the interview, use End interview instead.
      </ConfirmModal>
    </div>
  );
}

export default function InterviewRoomPage() {
  const { interviewId } = useParams();
  const navigate = useNavigate();
  const [interview, setInterview] = useState(null);
  const [token, setToken] = useState(null);
  const [failed, setFailed] = useState(null);
  const [ending, setEnding] = useState(false);
  const [elsewhere, setElsewhere] = useState(false);

  // Load the interview and a ticket for its room.
  useEffect(() => {
    Promise.all([apiGet(`/interviews/${interviewId}`), apiPost(`/interviews/${interviewId}/room`)])
      .then(([details, ticket]) => {
        setInterview(details);
        setToken(ticket.token);
      })
      .catch((error) => setFailed(error.message));
  }, [interviewId]);

  // Opened in another tab, then "Use this tab": a new ticket rejoins here.
  async function rejoinHere() {
    try {
      setToken((await apiPost(`/interviews/${interviewId}/room`)).token);
      setElsewhere(false);
    } catch (error) {
      setFailed(error.message);
    }
  }

  // End the interview for everyone, then go back to the list.
  async function end() {
    setEnding(true);
    try {
      await apiPost(`/interviews/${interviewId}/end`);
      notifyDone(`Interview with ${interview.candidate_name} ended`);
      navigate('/interviews');
    } catch (error) {
      notifyError('The interview wasn’t ended.', error);
      setEnding(false);
    }
  }

  if (failed) {
    return (
      <div className={classes.message}>
        <ErrorBanner title="You can’t join this interview.">{failed}</ErrorBanner>
        <Button variant="default" leftSection={<IconArrowLeft size={16} />} onClick={() => navigate('/interviews')}>
          Back to Interviews
        </Button>
      </div>
    );
  }
  if (elsewhere) {
    return (
      <div className={classes.message}>
        <div className={classes.messageCard}>
          <b>This interview is open in another tab</b>
          Only one connection per person is possible. Close the other tab, or continue here.
          <Button onClick={rejoinHere}>Use this tab</Button>
        </div>
      </div>
    );
  }
  if (!token || !interview) {
    return (
      <div className={classes.message}>
        <Skeleton />
      </div>
    );
  }

  return (
    <LiveKitRoom
      serverUrl={liveKitUrl()}
      token={token}
      connect
      audio
      video
      className={classes.roomWrap}
      onMediaDeviceFailure={onDeviceFailure}
      onDisconnected={(reason) => {
        if (reason === DisconnectReason.ROOM_DELETED) navigate('/interviews'); // ended elsewhere
        if (reason === DisconnectReason.DUPLICATE_IDENTITY) setElsewhere(true);
      }}
    >
      <Room interview={interview} interviewId={interviewId} onInterview={setInterview} onEnd={end} ending={ending} />
    </LiveKitRoom>
  );
}
