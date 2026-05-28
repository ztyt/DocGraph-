import { useParams } from "react-router-dom";
import { PageLayout } from "../components/system/PlaceholderPage";
import { PageState } from "../components/system/PageState";

export function FileDetailPage() {
  const { fileId } = useParams();

  return (
    <PageLayout eyebrow="File detail" title="File workspace">
      <PageState
        tone={fileId ? "success" : "empty"}
        title={fileId ? "File detail route ready" : "No file selected"}
        body={
          fileId
            ? `Route parameter received: ${fileId}. Metadata, chunks, profile, and related files arrive in later milestones.`
            : "Open a file result to populate this page."
        }
      />
    </PageLayout>
  );
}

