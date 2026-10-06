// The job board result in the chat (design: PostingResultCard in frame 1a,
// "Posting failed" frame 2e). Three cases: posted, failed, form link missing.

import { Anchor, Group, Text } from '@mantine/core';
import { IconAlertTriangle, IconCircleCheck, IconForms } from '@tabler/icons-react';
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
        <IconCircleCheck size={20} color="#2D7A4E" style={{ flex: 'none' }} />
        <div className={classes.postingBody}>
          <Text fz={14} fw={600}>
            Posted to the job board
          </Text>
          <Text fz={14} c="#48535B" lh={1.5}>
            Applicants send CVs through the application form linked in the post.
          </Text>
          <Group gap={12}>
            <Anchor href={result.url} target="_blank" rel="noopener noreferrer" fz={13} fw={600}>
              View post
            </Anchor>
            {result.form_url && (
              <Anchor href={result.form_url} target="_blank" rel="noopener noreferrer" fz={13} fw={600}>
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
        <IconForms size={20} color="#C08A1E" style={{ flex: 'none' }} />
        <div className={classes.postingBody}>
          <Text fz={14} fw={600}>
            Not posted yet: the application form link is missing
          </Text>
          <Text fz={14} c="#48535B" lh={1.5}>
            Send the Google Form link in the chat, then post the job.
          </Text>
          {onPost && (
            <Group gap={12}>
              <Anchor component="button" type="button" fz={13} fw={600} onClick={onPost} disabled={busy}>
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
      <IconAlertTriangle size={20} color="#B03A2E" style={{ flex: 'none' }} />
      <div className={classes.postingBody}>
        <Text fz={14} fw={600}>
          The job board didn’t accept the post
        </Text>
        <Text fz={14} c="#48535B" lh={1.5}>
          I tried 3 times. The approved job description is saved, so nothing is lost.
          {result.message ? ` (${result.message})` : ''}
        </Text>
        <Group gap={12}>
          {onPost && (
            <Anchor component="button" type="button" fz={13} fw={600} onClick={onPost} disabled={busy}>
              Try again
            </Anchor>
          )}
          {approvedJd && (
            <Anchor component="button" type="button" fz={13} fw={600} onClick={copyJd}>
              {copied ? 'Copied' : 'Copy job description'}
            </Anchor>
          )}
        </Group>
      </div>
    </div>
  );
}
