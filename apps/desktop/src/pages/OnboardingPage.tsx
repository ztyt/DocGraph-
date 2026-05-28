import { PlaceholderPage } from "../components/system/PlaceholderPage";

export function OnboardingPage() {
  return (
    <PlaceholderPage
      eyebrow="Onboarding"
      title="Workspace start"
      successTitle="Onboarding route ready"
      successBody="The desktop shell can host the first-run flow when settings arrive."
      emptyTitle="No onboarding state"
      emptyBody="First-run configuration has not been stored yet."
    />
  );
}

