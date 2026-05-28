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
