// Which page is shown for which address.

import { createBrowserRouter } from 'react-router';

import RequireInterviewer from './auth/RequireInterviewer';
import AppLayout from './layout/AppLayout';
import { NAV_ITEMS } from './layout/navigation';
import InterviewAnalysisPage from './pages/analysis/InterviewAnalysisPage';
import HiringAssistantPage from './pages/assistant/HiringAssistantPage';
import CandidateJoinPage from './pages/CandidateJoinPage';
import ComingSoonPage from './pages/ComingSoonPage';
import ErrorPage from './pages/ErrorPage';
import HomePage from './pages/home/HomePage';
import InterviewRoomPage from './pages/interview/InterviewRoomPage';
import InterviewsPage from './pages/InterviewsPage';
import JobPage from './pages/job/JobPage';
import JobsPage from './pages/JobsPage';
import KnowledgeBasePage from './pages/knowledge/KnowledgeBasePage';
import LoginPage from './pages/LoginPage';
import NotFoundPage from './pages/NotFoundPage';
import AssessmentReportPage from './pages/report/AssessmentReportPage';
import ReportsPage from './pages/report/ReportsPage';

// Screens that are built; other menu items still show "coming soon".
const BUILT_PAGES = {
  '/jobs': <JobsPage />,
  '/interviews': <InterviewsPage />,
  '/knowledge-base': <KnowledgeBasePage />,
  '/reports': <ReportsPage />,
};

// The Hiring Assistant and the interview room fill the whole area (no page
// padding); during an interview the menu is hidden: the left column shows
// the candidate's CV instead (user request, 13-10-2026).
const FULL_BLEED = { fullBleed: true };
const LIVE_ROOM = { fullBleed: true, immersive: true };

// errorElement: shown instead of a crashed page; never shows technical
// details (N12).
export const router = createBrowserRouter([
  // Open to everyone.
  { path: '/login', element: <LoginPage />, errorElement: <ErrorPage /> },
  // Candidates: the private link from the invitation email.
  { path: '/join/:linkToken', element: <CandidateJoinPage />, errorElement: <ErrorPage /> },
  // Interviewers only: everything else.
  {
    path: '/',
    element: (
      <RequireInterviewer>
        <AppLayout />
      </RequireInterviewer>
    ),
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'assistant', element: <HiringAssistantPage />, handle: FULL_BLEED },
      { path: 'assistant/:jobId', element: <HiringAssistantPage />, handle: FULL_BLEED },
      { path: 'jobs/:jobId', element: <JobPage /> },
      { path: 'interviews/:interviewId/room', element: <InterviewRoomPage />, handle: LIVE_ROOM },
      { path: 'interviews/:interviewId/analysis', element: <InterviewAnalysisPage /> },
      { path: 'interviews/:interviewId/report', element: <AssessmentReportPage /> },
      // Each module replaces its "coming soon" page with the real screen.
      ...NAV_ITEMS.filter((item) => !['/', '/assistant'].includes(item.path)).map((item) => ({
        path: item.path,
        element: BUILT_PAGES[item.path] ?? (
          <ComingSoonPage title={item.label} description={item.description} />
        ),
      })),
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
