import type { ApiEnvelope, HealthData, SystemInfoData } from "@docgraph/shared";
import { useEffect, useState } from "react";
import { getHealth, getSystemInfo } from "../apiClient";
import { PageLayout } from "../components/system/PlaceholderPage";
import { PageState } from "../components/system/PageState";

type HealthState =
  | { status: "loading" }
  | { status: "empty" }
  | {
      status: "success";
      health: ApiEnvelope<HealthData> & { data: HealthData };
      system: ApiEnvelope<SystemInfoData> & { data: SystemInfoData };
    }
  | { status: "error"; message: string };

export function HomePage() {
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
    <PageLayout eyebrow="Home" title="Local sidecar status">
      <HealthPanel state={healthState} />
    </PageLayout>
  );
}

function HealthPanel({ state }: { state: HealthState }) {
  if (state.status === "loading") {
    return (
      <PageState
        tone="loading"
        title="Checking sidecar"
        body="Waiting for the local service health response."
      />
    );
  }

  if (state.status === "empty") {
    return (
      <PageState
        tone="empty"
        title="No health data yet"
        body="The sidecar responded, but no health payload was returned."
      />
    );
  }

  if (state.status === "error") {
    return (
      <PageState
        tone="error"
        title="Sidecar offline"
        body={state.message}
        meta="PORT 8765"
      />
    );
  }

  const health = state.health.data;
  const system = state.system.data;

  return (
    <section className="state-panel success health-panel">
      <span className="status-dot success" />
      <div>
        <p className="state-meta">HEALTH OK</p>
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
    </section>
  );
}

function FeatureFlag({ label, enabled }: { label: string; enabled: boolean }) {
  return <li className={enabled ? "enabled" : "disabled"}>{label}</li>;
}

