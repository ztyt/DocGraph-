import type { ApiEnvelope, SearchData, SearchQuery, SearchResultItem } from "@docgraph/shared";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { openFile, revealFileInFolder, searchFiles } from "../apiClient";
import { PageLayout } from "../components/system/PlaceholderPage";
import { PageState } from "../components/system/PageState";

type SearchViewState =
  | { status: "empty"; reason: "idle" | "no-results" }
  | { status: "loading"; query: SearchQuery }
  | { status: "error"; message: string }
  | { status: "success"; envelope: ApiEnvelope<SearchData> & { data: SearchData } };

type FileActionStatus = "idle" | "running" | "success" | "error";

interface FileActionState {
  status: FileActionStatus;
  message: string;
}

const DEFAULT_SEARCH: SearchQuery = {
  q: "",
  type: "",
  source: "",
  modified_from: "",
  modified_to: "",
  limit: 20,
  offset: 0,
};

export function SearchPage() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [draft, setDraft] = useState<SearchQuery>(DEFAULT_SEARCH);
  const [query, setQuery] = useState<SearchQuery | null>(null);
  const [state, setState] = useState<SearchViewState>({ status: "empty", reason: "idle" });
  const [fileActions, setFileActions] = useState<Record<string, FileActionState>>({});

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }

    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  useEffect(() => {
    if (!query) return;
    let isMounted = true;

    async function loadSearchResults() {
      if (!query) return;
      setState({ status: "loading", query });
      try {
        const envelope = await searchFiles(query);
        if (!isMounted) return;
        const data = envelope.data;
        if (!data || data.items.length === 0) {
          setState({ status: "empty", reason: "no-results" });
          return;
        }
        setState({ status: "success", envelope: { ...envelope, data } });
      } catch (error) {
        if (!isMounted) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Search failed.",
        });
      }
    }

    void loadSearchResults();
    return () => {
      isMounted = false;
    };
  }, [query]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuery = { ...draft, q: draft.q.trim(), offset: 0 };
    setDraft(nextQuery);
    if (!nextQuery.q) {
      setState({ status: "empty", reason: "idle" });
      setQuery(null);
      return;
    }
    setQuery(nextQuery);
  }

  function handleReset() {
    setDraft(DEFAULT_SEARCH);
    setQuery(null);
    setState({ status: "empty", reason: "idle" });
    inputRef.current?.focus();
  }

  function goToPage(offset: number) {
    const baseQuery = query ?? draft;
    const nextQuery = { ...baseQuery, offset };
    setDraft(nextQuery);
    setQuery(nextQuery);
  }

  async function runFileAction(fileId: string, action: "open" | "reveal") {
    const key = fileActionKey(fileId, action);
    setFileActions((current) => ({
      ...current,
      [key]: { status: "running", message: "Starting" },
    }));
    try {
      const envelope = action === "open" ? await openFile(fileId) : await revealFileInFolder(fileId);
      const result = envelope.data;
      setFileActions((current) => ({
        ...current,
        [key]: {
          status: "success",
          message: result?.status === "started" ? "Started" : "Done",
        },
      }));
    } catch (error) {
      setFileActions((current) => ({
        ...current,
        [key]: {
          status: "error",
          message: error instanceof Error ? error.message : "Action failed",
        },
      }));
    }
  }

  return (
    <PageLayout eyebrow="Search" title="Search center">
      <section className="search-workbench">
        <form className="search-topbar" onSubmit={handleSubmit}>
          <label className="field search-query-field">
            Query
            <input
              ref={inputRef}
              value={draft.q}
              onChange={(event) => setDraft({ ...draft, q: event.target.value })}
              placeholder="alpha project budget"
              autoComplete="off"
            />
          </label>
          <button className="primary-button" type="submit" disabled={!draft.q.trim()}>
            Search
          </button>
        </form>

        <div className="search-main-grid">
          <aside className="search-filter-panel" aria-label="Search filters">
            <label className="field">
              Type
              <input
                value={draft.type ?? ""}
                onChange={(event) => setDraft({ ...draft, type: event.target.value })}
                placeholder="pdf, docx, xlsx"
              />
            </label>
            <label className="field">
              Source
              <select
                value={draft.source ?? ""}
                onChange={(event) => setDraft({ ...draft, source: event.target.value })}
              >
                <option value="">All</option>
                <option value="text">Text</option>
                <option value="office">Office</option>
                <option value="pdf">PDF</option>
                <option value="image">Image</option>
                <option value="archive">Archive</option>
                <option value="unknown">Unknown</option>
              </select>
            </label>
            <label className="field">
              Modified after
              <input
                type="date"
                value={dateInputValue(draft.modified_from)}
                onChange={(event) =>
                  setDraft({ ...draft, modified_from: dateStart(event.target.value) })
                }
              />
            </label>
            <label className="field">
              Modified before
              <input
                type="date"
                value={dateInputValue(draft.modified_to)}
                onChange={(event) => setDraft({ ...draft, modified_to: dateEnd(event.target.value) })}
              />
            </label>
            <div className="search-filter-actions">
              <button className="secondary-button" type="button" onClick={handleReset}>
                Reset
              </button>
            </div>
          </aside>

          <SearchResultPanel state={state} fileActions={fileActions} onFileAction={runFileAction} onPage={goToPage} />
        </div>
      </section>
    </PageLayout>
  );
}

function SearchResultPanel({
  state,
  fileActions,
  onFileAction,
  onPage,
}: {
  state: SearchViewState;
  fileActions: Record<string, FileActionState>;
  onFileAction: (fileId: string, action: "open" | "reveal") => Promise<void>;
  onPage: (offset: number) => void;
}) {
  if (state.status === "loading") {
    return <PageState tone="loading" title="Searching" body="Reading the local index." />;
  }

  if (state.status === "error") {
    return <PageState tone="error" title="Search unavailable" body={state.message} />;
  }

  if (state.status === "empty") {
    return (
      <PageState
        tone="empty"
        title={state.reason === "idle" ? "Ready to search" : "No matches"}
        body={
          state.reason === "idle"
            ? "Indexed chunks are ready."
            : "No indexed chunks matched the current query."
        }
      />
    );
  }

  return (
    <SearchResults
      data={state.envelope.data}
      fileActions={fileActions}
      traceId={state.envelope.trace_id}
      onFileAction={onFileAction}
      onPage={onPage}
    />
  );
}

function SearchResults({
  data,
  fileActions,
  traceId,
  onFileAction,
  onPage,
}: {
  data: SearchData;
  fileActions: Record<string, FileActionState>;
  traceId: string;
  onFileAction: (fileId: string, action: "open" | "reveal") => Promise<void>;
  onPage: (offset: number) => void;
}) {
  const nextOffset = data.filters.offset + data.filters.limit;
  const previousOffset = Math.max(0, data.filters.offset - data.filters.limit);
  const hasPrevious = data.filters.offset > 0;
  const hasNext = nextOffset < data.total;

  return (
    <section className="search-results-panel">
      <div className="search-results-header">
        <div>
          <p className="state-meta">RESULTS</p>
          <h2>{data.total} matching files</h2>
        </div>
        <span>{traceId}</span>
      </div>
      <div className="search-results-list">
        {data.items.map((item) => (
          <SearchResultCard
            key={item.file_id}
            item={item}
            openState={fileActions[fileActionKey(item.file_id, "open")]}
            revealState={fileActions[fileActionKey(item.file_id, "reveal")]}
            onFileAction={onFileAction}
          />
        ))}
      </div>
      <div className="search-pagination">
        <button
          className="secondary-button"
          type="button"
          disabled={!hasPrevious}
          onClick={() => onPage(previousOffset)}
        >
          Previous
        </button>
        <span>
          {data.filters.offset + 1}-{Math.min(nextOffset, data.total)} of {data.total}
        </span>
        <button
          className="secondary-button"
          type="button"
          disabled={!hasNext}
          onClick={() => onPage(nextOffset)}
        >
          Next
        </button>
      </div>
    </section>
  );
}

function SearchResultCard({
  item,
  openState,
  revealState,
  onFileAction,
}: {
  item: SearchResultItem;
  openState?: FileActionState;
  revealState?: FileActionState;
  onFileAction: (fileId: string, action: "open" | "reveal") => Promise<void>;
}) {
  return (
    <article className="search-result-card">
      <div className="search-result-title-row">
        <div>
          <h3>{item.filename}</h3>
          <p>{item.path}</p>
        </div>
        <div className="file-action-cluster">
          <button
            className="secondary-button search-open-button"
            type="button"
            disabled={openState?.status === "running"}
            onClick={() => void onFileAction(item.file_id, "open")}
          >
            Open
          </button>
          <button
            className="secondary-button search-open-button"
            type="button"
            disabled={revealState?.status === "running"}
            onClick={() => void onFileAction(item.file_id, "reveal")}
          >
            Folder
          </button>
        </div>
      </div>
      <FileActionMessage openState={openState} revealState={revealState} />
      <div className="search-result-snippet">{renderSnippet(item.snippet)}</div>
      <dl className="search-result-meta">
        <div>
          <dt>Type</dt>
          <dd>{typeLabel(item)}</dd>
        </div>
        <div>
          <dt>Modified</dt>
          <dd>{formatDate(item.modified_time)}</dd>
        </div>
        <div>
          <dt>BM25</dt>
          <dd>{item.bm25_score.toFixed(4)}</dd>
        </div>
      </dl>
      <div className="matched-chunk-list" aria-label="Matched chunks">
        {item.matched_chunks.map((chunk) => (
          <div className="matched-chunk" key={chunk.chunk_id}>
            <div>
              <strong>{chunk.heading ?? "Chunk"}</strong>
              <span>{chunk.chunk_id}</span>
            </div>
            <p>{renderSnippet(chunk.snippet)}</p>
          </div>
        ))}
      </div>
    </article>
  );
}

function FileActionMessage({
  openState,
  revealState,
}: {
  openState?: FileActionState;
  revealState?: FileActionState;
}) {
  const visibleState = revealState && revealState.status !== "idle" ? revealState : openState;
  if (!visibleState || visibleState.status === "idle") return null;
  return <p className={`file-action-message ${visibleState.status}`}>{visibleState.message}</p>;
}

function renderSnippet(value: string) {
  const parts = value.split(/(<mark>|<\/mark>)/);
  let highlighted = false;
  return parts.map((part, index) => {
    if (part === "<mark>") {
      highlighted = true;
      return null;
    }
    if (part === "</mark>") {
      highlighted = false;
      return null;
    }
    if (!part) return null;
    return highlighted ? <mark key={`${part}-${index}`}>{part}</mark> : <span key={`${part}-${index}`}>{part}</span>;
  });
}

function typeLabel(item: SearchResultItem) {
  const extension = item.extension ? item.extension.replace(/^\./, "") : "unknown";
  return item.source_type ? `${item.source_type} / ${extension}` : extension;
}

function formatDate(value: string | null) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function dateInputValue(value?: string) {
  if (!value) return "";
  return value.slice(0, 10);
}

function dateStart(value: string) {
  return value ? `${value}T00:00:00+00:00` : "";
}

function dateEnd(value: string) {
  return value ? `${value}T23:59:59+00:00` : "";
}

function fileActionKey(fileId: string, action: "open" | "reveal") {
  return `${fileId}:${action}`;
}
