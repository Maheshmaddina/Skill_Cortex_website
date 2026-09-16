import { Navigate, Outlet, useLocation } from "react-router";

import { PageSpinner } from "../components/ui.jsx";
import { useAuth } from "./AuthContext.jsx";

export function homeFor(user) {
  return user?.role === "ADMIN" ? "/admin" : "/dashboard";
}

/** Only allow same-site relative paths as post-login redirects. */
export function safeNext(next) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

export default function RequireAuth({ role, children }) {
  const { user, status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <PageSpinner />;
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (role && user.role !== role) return <Navigate to={homeFor(user)} replace />;
  return children ?? <Outlet />;
}
