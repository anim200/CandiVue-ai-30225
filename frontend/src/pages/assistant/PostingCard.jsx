// The job board cards in the chat (design: PostingResultCard in frame 1a,
// "Posting failed" frame 2e): the "Post this job?" question after approval,
// and the result: posted, failed or form link missing.

import { Anchor, Button, Group, Text } from '@mantine/core';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconForms,
  IconSpeakerphone,
  IconWorldUpload,
} from '@tabler/icons-react';
import { useState } from 'react';

import classes from './Assistant.module.css';

// Plain text of the approved JD, for "Copy job description".
function jdAsText(jd, profile) {
  const c = jd.content;
  const lines = [c.title, '', c.about, '', 'Key responsibilities', ...c.responsibilities.map((r) => `- ${r}`)];
  const requirements = (profile?.requirements ?? []).map((r) => `- ${r.text} (${r.level})`);
  if (requirements.length) lines.push('', 'Requirements', ...requirements);
  if (c.work_arrangement) lines.push('', 'Work arrangement', c.work_arrangement);
  if (c.what_we_offer?.length) lines.push('', 'What we offer', ...c.what_we_offer.map((o) => `- ${o}`));
  if (c.equal_opportunity) lines.push('', c.equal_opportunity);
  return lines.join('\n');
}

// "Post this job to the job board?" with Post / Don't post (the graph waits
// for this answer). question: the pending_review from the backend.
export function PostConfirmCard({ question, onDecide, busy }) {
  return (
    <div className={`${classes.postingCard} ${classes.postConfirm}`}>
      <IconSpeakerphone size={20} color="var(--cv-warning-text-mid)" style={{ flex: 'none' }} />
      <div className={classes.postingBody}>
        <Text fz={15} fw={600}>
          Post this job to the job board?
        </Text>
        <Text fz={15} c="var(--cv-text-secondary)" lh={1.5}>
          {question.has_form
            ? `I’ll publish job description version ${question.version} on the job board with your application form link.`
            : `Job description version ${question.version} is approved, but the application form link is missing. If you post now, I’ll ask for the link first.`}
        </Text>
        <Group gap={8} mt={6}>
          <Button variant="default" size="xs" onClick={() => onDecide('skip')} disabled={busy}>
            Don’t post
          </Button>
          <Button size="xs" leftSection={<IconWorldUpload size={14} />} onClick={() => onDecide('post')} loading={busy}>
            Post to job board
          </Button>
        </Group>
      </div>
    </div>
  );
}

// One posting result card. onPost: post again (only on the newest card).
export default function PostingCard({ result, approvedJd, profile, onPost, busy }) {
  const [copied, setCopied] = useState(false);

  // Copy the approved JD so it can be posted by hand if needed.
  async function copyJd() {
    await navigator.clipboard.writeText(jdAsText(approvedJd, profile));
    setCopied(true);
  }

  if (result.status === 'posted') {
    return (
      <div className={classes.postingCard}>
        <IconCircleCheck size={20} color="var(--cv-success-text)" style={{ flex: 'none' }} />
        <div className={classes.postingBody}>
          <Text fz={15} fw={600}>
            Posted to the job board
          </Text>
          <Text fz={15} c="var(--cv-text-secondary)" lh={1.5}>
            Applicants send CVs through the application form linked in the post.
          </Text>
          <Group gap={12}>
            <Anchor href={result.url} target="_blank" rel="noopener noreferrer" fz={14} fw={600}>
              View post
            </Anchor>
            {result.form_url && (
              <Anchor href={result.form_url} target="_blank" rel="noopener noreferrer" fz={14} fw={600}>
                Application form
              </Anchor>
            )}
          </Group>
        </div>
      </div>
    );
  }

  if (result.status === 'needs_form') {
    return (
      <div className={classes.postingCard}>
        <IconForms size={20} color="var(--cv-warning-text-mid)" style={{ flex: 'none' }} />
        <div className={classes.postingBody}>
          <Text fz={15} fw={600}>
            Not posted yet: the application form link is missing
          </Text>
          <Text fz={15} c="var(--cv-text-secondary)" lh={1.5}>
            Send the Google Form link in the chat, then post the job.
          </Text>
          {onPost && (
            <Group gap={12}>
              <Anchor component="button" type="button" fz={14} fw={600} onClick={onPost} disabled={busy}>
                Post now
              </Anchor>
            </Group>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={classes.postingCard}>
      <IconAlertTriangle size={20} color="var(--cv-danger-text)" style={{ flex: 'none' }} />
      <div className={classes.postingBody}>
        <Text fz={15} fw={600}>
          The job board didn’t accept the post
        </Text>
        <Text fz={15} c="var(--cv-text-secondary)" lh={1.5}>
          I tried 3 times. The approved job description is saved, so nothing is lost.
          {result.message ? ` (${result.message})` : ''}
        </Text>
        <Group gap={12}>
          {onPost && (
            <Anchor component="button" type="button" fz={14} fw={600} onClick={onPost} disabled={busy}>
              Try again
            </Anchor>
          )}
          {approvedJd && (
            <Anchor component="button" type="button" fz={14} fw={600} onClick={copyJd}>
              {copied ? 'Copied' : 'Copy job description'}
            </Anchor>
          )}
        </Group>
      </div>
    </div>
  );
}
