import { createBrowserRouter, Navigate } from "react-router-dom";

import { ProtectedLayout, PublicOnlyRoute } from "./components/layout/route-guards";
import { BacktestsPage } from "./pages/backtests-page";
import { DashboardPage } from "./pages/dashboard-page";
import { LoginPage } from "./pages/login-page";
import { SettingsPage } from "./pages/settings-page";

export const router = createBrowserRouter([
  {
    element: <PublicOnlyRoute />,
    children: [{ path: "/login", element: <LoginPage /> }],
  },
  {
    element: <ProtectedLayout />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/backtests", element: <BacktestsPage /> },
      { path: "/settings", element: <SettingsPage /> },
      // Redirect old routes to dashboard so bookmarks don't 404
      { path: "/market-data", element: <Navigate to="/" replace /> },
      { path: "/paper-trading", element: <Navigate to="/" replace /> },
      { path: "/agents", element: <Navigate to="/settings" replace /> },
    ],
  },
]);
