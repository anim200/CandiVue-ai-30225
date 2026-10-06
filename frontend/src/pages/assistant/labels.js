// Words shown for backend values, in one place so every screen says the same.

// Where a job is, as a line under its name in the thread list.
// attention: needs the interviewer (shown in amber with an eye icon).
export const STAGES = {
  drafting_profile: { text: 'Drafting profile' },
  profile_saved: { text: 'Profile saved' },
  jd_to_approve: { text: 'Job description to approve', attention: true },
  jd_rejected: { text: 'Writing a new version' },
  jd_approved: { text: 'Job description approved' },
};

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
