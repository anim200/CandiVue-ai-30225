// Which page is shown for which address.

import { createBrowserRouter, Navigate } from 'react-router';

import AppLayout from './layout/AppLayout';
import { NAV_ITEMS } from './layout/navigation';
import ComingSoonPage from './pages/ComingSoonPage';
import ErrorPage from './pages/ErrorPage';
import NotFoundPage from './pages/NotFoundPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    // Shown instead of a crashed page; never shows technical details (N12).
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
