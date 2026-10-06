// Shared empty, loading and error blocks used by every screen, so the states
// look the same everywhere (design "states" frames).

import { IconAlertCircle } from '@tabler/icons-react';

import classes from './Feedback.module.css';

// Red box: bold title, explanation and an optional "Try again" button.
export function ErrorBanner({ title, children, onRetry, icon: Icon = IconAlertCircle }) {
  return (
    <div className={classes.error} role="alert">
      <Icon size={20} className={classes.errorIcon} />
      <div className={classes.errorText}>
        <b>{title}</b> {children}
      </div>
      {onRetry && (
        <button type="button" className={classes.retry} onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

// Empty state: icon in a tinted circle, a title, a short text and an action.
export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className={classes.empty}>
      <span className={classes.emptyIcon}>
        <Icon size={24} />
      </span>
      <div className={classes.emptyTitle}>{title}</div>
      <div className={classes.emptyText}>{children}</div>
      {action}
    </div>
  );
}

// Pulsing grey bars shown while data loads; widths are percentages.
export function Skeleton({ widths = [60, 80, 70] }) {
  return (
    <div className={classes.skeleton} aria-label="Loading">
      {widths.map((width, index) => (
        <div key={index} className={classes.bar} style={{ width: `${width}%` }} />
      ))}
    </div>
  );
}
