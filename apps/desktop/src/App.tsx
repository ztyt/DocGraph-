import { Outlet } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ErrorBoundary } from "./components/system/ErrorBoundary";

export function App() {
  return (
    <AppShell>
      <ErrorBoundary>
        <Outlet />
      </ErrorBoundary>
    </AppShell>
  );
}

