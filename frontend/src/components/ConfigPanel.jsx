import { useState, useEffect } from "react";
import PromptsPanel from "./PromptsPanel";

const API_BASE = import.meta.env.VITE_API_URL || "";

const GROUP_META = {
  llm_planner: {
    label: "Model",
    fields: {
      provider: { label: "Provider", type: "select" },
      model: { label: "Model", type: "select" },
    },
  },
  llm_database: {
    label: "Model",
    fields: {
      provider: { label: "Provider", type: "select" },
      model: { label: "Model", type: "select" },
    },
  },
  llm_browser: {
    label: "Model",
    fields: {
      provider: { label: "Provider", type: "select" },
      model: { label: "Model", type: "select" },
    },
  },
  llm_chart: {
    label: "Model",
    fields: {
      provider: { label: "Provider", type: "select" },
      model: { label: "Model", type: "select" },
    },
  },
  llm_memory: {
    label: "Model",
    fields: {
      provider: { label: "Provider", type: "select" },
      model: { label: "Model", type: "select" },
    },
  },
  llm_report: {
    label: "Model",
    fields: {
      provider: { label: "Provider", type: "select" },
      model: { label: "Model", type: "select" },
    },
  },
  llm: {
    label: "Default LLM (Fallback)",
    fields: {
      default_provider: { label: "Provider", type: "select" },
      default_model: { label: "Model", type: "select" },
    },
  },
};

const AGENT_SECTIONS = [
  {
    key: "planner",
    title: "Planner Agent",
    llmGroup: "llm_planner",
    promptAgent: "planner",
    toggleKey: "planner",
    toggleEnabled: false,
  },
  {
    key: "database",
    title: "Database Agent",
    llmGroup: "llm_database",
    promptAgent: "database",
    toggleKey: "database",
    toggleEnabled: true,
  },
  {
    key: "browser",
    title: "Browser Agent",
    llmGroup: "llm_browser",
    promptAgent: "browser",
    toggleKey: "browser",
    toggleEnabled: true,
  },
  {
    key: "chart",
    title: "Chart Agent",
    llmGroup: "llm_chart",
    promptAgent: "chart",
    toggleKey: "chart",
    toggleEnabled: true,
  },
  {
    key: "memory",
    title: "Memory Agent",
    llmGroup: "llm_memory",
    promptAgent: "memory",
    toggleKey: "memory",
    toggleEnabled: true,
  },
  {
    key: "report",
    title: "Report Agent",
    llmGroup: "llm_report",
    promptAgent: "report",
    toggleKey: "report",
    toggleEnabled: true,
  },
];

export default function ConfigPanel() {
  const [configs, setConfigs] = useState({});
  const [llmOptions, setLlmOptions] = useState({ providers: [], models: {} });
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/v1/admin/configs`)
      .then((r) => r.json())
      .then((data) => setConfigs(data))
      .catch(() => setStatus("Failed to load configs"));
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/v1/admin/llm/options`)
      .then((r) => r.json())
      .then((data) =>
        setLlmOptions({
          providers: data.providers || [],
          models: data.models || {},
        })
      )
      .catch(() => {});
  }, []);

  const isLlmGroup = (group) => group.startsWith("llm");
  const getProviderKey = (group) =>
    group === "llm" ? "default_provider" : "provider";
  const getModelKey = (group) =>
    group === "llm" ? "default_model" : "model";

  const getFieldOptions = (group, field) => {
    if (!isLlmGroup(group)) return [];
    const providerKey = getProviderKey(group);
    const modelKey = getModelKey(group);
    if (field === providerKey) {
      return llmOptions.providers || [];
    }
    if (field === modelKey) {
      const provider =
        configs[group]?.[providerKey] || llmOptions.providers?.[0];
      return llmOptions.models?.[provider] || [];
    }
    return [];
  };

  useEffect(() => {
    if (!llmOptions.providers.length) return;
    const llmGroups = [
      "llm_planner",
      "llm_database",
      "llm_browser",
      "llm_chart",
      "llm_memory",
      "llm_report",
      "llm",
    ];
    setConfigs((prev) => {
      let changed = false;
      const next = { ...prev };
      llmGroups.forEach((group) => {
        const providerKey = getProviderKey(group);
        const modelKey = getModelKey(group);
        const currentGroup = next[group] ? { ...next[group] } : {};
        const provider =
          llmOptions.providers.includes(currentGroup[providerKey])
            ? currentGroup[providerKey]
            : llmOptions.providers[0];
        const modelOptions = llmOptions.models?.[provider] || [];
        const model =
          modelOptions.length > 0 && modelOptions.includes(currentGroup[modelKey])
            ? currentGroup[modelKey]
            : modelOptions[0] || currentGroup[modelKey] || "";
        if (provider && currentGroup[providerKey] !== provider) {
          currentGroup[providerKey] = provider;
          changed = true;
        }
        if (model && currentGroup[modelKey] !== model) {
          currentGroup[modelKey] = model;
          changed = true;
        }
        next[group] = currentGroup;
      });
      return changed ? next : prev;
    });
  }, [llmOptions]);

  const handleChange = (group, field, value) => {
    setConfigs((prev) => ({
      ...prev,
      [group]: (() => {
        const nextGroup = { ...prev[group], [field]: value };
        if (isLlmGroup(group) && field === getProviderKey(group)) {
          const modelKey = getModelKey(group);
          const options = llmOptions.models?.[value] || [];
          if (options.length > 0 && !options.includes(nextGroup[modelKey])) {
            nextGroup[modelKey] = options[0];
          }
        }
        return nextGroup;
      })(),
    }));
  };

  const isEnabledValue = (value) => {
    if (value === undefined || value === null || value === "") return true;
    const normalized = String(value).trim().toLowerCase();
    return !["0", "false", "no", "off", "disabled"].includes(normalized);
  };

  const handleAgentToggle = (key, checked) => {
    handleChange("agents", key, checked ? "true" : "false");
  };

  const handleSave = async () => {
    setSaving(true);
    setStatus("");
    try {
      const res = await fetch(`${API_BASE}/v1/admin/configs`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ configs }),
      });
      if (res.ok) setStatus("Saved");
      else setStatus("Save failed");
    } catch {
      setStatus("Save failed");
    }
    setSaving(false);
    setTimeout(() => setStatus(""), 2000);
  };

  return (
    <div className="config-panel">
      <div className="panel-header">
        <h2>Configuration</h2>
        <div className="panel-actions">
          {status && <span className="panel-status">{status}</span>}
          <button className="save-btn" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save All"}
          </button>
        </div>
      </div>

      <div className="config-sections">
        <section className="config-section">
          <div className="section-title">Agent Configuration</div>
          <div className="agent-grid">
            {AGENT_SECTIONS.map((agent) => {
              const meta = GROUP_META[agent.llmGroup];
              const isEnabled = isEnabledValue(configs.agents?.[agent.toggleKey]);
              return (
                <div key={agent.key} className="agent-card">
                  <div className="agent-card-header">
                    <h3>{agent.title}</h3>
                    {agent.toggleEnabled ? (
                      <label className="toggle-wrap">
                        <input
                          type="checkbox"
                          checked={isEnabled}
                          onChange={(e) => handleAgentToggle(agent.toggleKey, e.target.checked)}
                        />
                        <span className="toggle-pill" />
                      </label>
                    ) : (
                      <span className="toggle-fixed">Always on</span>
                    )}
                  </div>
                  <div className="agent-card-body">
                    {meta && (
                      <div className="agent-llm">
                        <div className="agent-llm-title">{meta.label}</div>
                        <div className="config-fields">
                          {Object.entries(meta.fields).map(([field, fieldMeta]) => (
                            <div key={field} className="config-field">
                              <label>{fieldMeta.label}</label>
                              {fieldMeta.type === "select" ? (
                                <select
                                  value={configs[agent.llmGroup]?.[field] ?? ""}
                                  onChange={(e) =>
                                    handleChange(agent.llmGroup, field, e.target.value)
                                  }
                                >
                                  {(() => {
                                    const options = getFieldOptions(agent.llmGroup, field);
                                    const current = configs[agent.llmGroup]?.[field] ?? "";
                                    const selectOptions =
                                      options.length > 0
                                        ? options
                                        : current
                                        ? [current]
                                        : [];
                                    if (selectOptions.length === 0) {
                                      return (
                                        <option value="" disabled>
                                          No options
                                        </option>
                                      );
                                    }
                                    return selectOptions.map((option) => (
                                      <option key={option} value={option}>
                                        {option}
                                      </option>
                                    ));
                                  })()}
                                </select>
                              ) : (
                                <input
                                  type={fieldMeta.type}
                                  value={configs[agent.llmGroup]?.[field] ?? ""}
                                  onChange={(e) =>
                                    handleChange(agent.llmGroup, field, e.target.value)
                                  }
                                />
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="agent-prompts">
                      <div className="agent-prompts-title">Prompts</div>
                      <PromptsPanel showTitle={false} agentFilter={agent.promptAgent} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="config-section">
          <div className="section-title">System Configuration</div>
          <div className="config-groups">
            <div className="config-group">
              <h3>{GROUP_META.llm.label}</h3>
              <div className="config-fields">
                {Object.entries(GROUP_META.llm.fields).map(([field, fieldMeta]) => (
                  <div key={field} className="config-field">
                    <label>{fieldMeta.label}</label>
                    {fieldMeta.type === "select" ? (
                      <select
                        value={configs.llm?.[field] ?? ""}
                        onChange={(e) => handleChange("llm", field, e.target.value)}
                      >
                        {(() => {
                          const options = getFieldOptions("llm", field);
                          const current = configs.llm?.[field] ?? "";
                          const selectOptions =
                            options.length > 0 ? options : current ? [current] : [];
                          if (selectOptions.length === 0) {
                            return (
                              <option value="" disabled>
                                No options
                              </option>
                            );
                          }
                          return selectOptions.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ));
                        })()}
                      </select>
                    ) : (
                      <input
                        type={fieldMeta.type}
                        value={configs.llm?.[field] ?? ""}
                        onChange={(e) => handleChange("llm", field, e.target.value)}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
