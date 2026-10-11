// The interviewer's live interview (design: Live Interview, option 1a): the
// call on the left with the live transcript under it; a right column with
// the identity check (F7) and the Hiring Assistant (§4B-10). The interviewer
// joins from the Interviews page ("Join now"), any time until the interview
// is ended. Interviewers only (route guard + backend).

import { useDocumentTitle } from '@mantine/hooks';
import { IconMessageCircle, IconTextCaption, IconUserCheck } from '@tabler/icons-react';
import { LiveKitRoom } from '@livekit/components-react';
import { DisconnectReason } from 'livekit-client';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { apiGet, apiPost } from '../../api/client';
import { ErrorBanner, Skeleton } from '../../components/Feedback';
import { notifyDone, notifyError } from '../../components/notify';
import classes from './InterviewRoom.module.css';
import CallView from './CallView';
import { liveKitUrl } from './liveKit';

// A side panel with a title (its content is added by later steps).
function Panel({ icon: Icon, title, note, children }) {
  return (
    <section className={classes.panel}>
      <div className={classes.panelHead}>
        <Icon size={17} />
        {title}
        {note && <span className={classes.panelNote}>{note}</span>}
      </div>
      <div className={classes.panelBody}>{children}</div>
    </section>
  );
}

export default function InterviewRoomPage() {
  const { interviewId } = useParams();
  const navigate = useNavigate();
  const [interview, setInterview] = useState(null);
  const [token, setToken] = useState(null);
  const [failed, setFailed] = useState(null);
  const [ending, setEnding] = useState(false);
  useDocumentTitle(`Interview: ${interview?.candidate_name ?? '…'} · CandiVue AI`);

  // Load the interview and a ticket for its room.
  useEffect(() => {
    Promise.all([apiGet(`/interviews/${interviewId}`), apiPost(`/interviews/${interviewId}/room`)])
      .then(([details, ticket]) => {
        setInterview(details);
        setToken(ticket.token);
      })
      .catch((error) => setFailed(error.message));
  }, [interviewId]);

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
      <div className={classes.page}>
        <ErrorBanner title="You can’t join this interview.">{failed}</ErrorBanner>
      </div>
    );
  }
  if (!token) {
    return (
      <div className={classes.page}>
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
      className={classes.page}
      onDisconnected={(reason) => {
        // Ended elsewhere (e.g. another tab): leave the room page.
        if (reason === DisconnectReason.ROOM_DELETED) navigate('/interviews');
      }}
    >
      <div className={classes.layout}>
        <div className={classes.main}>
          <CallView
            role="interviewer"
            title={`${interview.candidate_name} · ${interview.job_title}`}
            otherName={interview.candidate_name}
            onFinish={end}
            finishing={ending}
          />
          <Panel icon={IconTextCaption} title="Live transcript" note="Saved as you go">
            The transcript will appear here while you talk (speech-to-text is the next step).
          </Panel>
        </div>
        <aside className={classes.side}>
          <Panel icon={IconUserCheck} title="Identity check">
            Face and voice identification comes in a later step. Confirm the candidate’s identity
            another way for now.
          </Panel>
          <Panel icon={IconMessageCircle} title="Hiring Assistant" note="Only you see this">
            Question suggestions from the question bank come in a later step.
          </Panel>
        </aside>
      </div>
    </LiveKitRoom>
  );
}
