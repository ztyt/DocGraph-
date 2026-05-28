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
