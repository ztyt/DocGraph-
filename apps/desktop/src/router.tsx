import { createBrowserRouter, Navigate } from "react-router-dom";
import { App } from "./App";
import { AuditPage } from "./pages/AuditPage";
import { FileDetailPage } from "./pages/FileDetailPage";
import { HomePage } from "./pages/HomePage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { ScanPage } from "./pages/ScanPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "onboarding", element: <OnboardingPage /> },
      { path: "scan", element: <ScanPage /> },
      { path: "search", element: <SearchPage /> },
      { path: "files/:fileId", element: <FileDetailPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "audit", element: <AuditPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

