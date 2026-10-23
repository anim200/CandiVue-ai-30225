// The AI's icon everywhere in the app (it replaces the sparkle): the small
// CandiVue "match" mark, three candidate dots linked to a centre. Still by
// default; active: candidate dots travel to the centre, which pulses (while
// the AI works). Used like a Tabler icon (size, className), so it fits menus,
// buttons and empty states. Its colour is the text colour around it unless
// a parent sets --mark-icon / --mark-accent (the chat uses the signal colours).

import classes from './AssistantMark.module.css';

export default function AssistantMark({ size = 24, active = false, className = '', style }) {
  return (
    <svg
      className={`${classes.mark} ${active ? classes.active : ''} ${className}`}
      viewBox="0 0 40 40"
      width={size}
      height={size}
      style={style}
      aria-hidden="true"
      focusable="false"
    >
      <circle className={classes.ring} cx="20" cy="20" r="14" />
      <g className={classes.lines}>
        <line x1="14" y1="14.5" x2="21.5" y2="21.5" />
        <line x1="26.5" y1="14" x2="21.5" y2="21.5" />
        <line x1="14.5" y1="26.5" x2="21.5" y2="21.5" />
      </g>
      <g className={classes.nodes}>
        <circle cx="14" cy="14.5" r="2.2" />
        <circle cx="26.5" cy="14" r="2.2" />
        <circle cx="14.5" cy="26.5" r="2.2" />
      </g>
      {active && (
        <>
          {/* The signals travel from each dot to the centre. */}
          <circle className={classes.sig} cx="14" cy="14.5" r="1.7" style={{ '--dx': '7.5px', '--dy': '7px' }} />
          <circle
            className={`${classes.sig} ${classes.sig2}`}
            cx="26.5"
            cy="14"
            r="1.7"
            style={{ '--dx': '-5px', '--dy': '7.5px' }}
          />
          <circle
            className={`${classes.sig} ${classes.sig3}`}
            cx="14.5"
            cy="26.5"
            r="1.7"
            style={{ '--dx': '7px', '--dy': '-5px' }}
          />
        </>
      )}
      <circle className={classes.core} cx="21.5" cy="21.5" r="4" />
    </svg>
  );
}
