import { useEffect, useState } from "react";
import { PageState } from "./PageState";

type PlaceholderStatus = "loading" | "empty" | "error" | "success";

interface PlaceholderPageProps {
  eyebrow: string;
  title: string;
  successTitle: string;
  successBody: string;
  emptyTitle: string;
  emptyBody: string;
}

export function PlaceholderPage({
  eyebrow,
  title,
  successTitle,
  successBody,
  emptyTitle,
  emptyBody,
}: PlaceholderPageProps) {
  const [status, setStatus] = useState<PlaceholderStatus>("loading");

  useEffect(() => {
    const timer = window.setTimeout(() => setStatus("success"), 120);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <PageLayout eyebrow={eyebrow} title={title}>
      <PlaceholderState
        status={status}
        successTitle={successTitle}
        successBody={successBody}
        emptyTitle={emptyTitle}
        emptyBody={emptyBody}
      />
    </PageLayout>
  );
}

export function PageLayout({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="page-stack">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2 className="page-title">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function PlaceholderState({
  status,
  successTitle,
  successBody,
  emptyTitle,
  emptyBody,
}: {
  status: PlaceholderStatus;
  successTitle: string;
  successBody: string;
  emptyTitle: string;
  emptyBody: string;
}) {
  if (status === "loading") {
    return <PageState tone="loading" title="Loading" body="Preparing page state." />;
  }

  if (status === "empty") {
    return <PageState tone="empty" title={emptyTitle} body={emptyBody} />;
  }

  if (status === "error") {
    return <PageState tone="error" title="Page unavailable" body="The page state failed to load." />;
  }

  return <PageState tone="success" title={successTitle} body={successBody} />;
}

