// The band at the top of each interviewer page: the page's title and
// buttons on a soft teal wash with a drawing on the right that fits the
// page (candidate network, interview tiles, charts...). The drawing is
// decoration only: hidden from screen readers, on phones and in print.
// Its colours are tokens (--cv-art-*), so it has a light and a dark look.

import { useId } from 'react';

import classes from './PageHero.module.css';

// Sound bars under the interview tiles (half heights, left to right).
const WAVE = [6, 12, 20, 10, 26, 16, 8, 22, 30, 18, 10, 24, 14, 8, 18, 12, 6, 16, 10, 20, 8, 14, 6];

// One drawing per page; each fits the box x 930-1420, y 30-320 (the
// motif layer below) and has one softly pulsing point.
const ART = {
  // Jobs: many CVs, one strong match.
  network: (
    <>
      <g className={classes.line} strokeOpacity="0.16">
        <line x1="960" y1="90" x2="1060" y2="170" />
        <line x1="960" y1="90" x2="1150" y2="70" />
        <line x1="1060" y1="170" x2="1150" y2="70" />
        <line x1="1150" y1="70" x2="1330" y2="80" />
        <line x1="1330" y1="80" x2="1385" y2="215" />
        <line x1="1120" y1="255" x2="1060" y2="170" />
        <line x1="1120" y1="255" x2="1010" y2="265" />
        <line x1="1010" y1="265" x2="1060" y2="170" />
        <line x1="1290" y1="275" x2="1385" y2="215" />
      </g>
      <g className={classes.line} strokeWidth="1.25" strokeOpacity="0.34">
        <line x1="1240" y1="160" x2="1060" y2="170" />
        <line x1="1240" y1="160" x2="1150" y2="70" />
        <line x1="1240" y1="160" x2="1330" y2="80" />
        <line x1="1240" y1="160" x2="1385" y2="215" />
        <line x1="1240" y1="160" x2="1290" y2="275" />
        <line x1="1240" y1="160" x2="1120" y2="255" />
      </g>
      <g className={classes.node} strokeOpacity="0.45" strokeWidth="1.25">
        <circle cx="960" cy="90" r="4" />
        <circle cx="1060" cy="170" r="4.5" />
        <circle cx="1150" cy="70" r="5" />
        <circle cx="1330" cy="80" r="4.5" />
        <circle cx="1385" cy="215" r="4" />
        <circle cx="1120" cy="255" r="4" />
        <circle cx="1010" cy="265" r="3.5" />
        <circle cx="1290" cy="275" r="4" />
      </g>
      <Focus x={1240} y={160} />
    </>
  ),
  // Home: the overview, rings around the interviewer with work on them.
  rings: (
    <>
      <g className={classes.line} fill="none">
        <circle cx="1240" cy="170" r="40" strokeOpacity="0.30" />
        <circle cx="1240" cy="170" r="72" strokeOpacity="0.22" />
        <circle cx="1240" cy="170" r="104" strokeOpacity="0.15" />
        <circle cx="1240" cy="170" r="136" strokeOpacity="0.09" />
      </g>
      <g className={classes.node} strokeOpacity="0.5" strokeWidth="1.25">
        <circle cx="1295" cy="124" r="5" />
        <circle cx="1172" cy="195" r="4.5" />
        <circle cx="1330" cy="222" r="5" />
        <circle cx="1160" cy="103" r="4" />
        <circle cx="1106" cy="194" r="4" />
        <circle cx="1287" cy="42" r="3.5" />
        <circle cx="1374" cy="147" r="3.5" />
      </g>
      <Focus x={1240} y={170} />
    </>
  ),
  // Interviews: two video tiles and the sound of the conversation.
  interview: (
    <>
      <g className={classes.node} strokeOpacity="0.35" strokeWidth="1.25">
        <rect x="1010" y="60" width="170" height="120" rx="14" />
        <rect x="1200" y="100" width="170" height="120" rx="14" />
      </g>
      <g className={classes.ink} fillOpacity="0.14">
        <circle cx="1095" cy="108" r="18" />
        <path d="M1060 160 a35 28 0 0 1 70 0 Z" />
        <circle cx="1285" cy="148" r="18" />
        <path d="M1250 200 a35 28 0 0 1 70 0 Z" />
      </g>
      <g className={classes.line} strokeWidth="4" strokeLinecap="round" strokeOpacity="0.22">
        {WAVE.map((h, i) => (
          <line key={i} x1={1030 + i * 15} y1={282 - h} x2={1030 + i * 15} y2={282 + h} />
        ))}
      </g>
      <Focus x={1166} y={76} small />
    </>
  ),
  // Reports: scores rising, the best one marked.
  chart: (
    <>
      <line className={classes.line} x1="990" y1="290" x2="1410" y2="290" strokeOpacity="0.2" />
      <g className={classes.node} strokeOpacity="0.3" strokeWidth="1.25">
        {[60, 95, 80, 130, 165].map((h, i) => (
          <rect key={h} x={1020 + i * 62} y={290 - h} width="36" height={h} rx="6" />
        ))}
      </g>
      <polyline
        className={classes.line}
        fill="none"
        strokeWidth="1.5"
        strokeOpacity="0.45"
        points="1038,210 1100,175 1162,190 1224,140 1286,105 1350,70"
      />
      <g className={classes.node} strokeOpacity="0.5" strokeWidth="1.25">
        <circle cx="1038" cy="210" r="4" />
        <circle cx="1100" cy="175" r="4" />
        <circle cx="1162" cy="190" r="4" />
        <circle cx="1224" cy="140" r="4" />
        <circle cx="1286" cy="105" r="4" />
      </g>
      <Focus x={1350} y={70} />
    </>
  ),
  // Interview analysis: question and answer, checked against evidence.
  qa: (
    <>
      <g className={classes.node} strokeOpacity="0.35" strokeWidth="1.25">
        <path d="M1000 72 h170 a16 16 0 0 1 16 16 v38 a16 16 0 0 1 -16 16 h-130 l-18 16 v-16 h-22 a16 16 0 0 1 -16 -16 v-38 a16 16 0 0 1 16 -16 Z" />
        <path d="M1160 170 h190 a16 16 0 0 1 16 16 v48 a16 16 0 0 1 -16 16 h-22 v16 l-18 -16 h-150 a16 16 0 0 1 -16 -16 v-48 a16 16 0 0 1 16 -16 Z" />
      </g>
      <g className={classes.ink} fillOpacity="0.16">
        <rect x="1004" y="94" width="120" height="8" rx="4" />
        <rect x="1004" y="112" width="80" height="8" rx="4" />
        <rect x="1164" y="192" width="150" height="8" rx="4" />
        <rect x="1164" y="210" width="170" height="8" rx="4" />
        <rect x="1164" y="228" width="100" height="8" rx="4" />
      </g>
      <path className={classes.line} d="M1186 106 C 1250 100, 1290 96, 1318 92" fill="none" strokeDasharray="4 6" strokeOpacity="0.35" />
      <g className={classes.line} fill="none" strokeWidth="3" strokeOpacity="0.45" strokeLinecap="round">
        <circle cx="1345" cy="88" r="26" />
        <line x1="1364" y1="107" x2="1388" y2="131" />
      </g>
      <Focus x={1345} y={88} small />
    </>
  ),
  // Knowledge base: reference documents and the passages found in them.
  documents: (
    <>
      <g className={classes.node} strokeOpacity="0.32" strokeWidth="1.25">
        <rect x="1080" y="85" width="130" height="165" rx="10" transform="rotate(-9 1145 168)" />
        <rect x="1110" y="80" width="130" height="165" rx="10" transform="rotate(-2 1175 163)" />
        <rect x="1140" y="78" width="130" height="165" rx="10" transform="rotate(6 1205 160)" />
      </g>
      <g className={classes.ink} fillOpacity="0.16" transform="rotate(6 1205 160)">
        <rect x="1158" y="102" width="70" height="8" rx="4" />
        <rect x="1158" y="122" width="94" height="6" rx="3" />
        <rect x="1158" y="138" width="86" height="6" rx="3" />
        <rect x="1158" y="154" width="94" height="6" rx="3" />
        <rect x="1158" y="170" width="60" height="6" rx="3" />
      </g>
      <g className={classes.line} strokeOpacity="0.3">
        <line x1="1272" y1="170" x2="1350" y2="95" />
        <line x1="1272" y1="170" x2="1395" y2="175" />
        <line x1="1272" y1="170" x2="1345" y2="255" />
      </g>
      <g className={classes.node} strokeOpacity="0.5" strokeWidth="1.25">
        <circle cx="1350" cy="95" r="4.5" />
        <circle cx="1395" cy="175" r="4.5" />
        <circle cx="1345" cy="255" r="4.5" />
      </g>
      <Focus x={1272} y={170} small />
    </>
  ),
};

// The drawing's strong point: a teal dot with a soft, slowly pulsing halo.
function Focus({ x, y, small = false }) {
  return (
    <g className={classes.ink}>
      <circle className={classes.pulse} cx={x} cy={y} r={small ? 22 : 34} fillOpacity="0.06" />
      <circle cx={x} cy={y} r={small ? 13 : 20} fillOpacity="0.1" />
      <circle cx={x} cy={y} r={small ? 5 : 7.5} fillOpacity="0.85" />
    </g>
  );
}

// art: network | rings | interview | chart | qa | documents. beside: the
// width (px) of controls on the right of a short header, so the drawing
// sits left of them instead of under them.
export default function PageHero({ art = 'network', beside = 0, children }) {
  const id = `hero${useId().replace(/[^a-zA-Z0-9]/g, '')}`; // safe inside url(#...)
  return (
    <div className={classes.hero} style={beside ? { '--hero-beside': `${beside}px` } : undefined}>
      <svg
        className={classes.art}
        viewBox="0 0 1440 360"
        preserveAspectRatio="xMaxYMid slice"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <linearGradient id={`${id}-wash`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" className={classes.wash1} />
            <stop offset="0.5" className={classes.wash2} />
            <stop offset="1" className={classes.wash3} />
          </linearGradient>
          <radialGradient id={`${id}-glow`} cx="1260" cy="30" r="420" gradientUnits="userSpaceOnUse">
            <stop offset="0" className={classes.stopInk} stopOpacity="0.16" />
            <stop offset="1" className={classes.stopInk} stopOpacity="0" />
          </radialGradient>
          <radialGradient id={`${id}-mint`} cx="960" cy="320" r="320" gradientUnits="userSpaceOnUse">
            <stop offset="0" className={classes.stopMint} stopOpacity="0.22" />
            <stop offset="1" className={classes.stopMint} stopOpacity="0" />
          </radialGradient>
          {/* Dot grid, faded out towards the text on the left. */}
          <pattern id={`${id}-dots`} width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="11" cy="11" r="1.2" className={classes.ink} fillOpacity="0.32" />
          </pattern>
          <radialGradient id={`${id}-dotfade`} cx="1210" cy="160" r="460" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#fff" />
            <stop offset="0.55" stopColor="#fff" stopOpacity="0.5" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
          <mask id={`${id}-dotmask`}>
            <rect width="1440" height="360" fill={`url(#${id}-dotfade)`} />
          </mask>
          {/* The band melts into the page at the bottom. */}
          <linearGradient id={`${id}-fade`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0.6" className={classes.stopFade} stopOpacity="0" />
            <stop offset="1" className={classes.stopFade} stopOpacity="1" />
          </linearGradient>
        </defs>

        <rect width="1440" height="360" fill={`url(#${id}-wash)`} />
        <rect width="1440" height="360" fill={`url(#${id}-glow)`} />
        <rect width="1440" height="360" fill={`url(#${id}-mint)`} />
        <g className={classes.drawing}>
          <rect width="1440" height="360" fill={`url(#${id}-dots)`} mask={`url(#${id}-dotmask)`} />
          <g className={classes.line} fill="none">
            <path d="M760 360 C 900 250, 1060 300, 1180 200 S 1380 60, 1460 40" strokeOpacity="0.08" />
            <path d="M820 360 C 960 270, 1100 320, 1220 225 S 1400 90, 1460 80" strokeOpacity="0.06" />
            <path d="M700 360 C 840 230, 1020 280, 1140 175 S 1360 30, 1460 0" strokeOpacity="0.05" />
          </g>
        </g>
        <rect width="1440" height="360" fill={`url(#${id}-fade)`} />
      </svg>
      {/* The page's drawing: always whole, as high as the band, on the right. */}
      <svg
        className={`${classes.motif} ${beside ? classes.beside : ''}`}
        viewBox="930 30 490 290"
        preserveAspectRatio="xMaxYMid meet"
        aria-hidden="true"
        focusable="false"
      >
        {ART[art]}
      </svg>
      <div className={classes.content}>{children}</div>
    </div>
  );
}
