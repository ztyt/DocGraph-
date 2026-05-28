import type { ApiEnvelope, HealthData, SystemInfoData } from "@docgraph/shared";
import { useEffect, useState } from "react";
import { getHealth, getSystemInfo } from "./apiClient";

type HealthState =
  | { status: "loading" }
  | { status: "empty" }
  | {
      status: "success";
      health: ApiEnvelope<HealthData> & { data: HealthData };
      system: ApiEnvelope<SystemInfoData> & { data: SystemInfoData };
    }
  | { status: "error"; message: string };

export function App() {
  const [healthState, setHealthState] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    let isMounted = true;

    async function loadHealth() {
      try {
        const [health, system] = await Promise.all([getHealth(), getSystemInfo()]);
        if (!isMounted) return;

        if (!health.data || !system.data) {
          setHealthState({ status: "empty" });
          return;
        }

        setHealthState({
          status: "success",
          health: { ...health, data: health.data },
          system: { ...system, data: system.data },
        });
      } catch (error) {
        if (!isMounted) return;
        setHealthState({
          status: "error",
          message: error instanceof Error ? error.message : "Sidecar health check failed.",
        });
      }
    }

    void loadHealth();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="app-shell">
      <section className="workspace">
        <p className="eyebrow">DocGraph V4</p>
        <h1>Local sidecar status</h1>
        <HealthPanel state={healthState} />
      </section>
    </main>
  );
}

function HealthPanel({ state }: { state: HealthState }) {
  if (state.status === "loading") {
    return (
      <div className="status-panel">
        <span className="status-dot pending" />
        <div>
          <h2>Checking sidecar</h2>
          <p>Waiting for the local service health response.</p>
        </div>
      </div>
    );
  }

  if (state.status === "empty") {
    return (
      <div className="status-panel">
        <span className="status-dot pending" />
        <div>
          <h2>No health data yet</h2>
          <p>The sidecar responded, but no health payload was returned.</p>
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="status-panel error">
        <span className="status-dot offline" />
        <div>
          <h2>Sidecar offline</h2>
          <p>{state.message}</p>
          <p className="hint">Start the sidecar with Python on port 8765, then refresh.</p>
        </div>
      </div>
    );
  }

  const health = state.health.data;
  const system = state.system.data;

  return (
    <div className="status-panel success">
      <span className="status-dot online" />
      <div>
        <h2>Sidecar healthy</h2>
        <p>
          {health.service} {health.version} is running in {health.mode} mode.
        </p>
        <dl className="meta-grid">
          <div>
            <dt>Trace</dt>
            <dd>{state.health.trace_id}</dd>
          </div>
          <div>
            <dt>Elapsed</dt>
            <dd>{state.health.elapsed_ms} ms</dd>
          </div>
          <div>
            <dt>Python</dt>
            <dd>{system.python_version}</dd>
          </div>
          <div>
            <dt>Platform</dt>
            <dd>
              {system.platform} {system.platform_release} {system.machine}
            </dd>
          </div>
        </dl>
        <ul className="feature-list">
          <FeatureFlag label="LLM" enabled={health.features.llm} />
          <FeatureFlag label="OCR" enabled={health.features.ocr} />
          <FeatureFlag label="Vector" enabled={health.features.vector_search} />
          <FeatureFlag label="Watchdog" enabled={health.features.watchdog} />
        </ul>
      </div>
    </div>
  );
}

function FeatureFlag({ label, enabled }: { label: string; enabled: boolean }) {
  return <li className={enabled ? "enabled" : "disabled"}>{label}</li>;
}
