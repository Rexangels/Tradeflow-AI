import { createBrowserRouter } from "react-router-dom";

import { ProtectedLayout, PublicOnlyRoute } from "./components/layout/route-guards";
import { AgentsPage } from "./pages/agents-page";
import { BacktestsPage } from "./pages/backtests-page";
import { DashboardPage } from "./pages/dashboard-page";
import { LoginPage } from "./pages/login-page";
import { MarketDataPage } from "./pages/market-data-page";
import { PaperTradingPage } from "./pages/paper-trading-page";
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
      { path: "/agents", element: <AgentsPage /> },
      { path: "/backtests", element: <BacktestsPage /> },
      { path: "/market-data", element: <MarketDataPage /> },
      { path: "/paper-trading", element: <PaperTradingPage /> },
      { path: "/settings", element: <SettingsPage /> },
    ],
  },
]);
