import type { ApiEnvelope, SettingsData } from "@docgraph/shared";
import { useEffect, useMemo, useState } from "react";
import { getSettings, updateSettings } from "../apiClient";
import { PageLayout } from "../components/system/PlaceholderPage";
import { PageState } from "../components/system/PageState";

type SettingsState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "error"; message: string }
  | {
      status: "success";
      envelope: ApiEnvelope<SettingsData> & { data: SettingsData };
      draft: SettingsData;
      saving: boolean;
      savedAt: string | null;
    };

export function SettingsPage() {
  const [state, setState] = useState<SettingsState>({ status: "loading" });

  useEffect(() => {
    let isMounted = true;

    async function loadSettings() {
      try {
        const envelope = await getSettings();
        if (!isMounted) return;

        if (!envelope.data) {
          setState({ status: "empty" });
          return;
        }

        setState({
          status: "success",
          envelope: { ...envelope, data: envelope.data },
          draft: envelope.data,
          saving: false,
          savedAt: null,
        });
      } catch (error) {
        if (!isMounted) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Settings request failed.",
        });
      }
    }

    void loadSettings();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <PageLayout eyebrow="Settings" title="Settings and feature flags">
      <SettingsContent state={state} setState={setState} />
    </PageLayout>
  );
}

function SettingsContent({
  state,
  setState,
}: {
  state: SettingsState;
  setState: React.Dispatch<React.SetStateAction<SettingsState>>;
}) {
  if (state.status === "loading") {
    return <PageState tone="loading" title="Loading settings" body="Reading local settings.json." />;
  }

  if (state.status === "empty") {
    return (
      <PageState
        tone="empty"
        title="No settings found"
        body="The sidecar returned an empty settings payload."
      />
    );
  }

  if (state.status === "error") {
    return <PageState tone="error" title="Settings unavailable" body={state.message} />;
  }

  return <SettingsForm state={state} setState={setState} />;
}

function SettingsForm({
  state,
  setState,
}: {
  state: Extract<SettingsState, { status: "success" }>;
  setState: React.Dispatch<React.SetStateAction<SettingsState>>;
}) {
  const changed = useMemo(
    () => JSON.stringify(state.draft) !== JSON.stringify(state.envelope.data),
    [state.draft, state.envelope.data],
  );

  function patchDraft(patch: Partial<SettingsData>) {
    setState((current) => {
      if (current.status !== "success") return current;
      return { ...current, draft: { ...current.draft, ...patch }, savedAt: null };
    });
  }

  async function saveSettings() {
    setState((current) => {
      if (current.status !== "success") return current;
      return { ...current, saving: true };
    });

    try {
      const envelope = await updateSettings(state.draft);
      if (!envelope.data) {
        setState({ status: "empty" });
        return;
      }
      setState({
        status: "success",
        envelope: { ...envelope, data: envelope.data },
        draft: envelope.data,
        saving: false,
        savedAt: new Date().toLocaleTimeString(),
      });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof Error ? error.message : "Failed to save settings.",
      });
    }
  }

  return (
    <section className="settings-grid">
      <div className="settings-card">
        <h3>Privacy</h3>
        <label className="field">
          <span>Privacy mode</span>
          <select
            value={state.draft.privacy_mode}
            onChange={(event) =>
              patchDraft({ privacy_mode: event.target.value as SettingsData["privacy_mode"] })
            }
          >
            <option value="local">Local</option>
            <option value="half_cloud">Half cloud</option>
            <option value="cloud_enhanced">Cloud enhanced</option>
          </select>
        </label>
      </div>

      <div className="settings-card">
        <h3>Retrieval</h3>
        <label className="field">
          <span>Backend</span>
          <select
            value={state.draft.retrieval_backend}
            onChange={(event) =>
              patchDraft({
                retrieval_backend: event.target.value as SettingsData["retrieval_backend"],
              })
            }
          >
            <option value="fts">FTS</option>
            <option value="rrf">RRF</option>
            <option value="vector">Vector</option>
          </select>
        </label>
      </div>

      <div className="settings-card">
        <h3>Feature flags</h3>
        <Toggle
          label="LLM"
          checked={state.draft.llm_enabled}
          onChange={(value) => patchDraft({ llm_enabled: value })}
        />
        <Toggle
          label="OCR"
          checked={state.draft.ocr_enabled}
          onChange={(value) => patchDraft({ ocr_enabled: value })}
        />
        <Toggle
          label="Vector search"
          checked={state.draft.vector_search_enabled}
          onChange={(value) => patchDraft({ vector_search_enabled: value })}
        />
        <Toggle
          label="Watchdog"
          checked={state.draft.watchdog_enabled}
          onChange={(value) => patchDraft({ watchdog_enabled: value })}
        />
      </div>

      <div className="settings-card">
        <h3>Resource limits</h3>
        <label className="field">
          <span>Graph node cap</span>
          <input
            min={10}
            max={200}
            type="number"
            value={state.draft.graph_node_cap}
            onChange={(event) => patchDraft({ graph_node_cap: Number(event.target.value) })}
          />
        </label>
        <label className="field">
          <span>Parser workers</span>
          <input
            min={1}
            max={8}
            type="number"
            value={state.draft.max_workers_parse}
            onChange={(event) => patchDraft({ max_workers_parse: Number(event.target.value) })}
          />
        </label>
      </div>

      <div className="settings-actions">
        <button className="primary-button" disabled={!changed || state.saving} onClick={saveSettings}>
          {state.saving ? "Saving" : "Save"}
        </button>
        <p>
          Trace {state.envelope.trace_id}
          {state.savedAt ? `, saved at ${state.savedAt}` : ""}
        </p>
      </div>
    </section>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}
