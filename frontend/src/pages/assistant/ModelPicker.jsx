// AI model picker under the chat: which model answers, and how much of its
// free daily quota CandiVue has used. Google has no API for the quota left,
// so the count is ours; the limit appears once Google has reported it, and
// "Usage on Google" opens Google's own numbers.

import { Anchor, Select } from '@mantine/core';
import { IconCpu, IconExternalLink } from '@tabler/icons-react';

import classes from './Assistant.module.css';

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

// The picker line. models/usageUrl come from GET /api/ai/models.
export default function ModelPicker({ models, usageUrl, onChange, busy }) {
  const chosen = models.find((model) => model.selected);
  const options = models.map((model) => ({
    value: model.name,
    label: model.blocked_until ? `${model.name} · limit reached` : model.name,
  }));

  return (
    <div className={classes.modelBar}>
      <IconCpu size={14} />
      <span>AI model</span>
      <Select
        size="xs"
        data={options}
        value={chosen?.name ?? null}
        onChange={(name) => name && name !== chosen?.name && onChange(name)}
        allowDeselect={false}
        disabled={busy}
        comboboxProps={{ position: 'top-start' }}
        aria-label="AI model"
        className={classes.modelSelect}
      />
      {chosen && (
        <span className={chosen.blocked_until ? classes.modelBlocked : undefined}>{usageText(chosen)}</span>
      )}
      <Anchor href={usageUrl} target="_blank" rel="noopener noreferrer" fz={12} className={classes.modelLink}>
        Usage on Google <IconExternalLink size={12} />
      </Anchor>
    </div>
  );
}
