// The CandiVue AI logo: the mark (an image file in public/assets/brand),
// "CandiVue" and the "✦ AI" pill.

import classes from './Logo.module.css';

const MARK = '/assets/brand/candivue-logo-mark.svg';
// Plays a short intro, then a gentle loop; the file itself shows the still
// logo when "reduce motion" is on.
const MARK_ANIMATED = '/assets/brand/candivue-logo-mark-animated.svg';

// The mark alone. animated: the moving version (app top bar only).
export function LogoMark({ size = 36, animated = false }) {
  return (
    <img
      className={classes.mark}
      src={animated ? MARK_ANIMATED : MARK}
      width={size}
      height={size}
      alt=""
      draggable={false}
    />
  );
}

// Mark + "CandiVue" + "✦ AI" pill. size: md (top bars) or lg (login brand
// panel). onDark: colours for the dark login brand panel.
export default function Logo({ size = 'md', onDark = false, animated = false }) {
  return (
    <span className={`${classes.logo} ${classes[size]} ${onDark ? classes.onDark : ''}`}>
      <LogoMark size={size === 'lg' ? 44 : 36} animated={animated} />
      <span className={classes.word}>
        Candi<span className={classes.vue}>Vue</span>
      </span>
      <span className={classes.ai}>
        <span aria-hidden="true">✦ </span>AI
      </span>
    </span>
  );
}
