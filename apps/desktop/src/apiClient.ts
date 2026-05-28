import type {
  ApiEnvelope,
  FeatureFlagsData,
  FeatureFlagsPatch,
  HealthData,
  SettingsData,
  SettingsPatch,
  SystemInfoData,
} from "@docgraph/shared";

const SIDECAR_BASE_URL = "http://127.0.0.1:8765";

async function request<TData>(
  path: string,
  options: { method?: "GET" | "PUT"; body?: unknown } = {},
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
