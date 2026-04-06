import { Navigate, Outlet } from "react-router-dom";

import { useSession } from "../../hooks/use-session";
import { AppShell } from "./app-shell";

export function ProtectedLayout() {
  const sessionQuery = useSession();

  if (sessionQuery.isLoading) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-100">Loading session...</div>;
  }

  if (!sessionQuery.data?.isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <AppShell />;
}

export function PublicOnlyRoute() {
  const sessionQuery = useSession();

  if (sessionQuery.isLoading) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-100">Loading session...</div>;
  }

  if (sessionQuery.data?.isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
