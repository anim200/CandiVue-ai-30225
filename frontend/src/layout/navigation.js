// The items in the left menu, in order, with the section (group) each one is
// shown under. Paths are used by the router too.

import {
  IconBooks,
  IconBriefcase,
  IconFileText,
  IconLayoutDashboard,
  IconVideo,
} from '@tabler/icons-react';

import AssistantMark from '../components/AssistantMark';

export const NAV_ITEMS = [
  {
    path: '/',
    label: 'Home',
    icon: IconLayoutDashboard,
    description: 'What needs you now: interviews, reports to review and CVs to screen.',
    group: 'Workspace',
  },
  {
    path: '/jobs',
    label: 'Jobs',
    icon: IconBriefcase,
    description: 'Job profiles, CV screening and candidate ranking will appear here.',
    group: 'Workspace',
  },
  {
    path: '/interviews',
    label: 'Interviews',
    icon: IconVideo,
    description: 'Upcoming and past interviews will appear here.',
    group: 'Workspace',
  },
  {
    path: '/reports',
    label: 'Reports',
    icon: IconFileText,
    description: 'Assessment reports waiting for your review will appear here.',
    group: 'Workspace',
  },
  {
    path: '/assistant',
    label: 'Hiring Assistant',
    icon: AssistantMark,
    description: 'Chat with the Hiring Assistant to create jobs and schedule interviews.',
    group: 'AI tools',
  },
  {
    path: '/knowledge-base',
    label: 'Knowledge base',
    icon: IconBooks,
    description: 'Documents the Hiring Assistant can search will appear here.',
    group: 'AI tools',
  },
];
