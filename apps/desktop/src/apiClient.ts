import type { ApiEnvelope, HealthData, SystemInfoData } from "@docgraph/shared";

const SIDECAR_BASE_URL = "http://127.0.0.1:8765";

async function request<TData>(path: string): Promise<ApiEnvelope<TData>> {
  const traceId = `web-${crypto.randomUUID()}`;
  const response = await fetch(`${SIDECAR_BASE_URL}${path}`, {
    headers: {
      "x-trace-id": traceId,
    },
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

