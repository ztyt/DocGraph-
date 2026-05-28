import { PlaceholderPage } from "../components/system/PlaceholderPage";

export function SettingsPage() {
  return (
    <PlaceholderPage
      eyebrow="Settings"
      title="Settings"
      successTitle="Settings route ready"
      successBody="Privacy mode, feature flags, workers, and retrieval settings start in the next milestone."
      emptyTitle="No settings loaded"
      emptyBody="Settings persistence is not connected yet."
    />
  );
}

