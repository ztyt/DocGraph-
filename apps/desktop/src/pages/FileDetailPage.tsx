import type { ApiEnvelope, FileDetailChunk, FileDetailData } from "@docgraph/shared";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getFileDetail, openFile, revealFileInFolder, retryParseFile } from "../apiClient";
import { PageLayout } from "../components/system/PlaceholderPage";
import { PageState } from "../components/system/PageState";

type FileDetailViewState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "error"; message: string }
  | { status: "success"; envelope: ApiEnvelope<FileDetailData> & { data: FileDetailData } };

type ActionState = "idle" | "running" | "success" | "error";

interface FileActionState {
  status: ActionState;
  message: string;
}

const IDLE_ACTION: FileActionState = { status: "idle", message: "" };

export function FileDetailPage() {
  const { fileId } = useParams();
  const [state, setState] = useState<FileDetailViewState>({ status: "loading" });
  const [openState, setOpenState] = useState<FileActionState>(IDLE_ACTION);
  const [revealState, setRevealState] = useState<FileActionState>(IDLE_ACTION);
  const [retryState, setRetryState] = useState<FileActionState>(IDLE_ACTION);

  useEffect(() => {
    if (!fileId) {
      setState({ status: "empty" });
      return;
    }

    const selectedFileId = fileId;
    let isMounted = true;
    async function loadDetail() {
      setState({ status: "loading" });
      try {
        const envelope = await getFileDetail(selectedFileId);
        if (!isMounted) return;
        const data = envelope.data;
        if (!data) {
          setState({ status: "empty" });
          return;
        }
        setState({ status: "success", envelope: { ...envelope, data } });
      } catch (error) {
        if (!isMounted) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "File detail could not be loaded.",
        });
      }
    }

    void loadDetail();
    return () => {
      isMounted = false;
    };
  }, [fileId]);

  async function runAction(action: "open" | "reveal" | "retry") {
    if (!fileId) return;
    const setActionState =
      action === "open" ? setOpenState : action === "reveal" ? setRevealState : setRetryState;
    setActionState({ status: "running", message: "Starting" });
    try {
      if (action === "open") {
        await openFile(fileId);
      } else if (action === "reveal") {
        await revealFileInFolder(fileId);
      } else {
        await retryParseFile(fileId);
      }
      setActionState({ status: "success", message: action === "retry" ? "Queued" : "Started" });
    } catch (error) {
      setActionState({
        status: "error",
        message: error instanceof Error ? error.message : "Action failed",
      });
    }
  }

  return (
    <PageLayout eyebrow="File detail" title="File workspace">
      <FileDetailPanel
        state={state}
        openState={openState}
        revealState={revealState}
        retryState={retryState}
        onAction={runAction}
      />
    </PageLayout>
  );
}

function FileDetailPanel({
  state,
  openState,
  revealState,
  retryState,
  onAction,
}: {
  state: FileDetailViewState;
  openState: FileActionState;
  revealState: FileActionState;
  retryState: FileActionState;
  onAction: (action: "open" | "reveal" | "retry") => Promise<void>;
}) {
  if (state.status === "loading") {
    return <PageState tone="loading" title="Loading file" body="Reading local metadata." />;
  }

  if (state.status === "empty") {
    return <PageState tone="empty" title="No file selected" body="No file route is active." />;
  }

  if (state.status === "error") {
    return <PageState tone="error" title="File unavailable" body={state.message} />;
  }

  return (
    <section className="file-detail-workbench">
      <FileMetaPanel
        data={state.envelope.data}
        openState={openState}
        revealState={revealState}
        retryState={retryState}
        traceId={state.envelope.trace_id}
        onAction={onAction}
      />
      <ChunkPanel chunks={state.envelope.data.chunks} />
    </section>
  );
}

function FileMetaPanel({
  data,
  openState,
  revealState,
  retryState,
  traceId,
  onAction,
}: {
  data: FileDetailData;
  openState: FileActionState;
  revealState: FileActionState;
  retryState: FileActionState;
  traceId: string;
  onAction: (action: "open" | "reveal" | "retry") => Promise<void>;
}) {
  const { file } = data;
  return (
    <section className="file-detail-meta-panel">
      <div className="file-detail-header">
        <div>
          <p className="state-meta">FILE</p>
          <h2>{file.filename}</h2>
          <p>{file.path}</p>
        </div>
        <Link className="secondary-button" to="/files">
          Back
        </Link>
      </div>

      <div className="file-detail-actions">
        <button
          className="primary-button"
          type="button"
          disabled={openState.status === "running"}
          onClick={() => void onAction("open")}
        >
          Open
        </button>
        <button
          className="secondary-button"
          type="button"
          disabled={revealState.status === "running"}
          onClick={() => void onAction("reveal")}
        >
          Folder
        </button>
        <button
          className="secondary-button"
          type="button"
          disabled={retryState.status === "running"}
          onClick={() => void onAction("retry")}
        >
          Reparse
        </button>
      </div>
      <ActionMessages states={[openState, revealState, retryState]} />

      <dl className="meta-grid file-detail-meta-grid">
        <div>
          <dt>Status</dt>
          <dd>
            <span className={`file-status ${file.file_status}`}>{file.file_status}</span>
            <span className={`file-status ${file.parse_status}`}>{file.parse_status}</span>
          </dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{typeLabel(data)}</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>{formatSize(file.size_bytes)}</dd>
        </div>
        <div>
          <dt>Modified</dt>
          <dd>{formatDate(file.modified_time)}</dd>
        </div>
        <div>
          <dt>Chunks</dt>
          <dd>{data.chunk_count}</dd>
        </div>
        <div>
          <dt>Trace</dt>
          <dd>{traceId}</dd>
        </div>
      </dl>
    </section>
  );
}

function ChunkPanel({ chunks }: { chunks: FileDetailChunk[] }) {
  if (chunks.length === 0) {
    return <PageState tone="empty" title="No chunks" body="This file has no parsed chunks yet." />;
  }

  return (
    <section className="file-chunk-panel">
      <div className="file-chunk-header">
        <p className="state-meta">CHUNKS</p>
        <h2>{chunks.length} parsed chunks</h2>
      </div>
      <div className="file-chunk-list">
        {chunks.map((chunk) => (
          <article className="file-chunk-card" key={chunk.chunk_id}>
            <div className="file-chunk-title">
              <h3>{chunk.heading ?? chunk.chunk_type ?? "Chunk"}</h3>
              <span>#{chunk.chunk_index}</span>
            </div>
            <p>{chunk.text}</p>
            <dl className="file-chunk-meta">
              <div>
                <dt>Type</dt>
                <dd>{chunk.chunk_type ?? "unknown"}</dd>
              </div>
              <div>
                <dt>Page</dt>
                <dd>{chunk.page_no ?? "none"}</dd>
              </div>
              <div>
                <dt>Sheet</dt>
                <dd>{chunk.sheet_name ?? "none"}</dd>
              </div>
              <div>
                <dt>Slide</dt>
                <dd>{chunk.slide_no ?? "none"}</dd>
              </div>
              <div>
                <dt>Tokens</dt>
                <dd>{chunk.token_count ?? "unknown"}</dd>
              </div>
              <div>
                <dt>Section</dt>
                <dd>{chunk.section_path ?? "none"}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}

function ActionMessages({ states }: { states: FileActionState[] }) {
  const visibleStates = states.filter((state) => state.status !== "idle");
  if (visibleStates.length === 0) return null;
  return (
    <div className="file-detail-action-messages">
      {visibleStates.map((state, index) => (
        <p className={`file-action-message ${state.status}`} key={`${state.status}-${index}`}>
          {state.message}
        </p>
      ))}
    </div>
  );
}

function typeLabel(data: FileDetailData) {
  const extension = data.file.extension ? data.file.extension.replace(/^\./, "") : "unknown";
  return data.file.source_type ? `${data.file.source_type} / ${extension}` : extension;
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
