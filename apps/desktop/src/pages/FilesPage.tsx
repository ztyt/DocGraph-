import type { ApiEnvelope, FileListData, FileListItem, FileListQuery } from "@docgraph/shared";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listFiles } from "../apiClient";
import { PageLayout } from "../components/system/PlaceholderPage";
import { PageState } from "../components/system/PageState";

type FilesViewState =
  | { status: "loading" }
  | { status: "empty"; query: FileListQuery }
  | { status: "error"; message: string }
  | { status: "success"; envelope: ApiEnvelope<FileListData> & { data: FileListData } };

const DEFAULT_QUERY: FileListQuery = {
  type: "",
  status: "",
  source: "",
  keyword: "",
  limit: 50,
  offset: 0,
};

export function FilesPage() {
  const [draft, setDraft] = useState<FileListQuery>(DEFAULT_QUERY);
  const [query, setQuery] = useState<FileListQuery>(DEFAULT_QUERY);
  const [state, setState] = useState<FilesViewState>({ status: "loading" });

  useEffect(() => {
    let isMounted = true;

    async function loadFiles() {
      setState({ status: "loading" });
      try {
        const envelope = await listFiles(query);
        if (!isMounted) return;
        const data = envelope.data;
        if (!data || data.items.length === 0) {
          setState({ status: "empty", query });
          return;
        }
        setState({ status: "success", envelope: { ...envelope, data } });
      } catch (error) {
        if (!isMounted) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Failed to load files.",
        });
      }
    }

    void loadFiles();
    return () => {
      isMounted = false;
    };
  }, [query]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery({ ...draft, offset: 0 });
  }

  function handleReset() {
    setDraft(DEFAULT_QUERY);
    setQuery(DEFAULT_QUERY);
  }

  return (
    <PageLayout eyebrow="Files" title="File list">
      <section className="files-workbench">
        <form className="files-filter-bar" onSubmit={handleSubmit}>
          <label className="field">
            Keyword
            <input
              value={draft.keyword ?? ""}
              onChange={(event) => setDraft({ ...draft, keyword: event.target.value })}
              placeholder="filename or path"
            />
          </label>
          <label className="field">
            Type
            <input
              value={draft.type ?? ""}
              onChange={(event) => setDraft({ ...draft, type: event.target.value })}
              placeholder="pdf, docx, md"
            />
          </label>
          <label className="field">
            Status
            <select
              value={draft.status ?? ""}
              onChange={(event) => setDraft({ ...draft, status: event.target.value })}
            >
              <option value="">All</option>
              <option value="discovered">Discovered</option>
              <option value="indexed">Indexed</option>
              <option value="failed">Failed</option>
            </select>
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
          <div className="files-filter-actions">
            <button className="primary-button" type="submit">
              Apply
            </button>
            <button className="secondary-button" type="button" onClick={handleReset}>
              Reset
            </button>
          </div>
        </form>

        <FilesResultPanel state={state} />
      </section>
    </PageLayout>
  );
}

function FilesResultPanel({ state }: { state: FilesViewState }) {
  if (state.status === "loading") {
    return <PageState tone="loading" title="Loading files" body="Reading local file metadata." />;
  }

  if (state.status === "empty") {
    return (
      <PageState
        tone="empty"
        title="No files found"
        body={
          hasActiveFilters(state.query)
            ? "No indexed files match the current filters."
            : "Run a scan to populate the local file index."
        }
      />
    );
  }

  if (state.status === "error") {
    return <PageState tone="error" title="Files unavailable" body={state.message} />;
  }

  return <FilesTable data={state.envelope.data} traceId={state.envelope.trace_id} />;
}

function FilesTable({ data, traceId }: { data: FileListData; traceId: string }) {
  return (
    <section className="files-table-panel">
      <div className="files-table-header">
        <div>
          <p className="state-meta">FILES</p>
          <h2>{data.total} indexed files</h2>
        </div>
        <span>{traceId}</span>
      </div>
      <div className="files-table-scroll">
        <table className="files-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Path</th>
              <th>Type</th>
              <th>Size</th>
              <th>Modified</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((file) => (
              <FileRow key={file.file_id} file={file} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FileRow({ file }: { file: FileListItem }) {
  return (
    <tr>
      <td>
        <Link to={`/files/${encodeURIComponent(file.file_id)}`}>{file.filename}</Link>
      </td>
      <td>{file.path}</td>
      <td>{typeLabel(file)}</td>
      <td>{formatSize(file.size_bytes)}</td>
      <td>{formatDate(file.modified_time)}</td>
      <td>
        <span className={`file-status ${file.file_status}`}>{file.file_status}</span>
      </td>
    </tr>
  );
}

function typeLabel(file: FileListItem) {
  const extension = file.extension ? file.extension.replace(/^\./, "") : "unknown";
  return file.source_type ? `${file.source_type} / ${extension}` : extension;
}

function formatSize(value: number | null) {
  if (value === null) return "Unknown";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string | null) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function hasActiveFilters(query: FileListQuery) {
  return Boolean(query.keyword || query.type || query.status || query.source);
}
