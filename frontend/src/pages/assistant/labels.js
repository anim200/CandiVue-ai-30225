// Words shown for backend values, in one place so every screen says the same.

// Where a job is, as a line under its name in the thread list.
// attention: needs the interviewer (shown in amber with an eye icon).
export const STAGES = {
  drafting_profile: { text: 'Drafting profile' },
  profile_saved: { text: 'Profile saved' },
  jd_to_approve: { text: 'Job description to approve', attention: true },
  jd_rejected: { text: 'Writing a new version' },
  jd_approved: { text: 'Approved · not posted' },
  post_to_confirm: { text: 'Post to job board?', attention: true },
  posted: { text: 'Posted · collecting CVs' },
  posting_failed: { text: 'Posting failed', attention: true },
};

// Short names of the four scoring dimensions, e.g. "Skills 40 · Experience 30".
export const DIMENSION_NAMES = [
  ['skills', 'Skills'],
  ['experience', 'Experience'],
  ['qualifications', 'Qualifications'],
  ['ats', 'ATS match'],
];

// Requirement levels, in the order the profile card lists them.
export const LEVELS = [
  ['mandatory', 'Mandatory'],
  ['required', 'Required'],
  ['preferred', 'Preferred'],
];

// Short names of knowledge-base collections, used in source chips.
export const COLLECTION_SHORT = {
  reference_library: 'Reference',
  company_policies: 'Company policy',
  previous_job_profiles: 'Previous profile',
  email_templates: 'Email template',
  question_bank: 'Question bank',
};

// "Company policy · Hybrid work" from a JD source (file name without extension).
export function sourceLabel(source) {
  const name = source.filename.replace(/\.[^.]+$/, '');
  return `${COLLECTION_SHORT[source.collection] ?? 'Document'} · ${name}`;
}

// What happened in the interviewer's Google Calendar ("added", "moved",
// "removed"); anything else is the reason it failed.
export const CALENDAR_DONE = {
  added: 'Added to your calendar',
  moved: 'Moved in your calendar',
  removed: 'Removed from your calendar',
};

// "Calendar not updated: <reason>" when it failed, null when all went well.
export function calendarProblem(calendar) {
  return calendar && !CALENDAR_DONE[calendar] ? `Calendar not updated: ${calendar}` : null;
}
