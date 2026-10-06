// Which page is shown for which address.

import { createBrowserRouter, Navigate } from 'react-router';

import RequireInterviewer from './auth/RequireInterviewer';
import AppLayout from './layout/AppLayout';
import { NAV_ITEMS } from './layout/navigation';
import CandidateJoinPage from './pages/CandidateJoinPage';
import ComingSoonPage from './pages/ComingSoonPage';
import ErrorPage from './pages/ErrorPage';
import LoginPage from './pages/LoginPage';
import NotFoundPage from './pages/NotFoundPage';

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
      { index: true, element: <Navigate to="/jobs" replace /> },
      // Each module replaces its "coming soon" page with the real screen.
      ...NAV_ITEMS.map((item) => ({
        path: item.path,
        element: <ComingSoonPage title={item.label} description={item.description} />,
      })),
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
