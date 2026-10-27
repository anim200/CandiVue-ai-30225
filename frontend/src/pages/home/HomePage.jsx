// Home (dashboard, an addition to the design): what needs the interviewer
// now, in one look. Cards with the main numbers (they count up), "Needs
// you" (live and today's interviews, reports to review, jobs to screen),
// the next interviews and applications per day. Read-only: every button
// opens the page where the work is done. Interviewers only (GET
// /api/dashboard); refreshed every 30 seconds.

import { Avatar, Button } from '@mantine/core';
import { BarChart } from '@mantine/charts';
import { useDocumentTitle, useReducedMotion } from '@mantine/hooks';
import {
  IconBriefcase,
  IconCalendarEvent,
  IconChecks,
  IconFileAnalytics,
  IconFileText,
  IconMailCheck,
  IconPlayerPlay,
  IconPlayerRecord,
  IconScan,
  IconUsers,
} from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { apiGet } from '../../api/client';
import { loadSession } from '../../auth/session';
import { EmptyState, ErrorBanner, Skeleton } from '../../components/Feedback';
import PageHero from '../../components/PageHero';
import StatusBadge from '../../components/StatusBadge';
import { CreateJobButton } from '../JobsPage';
import classes from './Home.module.css';
import { chartDays, firstName, greeting, interviewTime, plural } from './homeFormat';

const REFRESH_MS = 30000;
const COUNT_UP_MS = 700;
const CARDS = [
  { key: 'open_jobs', label: 'Open jobs', icon: IconBriefcase, to: '/jobs' },
  { key: 'applications_week', label: 'Applications this week', icon: IconUsers, to: '/jobs' },
  { key: 'cvs_to_screen', label: 'CVs to screen', icon: IconScan, to: '/jobs', alert: true },
  { key: 'interviews_today', label: 'Interviews today', icon: IconCalendarEvent, to: '/interviews', alert: true },
  { key: 'reports_to_review', label: 'Reports to review', icon: IconFileAnalytics, to: '/reports', alert: true },
  { key: 'selected_month', label: 'Selected this month', icon: IconMailCheck, to: '/reports' },
];
const STEP_ICONS = { live: IconPlayerRecord, interview: IconCalendarEvent, review: IconFileText, screen: IconScan };

// A number that counts up from 0 when it first appears (not with "reduce
// motion"), then follows changes.
function useCountUp(value) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  const last = useRef(reduce ? value : 0); // where the next count starts
  useEffect(() => {
    if (reduce) {
      setShown(value);
      return undefined;
    }
    let frame;
    const start = performance.now();
    const from = last.current;
    const step = (now) => {
      const progress = Math.min(1, (now - start) / COUNT_UP_MS);
      const current = Math.round(from + (value - from) * (1 - (1 - progress) ** 3));
      last.current = current;
      setShown(current);
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, reduce]);
  return shown;
}

// One number card; it links to the page with the details.
function StatCard({ label, value, icon: Icon, to, alert }) {
  const shown = useCountUp(value);
  return (
    <Link to={to} className={`${classes.stat} ${alert && value > 0 ? classes.statAlert : ''}`}>
      <span className={classes.statIcon}>
        <Icon size={20} />
      </span>
      <span className={classes.statValue}>{shown}</span>
      <span className={classes.statLabel}>{label}</span>
    </Link>
  );
}

// "Needs you": one row per thing to do, with the button that does it.
function NextSteps({ steps }) {
  const navigate = useNavigate();
  if (steps.length === 0) {
    return (
      <EmptyState icon={IconChecks} title="You’re all caught up">
        Nothing needs you right now. New CVs, interviews and reports appear here.
      </EmptyState>
    );
  }
  return (
    <ul className={classes.steps}>
      {steps.map((step) => {
        const Icon = STEP_ICONS[step.kind] ?? IconChecks;
        return (
          <li key={`${step.kind}-${step.link}`} className={`${classes.step} ${classes[`step_${step.kind}`] ?? ''}`}>
            <span className={classes.stepIcon}>
              <Icon size={18} />
            </span>
            <span className={classes.stepText}>
              <b>{step.text}</b>
              {step.detail && step.kind !== 'screen' && <span>{step.detail}</span>}
            </span>
            <Button
              size="xs"
              variant={step.kind === 'live' ? 'filled' : 'light'}
              leftSection={step.kind === 'live' || step.kind === 'interview' ? <IconPlayerPlay size={14} /> : null}
              onClick={() => navigate(step.link)}
            >
              {step.action}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

// The next interviews, soonest first.
function Upcoming({ interviews }) {
  if (interviews.length === 0) {
    return <p className={classes.none}>No interviews planned. Invite shortlisted candidates in the Hiring Assistant.</p>;
  }
  return (
    <ul className={classes.upcoming}>
      {interviews.map((item) => (
        <li key={item.id}>
          <Avatar name={item.candidate_name} color="initials" size={34} radius="xl" />
          <span className={classes.who}>
            <b>{item.candidate_name}</b>
            <span>{item.job_title}</span>
          </span>
          <span className={classes.when}>
            {item.status === 'live' ? (
              <StatusBadge tone="info">Live now</StatusBadge>
            ) : (
              interviewTime(item.scheduled_at)
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function HomePage() {
  useDocumentTitle('Home · CandiVue AI');
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const name = firstName(loadSession()?.user?.name);

  const load = useCallback(async () => {
    try {
      setData(await apiGet('/dashboard'));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
  const weekTotal = data?.counts.applications_week ?? 0;

  return (
    <div className={classes.page}>
      <PageHero art="rings" beside={290}>
        <div className={classes.top}>
          <div>
            <h1 className={classes.title}>
              {greeting(new Date().getHours())}
              {name && `, ${name}`}
            </h1>
            <p className={classes.date}>{today}</p>
          </div>
          <CreateJobButton />
        </div>
      </PageHero>

      {failed && !data && (
        <ErrorBanner title="We couldn’t load your overview." onRetry={load}>
          Check your connection and try again.
        </ErrorBanner>
      )}
      {!data && !failed && <Skeleton widths={[90, 70, 80, 60]} />}

      {data && (
        <>
          <div className={classes.stats}>
            {CARDS.map((card) => (
              <StatCard key={card.key} {...card} value={data.counts[card.key]} />
            ))}
          </div>

          <div className={classes.columns}>
            <section className={classes.card} aria-labelledby="needs-you">
              <h2 id="needs-you" className={classes.cardTitle}>
                Needs you
                {data.next_steps.length > 0 && <span className={classes.count}>{data.next_steps.length}</span>}
              </h2>
              <NextSteps steps={data.next_steps} />
            </section>

            <div className={classes.side}>
              <section className={classes.card} aria-labelledby="next-interviews">
                <h2 id="next-interviews" className={classes.cardTitle}>
                  Next interviews
                  <Link to="/interviews" className={classes.more}>
                    All interviews
                  </Link>
                </h2>
                <Upcoming interviews={data.upcoming} />
              </section>

              <section className={classes.card} aria-labelledby="applications">
                <h2 id="applications" className={classes.cardTitle}>
                  Applications, last 14 days
                  <span className={classes.more}>{plural(weekTotal, 'application')} this week</span>
                </h2>
                <BarChart
                  h={170}
                  data={chartDays(data.applications)}
                  dataKey="day"
                  series={[{ name: 'Applications', color: 'harbor.6' }]}
                  tickLine="none"
                  gridAxis="x"
                  barProps={{ radius: [4, 4, 0, 0] }}
                  xAxisProps={{ interval: 'preserveStartEnd', minTickGap: 12 }}
                  yAxisProps={{ allowDecimals: false, width: 28 }}
                  withTooltip
                  aria-label="Applications per day for the last 14 days"
                />
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
