// AI model picker under the chat: which model answers, and how much of its
// free daily quota CandiVue has used. Google has no API for the quota left,
// so the count is ours; the limit appears once Google has reported it, and
// "Usage on Google" opens Google's own numbers. Not in the design (added on
// the user's request; styles in Composer.module.css).

import { Anchor, Select } from '@mantine/core';
import { IconCpu, IconExternalLink } from '@tabler/icons-react';

import classes from './Composer.module.css';

// "in 13 h" / "in 25 min" until the model can be used again.
function resetsIn(blockedUntil) {
  const minutes = Math.max(1, Math.round((new Date(blockedUntil) - Date.now()) / 60000));
  return minutes >= 60 ? `in ${Math.round(minutes / 60)} h` : `in ${minutes} min`;
}

// One model's usage as a short line, e.g. "6 of 20 requests today".
function usageText(model) {
  const count = model.daily_limit
    ? `${model.requests_today} of ${model.daily_limit} requests today`
    : `${model.requests_today} requests today`;
  return model.blocked_until ? `${count} · limit reached, resets ${resetsIn(model.blocked_until)}` : count;
}

// Meter colour: teal, amber from 70%, red when the limit is reached.
function levelClass(model, share) {
  if (model.blocked_until || share >= 1) return classes.levelFull;
  return share >= 0.7 ? classes.levelHigh : '';
}

// The usage meter and text for the chosen model.
function Usage({ model }) {
  const share = model.daily_limit ? Math.min(model.requests_today / model.daily_limit, 1) : 0;
  return (
    <span className={classes.usage}>
      {model.daily_limit && (
        <span
          className={classes.meter}
          role="meter"
          aria-label="Requests used today"
          aria-valuemin={0}
          aria-valuemax={model.daily_limit}
          aria-valuenow={model.requests_today}
        >
          <span
            className={`${classes.meterFill} ${levelClass(model, share)}`}
            style={{ width: `${Math.max(share * 100, 3)}%`, display: 'block' }}
          />
        </span>
      )}
      <span className={model.blocked_until ? classes.blocked : undefined}>
        {model.blocked_until && <span className={classes.pulseDot} />}
        {usageText(model)}
      </span>
    </span>
  );
}

// The picker line. models/usageUrl come from GET /api/ai/models.
export default function ModelPicker({ models, usageUrl, onChange, busy }) {
  const chosen = models.find((model) => model.selected);
  const options = models.map((model) => ({
    value: model.name,
    label: model.blocked_until ? `${model.name} · limit reached` : model.name,
  }));

  return (
    <div className={classes.modelBar}>
      <Select
        size="xs"
        w={{ base: 190, sm: 220 }}
        data={options}
        value={chosen?.name ?? null}
        onChange={(name) => name && name !== chosen?.name && onChange(name)}
        allowDeselect={false}
        disabled={busy}
        leftSection={<IconCpu size={15} className={classes.modelIcon} />}
        comboboxProps={{ position: 'top-start', transitionProps: { transition: 'pop', duration: 180 } }}
        classNames={{ input: classes.modelInput }}
        aria-label="AI model"
        title="AI model used by the Hiring Assistant"
      />
      {/* key: choosing another model replays the short highlight */}
      {chosen && <Usage key={chosen.name} model={chosen} />}
      <Anchor href={usageUrl} target="_blank" rel="noopener noreferrer" fz={13} className={classes.googleLink}>
        Usage on Google <IconExternalLink size={12} />
      </Anchor>
    </div>
  );
}
