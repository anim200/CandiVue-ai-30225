// Wraps interviewer pages: anyone who is not a signed-in interviewer goes to
// the login page. This is only for a smooth UI; the backend enforces the
// role on every request (N9).

import { Navigate, useLocation } from 'react-router';

import { loadSession } from './session';

export default function RequireInterviewer({ children }) {
  const location = useLocation();

  if (loadSession()?.user.role !== 'interviewer') {
    // Remember the page, so the user returns to it after signing in.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
