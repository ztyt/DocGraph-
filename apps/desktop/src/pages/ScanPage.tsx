import type { ApiEnvelope, ScanJobData } from "@docgraph/shared";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { createScanJob, getScanJob, pauseScanJob, resumeScanJob } from "../apiClient";
import { PageLayout } from "../components/system/PlaceholderPage";
import { PageState } from "../components/system/PageState";

type ScanViewState =
  | { status: "loading"; message: string }
  | { status: "empty" }
  | { status: "error"; message: string; failures: ScanFailure[] }
  | {
      status: "success";
      envelope: ApiEnvelope<ScanJobData> & { data: ScanJobData };
      failures: ScanFailure[];
    };

interface ScanFailure {
  path: string;
  message: string;
}

const LAST_SCAN_JOB_KEY = "docgraph:last-scan-job";
const DEFAULT_EXCLUDE_RULES = [
  "node_modules",
  ".git",
  ".docgraph",
  "dist",
  "build",
  "*.tmp",
  "~$*",
].join("\n");

export function ScanPage() {
  const [rootPath, setRootPath] = useState("");
  const [excludeRules, setExcludeRules] = useState(DEFAULT_EXCLUDE_RULES);
  const [computeHash, setComputeHash] = useState(false);
  const [viewState, setViewState] = useState<ScanViewState>({
    status: "loading",
    message: "Checking the latest scan job.",
  });
  const currentJob =
    viewState.status === "success" ? viewState.envelope.data : null;

  useEffect(() => {
    let isMounted = true;
    const urlJobId = new URLSearchParams(window.location.search).get("job");
    const lastJobId = urlJobId || window.localStorage.getItem(LAST_SCAN_JOB_KEY);
    if (!lastJobId) {
      setViewState({ status: "empty" });
      return;
    }
    const jobId = lastJobId;
    window.localStorage.setItem(LAST_SCAN_JOB_KEY, jobId);

    async function loadLastJob() {
      try {
        const envelope = await getScanJob(jobId);
        if (!isMounted) return;
        const data = envelope.data;
        if (!data) {
          setViewState({ status: "empty" });
          return;
        }
        setRootPath(data.root_path);
        setComputeHash(data.compute_hash);
        setViewState({ status: "success", envelope: { ...envelope, data }, failures: [] });
      } catch (error) {
        if (!isMounted) return;
        window.localStorage.removeItem(LAST_SCAN_JOB_KEY);
        if (urlJobId) {
          setViewState({
            status: "error",
            message: error instanceof Error ? error.message : "Scan job could not be loaded.",
            failures: [{ path: jobId, message: "Scan job lookup failed." }],
          });
          return;
        }
        setViewState({ status: "empty" });
      }
    }

    void loadLastJob();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!currentJob || !["queued", "running"].includes(currentJob.job_status)) return;

    const timer = window.setInterval(async () => {
      try {
        const envelope = await getScanJob(currentJob.job_id);
        const data = envelope.data;
        if (!data) return;
        setViewState((state) => {
          const failures = state.status === "success" || state.status === "error" ? state.failures : [];
          return { status: "success", envelope: { ...envelope, data }, failures };
        });
      } catch (error) {
        setViewState({
          status: "error",
          message: error instanceof Error ? error.message : "Failed to refresh scan status.",
          failures: [
            {
              path: currentJob.root_path,
              message: error instanceof Error ? error.message : "Status refresh failed.",
            },
          ],
        });
      }
    }, 2500);

    return () => window.clearInterval(timer);
  }, [currentJob]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedPath = rootPath.trim();
    if (!trimmedPath) {
      setViewState({
        status: "error",
        message: "Folder path is required.",
        failures: [{ path: "Scan form", message: "Enter a folder path before starting." }],
      });
      return;
    }

    setViewState({ status: "loading", message: "Creating scan job." });
    try {
      const envelope = await createScanJob({
        root_path: trimmedPath,
        compute_hash: computeHash,
      });
      const data = envelope.data;
      if (!data) {
        setViewState({ status: "empty" });
        return;
      }
      window.localStorage.setItem(LAST_SCAN_JOB_KEY, data.job_id);
      setViewState({ status: "success", envelope: { ...envelope, data }, failures: [] });
    } catch (error) {
      setViewState({
        status: "error",
        message: error instanceof Error ? error.message : "Failed to create scan job.",
        failures: [
          {
            path: trimmedPath,
            message: error instanceof Error ? error.message : "Scan job creation failed.",
          },
        ],
      });
    }
  }

  async function handlePause() {
    if (!currentJob) return;
    await runJobAction(() => pauseScanJob(currentJob.job_id), currentJob.root_path);
  }

  async function handleResume() {
    if (!currentJob) return;
    await runJobAction(() => resumeScanJob(currentJob.job_id), currentJob.root_path);
  }

  async function runJobAction(
    action: () => Promise<ApiEnvelope<ScanJobData>>,
    fallbackPath: string,
  ) {
    setViewState({ status: "loading", message: "Updating scan job." });
    try {
      const envelope = await action();
      const data = envelope.data;
      if (!data) {
        setViewState({ status: "empty" });
        return;
      }
      setViewState((state) => {
        const failures = state.status === "success" || state.status === "error" ? state.failures : [];
        return { status: "success", envelope: { ...envelope, data }, failures };
      });
    } catch (error) {
      setViewState({
        status: "error",
        message: error instanceof Error ? error.message : "Failed to update scan job.",
        failures: [
          {
            path: fallbackPath,
            message: error instanceof Error ? error.message : "Scan job update failed.",
          },
        ],
      });
    }
  }

  return (
    <PageLayout eyebrow="Scan" title="Scan center">
      <form className="scan-workbench" onSubmit={handleSubmit}>
        <section className="scan-controls" aria-label="Scan controls">
          <label className="field">
            Folder path
            <input
              value={rootPath}
              onChange={(event) => setRootPath(event.target.value)}
              placeholder="C:\\Users\\Alenw\\Documents"
              autoComplete="off"
            />
          </label>
          <label className="field">
            Exclude rules
            <textarea
              value={excludeRules}
              onChange={(event) => setExcludeRules(event.target.value)}
              rows={7}
              spellCheck={false}
            />
          </label>
          <label className="toggle-row scan-toggle">
            Compute SHA-256
            <input
              type="checkbox"
              checked={computeHash}
              onChange={(event) => setComputeHash(event.target.checked)}
            />
          </label>
          <div className="scan-actions">
            <button
              className="primary-button"
              type="submit"
              disabled={viewState.status === "loading"}
            >
              Start scan
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={!currentJob || currentJob.job_status === "paused"}
              onClick={handlePause}
            >
              Pause
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={!currentJob || currentJob.job_status !== "paused"}
              onClick={handleResume}
            >
              Continue
            </button>
          </div>
        </section>

        <ScanStatusPanel state={viewState} ruleCount={activeRuleCount(excludeRules)} />
      </form>
    </PageLayout>
  );
}

function ScanStatusPanel({
  state,
  ruleCount,
}: {
  state: ScanViewState;
  ruleCount: number;
}) {
  if (state.status === "loading") {
    return <PageState tone="loading" title="Scan job loading" body={state.message} />;
  }

  if (state.status === "empty") {
    return (
      <PageState
        tone="empty"
        title="No scan job"
        body="Start a folder scan to see queue status, progress counters, and failures."
      />
    );
  }

  if (state.status === "error") {
    return (
      <section className="scan-status-stack">
        <PageState tone="error" title="Scan job error" body={state.message} />
        <FailureList failures={state.failures} />
      </section>
    );
  }

  return (
    <section className="scan-status-stack">
      <ScanProgress job={state.envelope.data} traceId={state.envelope.trace_id} ruleCount={ruleCount} />
      <FailureList failures={state.failures} errorMessage={state.envelope.data.error_message} />
    </section>
  );
}

function ScanProgress({
  job,
  traceId,
  ruleCount,
}: {
  job: ScanJobData;
  traceId: string;
  ruleCount: number;
}) {
  const statusLabel = job.job_status.replace(/^\w/, (char) => char.toUpperCase());
  const progressLabel = `${job.scanned_count} scanned, ${job.failed_count} failed`;

  return (
    <section className={`state-panel success scan-progress ${job.job_status}`}>
      <span className={`status-dot ${job.job_status === "failed" ? "error" : "success"}`} />
      <div>
        <p className="state-meta">{statusLabel}</p>
        <h2>{progressLabel}</h2>
        <div
          className={`progress-track ${job.job_status}`}
          role="progressbar"
          aria-label="Scan progress"
          aria-valuetext={progressLabel}
        >
          <span />
        </div>
        <dl className="meta-grid scan-meta-grid">
          <div>
            <dt>Current file</dt>
            <dd>{job.current_directory ?? job.root_path}</dd>
          </div>
          <div>
            <dt>Root</dt>
            <dd>{job.root_path}</dd>
          </div>
          <div>
            <dt>Ignored</dt>
            <dd>{job.ignored_count}</dd>
          </div>
          <div>
            <dt>Exclude rules</dt>
            <dd>{ruleCount}</dd>
          </div>
          <div>
            <dt>Trace</dt>
            <dd>{traceId}</dd>
          </div>
          <div>
            <dt>Task</dt>
            <dd>{job.task_id}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function FailureList({
  failures,
  errorMessage,
}: {
  failures: ScanFailure[];
  errorMessage?: string | null;
}) {
  const visibleFailures = useMemo(() => {
    if (failures.length > 0) return failures;
    if (!errorMessage) return [];
    return [{ path: "Scan job", message: errorMessage }];
  }, [failures, errorMessage]);

  return (
    <section className="failure-panel" aria-label="Scan failures">
      <div className="failure-panel-header">
        <h2>Failures</h2>
        <span>{visibleFailures.length}</span>
      </div>
      {visibleFailures.length === 0 ? (
        <p>No failures reported.</p>
      ) : (
        <ul>
          {visibleFailures.map((failure) => (
            <li key={`${failure.path}-${failure.message}`}>
              <strong>{failure.path}</strong>
              <span>{failure.message}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function activeRuleCount(value: string) {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean).length;
}
