import type {
  ApiEnvelope,
  CreateScanJobRequest,
  DatabaseStatusData,
  DocumentProfileData,
  FileActionData,
  FileEntitiesData,
  FileDetailData,
  FileListData,
  FileListQuery,
  FeatureFlagsData,
  FeatureFlagsPatch,
  HealthData,
  ParseRetryData,
  ScanJobData,
  SearchData,
  SearchQuery,
  SettingsData,
  SettingsPatch,
  SnapshotData,
  SystemInfoData,
} from "@docgraph/shared";

const SIDECAR_BASE_URL = "http://127.0.0.1:8765";

async function request<TData>(
  path: string,
  options: { method?: "GET" | "POST" | "PUT"; body?: unknown } = {},
): Promise<ApiEnvelope<TData>> {
  const traceId = `web-${crypto.randomUUID()}`;
  const response = await fetch(`${SIDECAR_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "content-type": "application/json",
      "x-trace-id": traceId,
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const payload = (await response.json()) as ApiEnvelope<TData>;

  if (!response.ok || !payload.ok) {
    throw new Error(payload.error?.message ?? `Request failed: ${path}`);
  }

  return payload;
}

export function getHealth() {
  return request<HealthData>("/api/health");
}

export function getSystemInfo() {
  return request<SystemInfoData>("/api/system/info");
}

export function getSettings() {
  return request<SettingsData>("/api/settings");
}

export function updateSettings(patch: SettingsPatch) {
  return request<SettingsData>("/api/settings", { method: "PUT", body: patch });
}

export function getFeatures() {
  return request<FeatureFlagsData>("/api/features");
}

export function updateFeatures(patch: FeatureFlagsPatch) {
  return request<FeatureFlagsData>("/api/features", { method: "PUT", body: patch });
}

export function getDatabaseStatus() {
  return request<DatabaseStatusData>("/api/db/status");
}

export function createDatabaseSnapshot() {
  return request<SnapshotData>("/api/db/snapshot", { method: "POST" });
}

export function restoreDatabaseSnapshot(snapshotId: string) {
  return request<SnapshotData>(`/api/db/restore/${encodeURIComponent(snapshotId)}`, {
    method: "POST",
  });
}

export function createScanJob(payload: CreateScanJobRequest) {
  return request<ScanJobData>("/api/scan/jobs", { method: "POST", body: payload });
}

export function getScanJob(jobId: string) {
  return request<ScanJobData>(`/api/scan/jobs/${encodeURIComponent(jobId)}`);
}

export function pauseScanJob(jobId: string) {
  return request<ScanJobData>(`/api/scan/jobs/${encodeURIComponent(jobId)}/pause`, {
    method: "POST",
  });
}

export function resumeScanJob(jobId: string) {
  return request<ScanJobData>(`/api/scan/jobs/${encodeURIComponent(jobId)}/resume`, {
    method: "POST",
  });
}

export function listFiles(query: FileListQuery = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<FileListData>(`/api/files${suffix}`);
}

export function getFileDetail(fileId: string) {
  return request<FileDetailData>(`/api/files/${encodeURIComponent(fileId)}`);
}

export function getFileProfile(fileId: string) {
  return request<DocumentProfileData>(`/api/files/${encodeURIComponent(fileId)}/profile`);
}

export function buildFileProfile(fileId: string) {
  return request<DocumentProfileData>(`/api/profile/build/${encodeURIComponent(fileId)}`, {
    method: "POST",
  });
}

export function getFileEntities(fileId: string) {
  return request<FileEntitiesData>(`/api/files/${encodeURIComponent(fileId)}/entities`);
}

export function openFile(fileId: string) {
  return request<FileActionData>(`/api/files/${encodeURIComponent(fileId)}/open`, {
    method: "POST",
  });
}

export function revealFileInFolder(fileId: string) {
  return request<FileActionData>(
    `/api/files/${encodeURIComponent(fileId)}/reveal-in-folder`,
    {
      method: "POST",
    },
  );
}

export function retryParseFile(fileId: string) {
  return request<ParseRetryData>(`/api/parse/retry/${encodeURIComponent(fileId)}`, {
    method: "POST",
  });
}

export function searchFiles(query: SearchQuery) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }

  return request<SearchData>(`/api/search?${params.toString()}`);
}
