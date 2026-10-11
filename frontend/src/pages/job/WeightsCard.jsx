// "Scoring weights" on the job page (F2). Not in the design: added on the
// user's request (human control). The interviewer's weights win; otherwise
// the Hiring Assistant's suggestion; otherwise defaults. Four whole
// percentages that must add up to 100 (the backend checks it too).

import { Button, Group, NumberInput } from '@mantine/core';
import { IconAdjustments, IconSparkles } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import { apiDelete, apiPut } from '../../api/client';
import classes from './JobPage.module.css';

export const WEIGHT_FIELDS = [
  ['skills', 'Technical skills'],
  ['experience', 'Relevant experience'],
  ['qualifications', 'Qualifications'],
  ['ats', 'ATS CV–JD match'],
];

// Only the four numbers of a weights object.
function numbers(weights) {
  return Object.fromEntries(WEIGHT_FIELDS.map(([key]) => [key, weights[key]]));
}

// Where the current weights come from, in plain words.
function sourceText(weights) {
  if (weights.source === 'interviewer') return 'Set by you.';
  if (weights.source === 'ai') return `Suggested by the Hiring Assistant: ${weights.reason || ''}`;
  return 'Default weights. The Hiring Assistant suggests weights when it saves the job profile.';
}

// The card. job: from GET /jobs/{id}; onSaved(job) after a change.
export default function WeightsCard({ job, onSaved, disabled }) {
  const [values, setValues] = useState(numbers(job.weights));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setValues(numbers(job.weights)); // a new job or a saved change
  }, [job.weights]);

  const total = WEIGHT_FIELDS.reduce((sum, [key]) => sum + (Number(values[key]) || 0), 0);
  const changed = WEIGHT_FIELDS.some(([key]) => values[key] !== job.weights[key]);

  // Save the interviewer's weights (they win over the suggestion).
  async function save() {
    setBusy(true);
    setError(null);
    try {
      onSaved(await apiPut(`/jobs/${job.id}/weights`, values));
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  // Forget the interviewer's weights: the suggestion (or defaults) applies.
  async function reset() {
    setBusy(true);
    setError(null);
    try {
      onSaved(await apiDelete(`/jobs/${job.id}/weights`));
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={classes.weightsCard} aria-label="Scoring weights">
      <div className={classes.weightsTop}>
        <IconAdjustments size={20} className={classes.weightsIcon} />
        <div>
          <div className={classes.cardTitle}>Scoring weights</div>
          <div className={classes.cardHint}>
            {job.weights.source === 'ai' && <IconSparkles size={13} className={classes.sparkle} />}
            {sourceText(job.weights)}
          </div>
        </div>
      </div>
      <div className={classes.weightsGrid}>
        {WEIGHT_FIELDS.map(([key, label]) => (
          <NumberInput
            key={key}
            label={label}
            value={values[key]}
            onChange={(value) => setValues((current) => ({ ...current, [key]: Number(value) || 0 }))}
            min={0}
            max={100}
            step={5}
            suffix="%"
            allowDecimal={false}
            disabled={disabled || busy}
          />
        ))}
      </div>
      <Group justify="space-between" gap={8} className={classes.weightsBottom}>
        <span className={total === 100 ? classes.totalOk : classes.totalBad} aria-live="polite">
          Total {total}%{total !== 100 && ' · must be 100%'}
        </span>
        <Group gap={8}>
          {job.weights.source === 'interviewer' && (
            <Button variant="default" size="xs" onClick={reset} disabled={disabled} loading={busy && !changed}>
              {job.ai_weights ? 'Use AI suggestion' : 'Use defaults'}
            </Button>
          )}
          <Button size="xs" onClick={save} disabled={disabled || !changed || total !== 100} loading={busy && changed}>
            Save weights
          </Button>
        </Group>
      </Group>
      {error && <div className={classes.weightsError}>{error}</div>}
    </section>
  );
}
