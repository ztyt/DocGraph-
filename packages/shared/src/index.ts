export const DOCGRAPH_VERSION = "0.0.0";

export interface ApiError {
  code: string;
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
}

export interface ApiEnvelope<TData> {
  ok: boolean;
  data: TData | null;
  error: ApiError | null;
  trace_id: string;
  elapsed_ms: number;
}

export interface HealthData {
  status: "ok";
  service: "docgraph-sidecar";
  version: string;
  mode: "local";
  features: {
    llm: boolean;
    ocr: boolean;
    vector_search: boolean;
    watchdog: boolean;
  };
}

export interface SystemInfoData {
  service: "docgraph-sidecar";
  version: string;
  python_version: string;
  platform: string;
  platform_release: string;
  machine: string;
}

export type PrivacyMode = "local" | "half_cloud" | "cloud_enhanced";
export type RetrievalBackend = "fts" | "rrf" | "vector";

export interface SettingsData {
  privacy_mode: PrivacyMode;
  llm_enabled: boolean;
  ocr_enabled: boolean;
  vector_search_enabled: boolean;
  watchdog_enabled: boolean;
  retrieval_backend: RetrievalBackend;
  graph_node_cap: number;
  max_workers_parse: number;
}

export type SettingsPatch = Partial<SettingsData>;

export interface FeatureFlagsData {
  llm: boolean;
  ocr: boolean;
  vector_search: boolean;
  watchdog: boolean;
}

export type FeatureFlagsPatch = Partial<FeatureFlagsData>;

export interface DatabaseStatusData {
  db_path: string;
  exists: boolean;
  schema_version: string | null;
  size_bytes: number;
  snapshot_count: number;
}

export interface FtsIndexData {
  file_id: string | null;
  indexed_chunk_count: number;
  indexed_file_count: number;
  rebuilt_at: string;
}

export interface SnapshotData {
  snapshot_id: string;
  snapshot_dir: string;
  db_path: string;
  settings_path: string | null;
  size_bytes: number;
  schema_version: string | null;
  status: "created" | "restored";
  created_at: string;
}

export type ScanJobStatus = "queued" | "running" | "paused" | "done" | "failed";

export interface ScanJobData {
  job_id: string;
  task_id: string;
  root_path: string;
  normalized_root_path: string;
  job_status: ScanJobStatus;
  current_directory: string | null;
  scanned_count: number;
  failed_count: number;
  ignored_count: number;
  compute_hash: boolean;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  paused_at: string | null;
}

export interface CreateScanJobRequest {
  root_path: string;
  compute_hash?: boolean;
  priority?: number;
}

export interface FileListItem {
  file_id: string;
  filename: string;
  path: string;
  extension: string | null;
  source_type: string | null;
  size_bytes: number | null;
  modified_time: string | null;
  file_status: string;
  parse_status: string;
}

export interface FileListFilters {
  type: string | null;
  status: string | null;
  source: string | null;
  keyword: string | null;
  limit: number;
  offset: number;
}

export interface FileListData {
  items: FileListItem[];
  total: number;
  filters: FileListFilters;
}

export interface FileListQuery {
  type?: string;
  status?: string;
  source?: string;
  keyword?: string;
  limit?: number;
  offset?: number;
}

export type TaskStatus = "queued" | "running" | "done" | "failed";

export interface TaskData {
  task_id: string;
  task_type: string;
  task_status: TaskStatus;
  priority: number;
  payload: Record<string, unknown>;
  retry_count: number;
  max_attempts: number;
  last_error_code: string | null;
  last_error_message: string | null;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ParseRetryData {
  file_id: string;
  task: TaskData;
}
