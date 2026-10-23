// The three floating example cards on the login brand panel: a transcript
// moment, a "Met" criterion and a screening score. Every 6 seconds they
// fade out one after another, show the next example candidate and fade
// back in; the score bar fills again. Decorative only (aria-hidden) and
// synthetic data. With "reduce motion" on, the first candidate stays.

import { useReducedMotion } from '@mantine/hooks';
import { IconCheck } from '@tabler/icons-react';
import { useEffect, useState } from 'react';

import classes from './LoginPage.module.css';

const CANDIDATES = [
  {
    name: 'Candidate A',
    time: '02:47',
    quote: '“…added pagination and an index.”',
    criterion: 'Database performance',
    score: 82,
    look: { skin: '#C68E6A', hair: '#231813', style: 'short', shirt: '#4C6A92' },
  },
  {
    name: 'Candidate B',
    time: '05:12',
    quote: '“…ran five usability tests first.”',
    criterion: 'User research',
    score: 88,
    look: { skin: '#8D5A3B', hair: '#17110E', style: 'curly', shirt: '#D08A68' },
  },
  {
    name: 'Candidate C',
    time: '03:05',
    quote: '“…automated it with Python and pandas.”',
    criterion: 'Python',
    score: 76,
    look: { skin: '#F2CBA8', hair: '#8A4B2A', style: 'long', shirt: '#5E8C6A' },
  },
  {
    name: 'Candidate D',
    time: '04:20',
    quote: '“…scored each idea by impact and effort.”',
    criterion: 'Prioritisation',
    score: 84,
    look: { skin: '#E3B08A', hair: '#2E211B', style: 'bun', shirt: '#7A6AA8' },
  },
];

const EVERY_MS = 6000; // a new candidate every 6 s
const OUT_STEP_MS = 120; // the cards fade out one after another
const SWAP_AT_MS = 650; // content swaps once all three are faded out
const IN_STEP_MS = 150; // ...and they fade back in one after another
const FILL_AT_MS = 400; // the score bar fills after the cards are back

// Hair on top of the head, per hair style.
const HAIR = {
  short: (h) => <path d="M40 56C37 36 48 29 60 29S83 36 80 56C78 47 72 42 61 42S43 46 40 56Z" fill={h} />,
  long: (h) => <path d="M40 60C37 36 48 29 60 29S83 36 80 60C76 46 66 40 53 44C47 46 43 52 40 60Z" fill={h} />,
  bun: (h) => (
    <>
      <circle cx="60" cy="26" r="9" fill={h} />
      <path d="M40 56C37 36 48 30 60 30S83 36 80 56C77 46 70 41 60 41S43 46 40 56Z" fill={h} />
    </>
  ),
  curly: (h) =>
    [
      [42, 47, 8],
      [47, 37, 9],
      [60, 32, 10],
      [73, 37, 9],
      [78, 47, 8],
    ].map(([x, y, r]) => <circle key={x} cx={x} cy={y} r={r} fill={h} />),
};

// A small drawn face (head and shoulders), never a photo.
function Face({ look }) {
  const { skin, hair, style, shirt } = look;
  return (
    <span className={classes.face}>
      <svg viewBox="18 22 84 84">
        {style === 'long' && <path d="M36 60C34 35 46 27 60 27S86 35 84 60L86 96C78 101 42 101 34 96Z" fill={hair} />}
        {style === 'curly' && <ellipse cx="60" cy="50" rx="25" ry="23" fill={hair} />}
        <rect x="52" y="72" width="16" height="20" rx="6" fill={skin} />
        <path d="M18 122C20 98 37 88 52 86L60 98L68 86C83 88 100 98 102 122Z" fill={shirt} />
        <circle cx="41" cy="61" r="4" fill={skin} />
        <circle cx="79" cy="61" r="4" fill={skin} />
        <ellipse cx="60" cy="58" rx="19" ry="22" fill={skin} />
        {HAIR[style](hair)}
        <g fill="#14262A">
          <ellipse cx="53" cy="59" rx="1.9" ry="2.3" />
          <ellipse cx="67" cy="59" rx="1.9" ry="2.3" />
        </g>
        <path d="M55.5 70q4.5 3.2 9 0" fill="none" stroke="#5A2A26" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </span>
  );
}

// The three cards; they rotate through the example candidates.
export default function LoginCards() {
  const reduced = useReducedMotion(false, { getInitialValueInEffect: false });
  const [index, setIndex] = useState(0);
  const [out, setOut] = useState([false, false, false]); // card faded out?
  const [barFull, setBarFull] = useState(true); // false: empty, no animation

  useEffect(() => {
    if (reduced) return undefined;
    const timers = new Set();
    // setTimeout that is cleared when the page closes.
    const later = (fn, ms) => {
      const timer = setTimeout(() => {
        timers.delete(timer);
        fn();
      }, ms);
      timers.add(timer);
    };
    const fade = (n, value) => setOut((old) => old.map((v, i) => (i === n ? value : v)));

    const interval = setInterval(() => {
      if (document.hidden) return; // tab in the background: skip this turn
      [0, 1, 2].forEach((n) => later(() => fade(n, true), n * OUT_STEP_MS));
      later(() => {
        setBarFull(false);
        setIndex((i) => (i + 1) % CANDIDATES.length);
        [0, 1, 2].forEach((n) => later(() => fade(n, false), n * IN_STEP_MS));
        later(() => setBarFull(true), FILL_AT_MS);
      }, SWAP_AT_MS);
    }, EVERY_MS);

    return () => {
      clearInterval(interval);
      timers.forEach(clearTimeout);
    };
  }, [reduced]);

  const c = CANDIDATES[index];
  const card = (n, extra = '') => `${classes.chip} ${extra} ${out[n] ? classes.out : ''}`;

  return (
    <div className={classes.chips} aria-hidden="true">
      <div className={card(0, classes.quoteCard)}>
        <div className={classes.cardContent}>
          <Face look={c.look} />
          <span className={classes.timestamp}>{c.time}</span>
          <span className={classes.quote}>{c.quote}</span>
        </div>
      </div>
      <div className={card(1)} style={{ marginRight: 46, animationDelay: '-3s' }}>
        <div className={classes.cardContent}>
          <span className={classes.met}>
            <IconCheck size={12} />
            Met
          </span>
          {c.criterion}
        </div>
      </div>
      <div className={card(2)} style={{ marginRight: 12, animationDelay: '-6s' }}>
        <div className={classes.cardContent} style={{ gap: 12 }}>
          <span className={classes.score}>{c.score}</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span className={classes.scoreLabel}>{c.name} · screening</span>
            <div className={classes.scoreTrack}>
              <div
                className={`${classes.scoreBar} ${barFull ? '' : classes.barReset}`}
                style={{ width: barFull ? `${c.score}%` : 0 }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
