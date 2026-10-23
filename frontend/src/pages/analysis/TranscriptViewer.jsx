// The saved transcript (design: Interview Analysis.dc.html, frame 1b):
// search, speaker filter and download; Q numbers in the margin link a turn
// to its Q&A unit, and the turn a source chip points to is highlighted.

import { Button, SegmentedControl, TextInput, UnstyledButton } from '@mantine/core';
import { IconDownload, IconSearch } from '@tabler/icons-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import classes from './Analysis.module.css';
import { clock, filterTurns, pairOfTurn, transcriptText } from './analysisFormat';

// Save the transcript as a text file.
function download(turns, fileName) {
  const url = URL.createObjectURL(new Blob([transcriptText(turns)], { type: 'text/plain' }));
  const link = Object.assign(document.createElement('a'), { href: url, download: fileName });
  link.click();
  URL.revokeObjectURL(url);
}

export default function TranscriptViewer({ turns, pairs, highlight, fileName, onPickPair }) {
  const [query, setQuery] = useState('');
  const [speaker, setSpeaker] = useState('all');
  const highlighted = useRef(null);
  const qids = useMemo(() => pairOfTurn(pairs), [pairs]);
  const shown = filterTurns(turns, query, speaker);

  // Bring the highlighted turn into view (opened from a source chip).
  useEffect(() => {
    highlighted.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [highlight]);

  return (
    <section className={classes.viewer}>
      <div className={classes.viewerTools}>
        <TextInput
          className={classes.search}
          leftSection={<IconSearch size={16} />}
          placeholder="Search the transcript"
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          aria-label="Search the transcript"
        />
        <SegmentedControl
          value={speaker}
          onChange={setSpeaker}
          data={[
            { value: 'all', label: 'All' },
            { value: 'interviewer', label: 'Interviewer' },
            { value: 'candidate', label: 'Candidate' },
          ]}
        />
        <Button
          variant="default"
          leftSection={<IconDownload size={15} />}
          onClick={() => download(turns, fileName)}
          disabled={turns.length === 0}
        >
          Download
        </Button>
      </div>
      <div className={classes.viewerBody}>
        {shown.map((turn) => {
          const qid = qids.get(turn.id);
          return (
            <div
              key={turn.id}
              ref={turn.id === highlight ? highlighted : undefined}
              className={`${classes.line} ${turn.id === highlight ? classes.highlight : ''}`}
            >
              {qid ? (
                <UnstyledButton className={classes.lineQid} onClick={() => onPickPair(qid)}>
                  {qid}
                </UnstyledButton>
              ) : (
                <span />
              )}
              <span className={classes.mono}>{clock(turn.start_ms)}</span>
              <span className={turn.speaker === 'interviewer' ? classes.interviewer : classes.candidate}>
                {turn.speaker === 'interviewer' ? 'Interviewer' : 'Candidate'}
              </span>
              <span>{turn.text}</span>
            </div>
          );
        })}
        {turns.length === 0 && <div className={classes.noHits}>No transcript was saved for this interview.</div>}
        {turns.length > 0 && shown.length === 0 && (
          <div className={classes.noHits}>
            {query.trim() ? `No turns match “${query.trim()}”. Try a shorter word.` : 'No turns from this speaker.'}
          </div>
        )}
      </div>
      <div className={classes.viewerFoot}>
        <span>Times are minutes:seconds from the start · Q numbers link turns to the Q&amp;A analysis</span>
        <span>
          {shown.length} of {turns.length} turns
        </span>
      </div>
    </section>
  );
}
