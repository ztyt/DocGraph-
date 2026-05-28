import { PlaceholderPage } from "../components/system/PlaceholderPage";

export function SearchPage() {
  return (
    <PlaceholderPage
      eyebrow="Search"
      title="Search center"
      successTitle="Search route ready"
      successBody="FTS results, filters, snippets, and file opening start after parsing and indexing."
      emptyTitle="No indexed content"
      emptyBody="Search will populate after documents are scanned and indexed."
    />
  );
}

