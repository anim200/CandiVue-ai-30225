// Wording for the home page (dashboard), kept apart from the page so it can
// be tested.

// "Good morning" / "Good afternoon" / "Good evening" for the local hour.
export function greeting(hour) {
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

// The first name of "Interviewer A" -> "Interviewer".
export function firstName(name) {
  return (name || '').trim().split(/\s+/)[0] || '';
}

// When an interview is: "Today, 10:30", "Tomorrow, 09:00" or "Fri 24 Oct, 10:00".
export function interviewTime(iso, now = new Date()) {
  const at = new Date(iso);
  const time = at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const day = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((day(at) - day(now)) / 86400000);
  if (days === 0) return `Today, ${time}`;
  if (days === 1) return `Tomorrow, ${time}`;
  const date = at.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
  return `${date}, ${time}`;
}

// The applications chart: one bar per day, labelled "Mon 20".
export function chartDays(days) {
  return days.map(({ day, count }) => {
    const [year, month, date] = day.split('-').map(Number);
    const label = new Date(year, month - 1, date).toLocaleDateString('en-GB', {
      weekday: 'short',
      day: 'numeric',
    });
    return { day: label, Applications: count };
  });
}

// "1 application" / "3 applications".
export function plural(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`;
}
