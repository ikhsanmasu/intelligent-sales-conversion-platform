import { useMemo, useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

export default function PromptsPanel({ showTitle = true, agentFilter = null }) {
  const [prompts, setPrompts] = useState([]);
  const [activeSlug, setActiveSlug] = useState(null);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/v1/admin/prompts`)
      .then((r) => r.json())
      .then((data) => {
        setPrompts(data);
      })
      .catch(() => setStatus("Failed to load prompts"));
  }, []);

  const filteredPrompts = useMemo(() => {
    if (!agentFilter) return prompts;
    return prompts.filter((prompt) => (prompt.agent || "other") === agentFilter);
  }, [agentFilter, prompts]);

  useEffect(() => {
    if (filteredPrompts.length === 0) {
      setActiveSlug(null);
      setEditContent("");
      return;
    }
    if (!activeSlug || !filteredPrompts.some((p) => p.slug === activeSlug)) {
      setActiveSlug(filteredPrompts[0].slug);
      setEditContent(filteredPrompts[0].content);
    }
  }, [filteredPrompts, activeSlug]);

  const activePrompt = filteredPrompts.find((p) => p.slug === activeSlug);

  const promptsByAgent = filteredPrompts.reduce((acc, prompt) => {
    const agent = prompt.agent || "other";
    if (!acc[agent]) {
      acc[agent] = [];
    }
    acc[agent].push(prompt);
    return acc;
  }, {});

  const formatAgentLabel = (agent) =>
    agent
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");

  const handleSelect = (slug) => {
    setActiveSlug(slug);
    const prompt = filteredPrompts.find((p) => p.slug === slug);
    setEditContent(prompt?.content ?? "");
    setStatus("");
  };

  const handleSave = async () => {
    if (!activeSlug) return;
    setSaving(true);
    setStatus("");
    try {
      const res = await fetch(`${API_BASE}/v1/admin/prompts/${activeSlug}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editContent }),
      });
      if (res.ok) {
        setPrompts((prev) =>
          prev.map((p) =>
            p.slug === activeSlug ? { ...p, content: editContent } : p
          )
        );
        setStatus("Saved");
      } else {
        setStatus("Save failed");
      }
    } catch {
      setStatus("Save failed");
    }
    setSaving(false);
    setTimeout(() => setStatus(""), 2000);
  };

  return (
    <div className="prompts-panel">
      <div className="prompts-list">
        {showTitle && <h3>Prompts</h3>}
        {agentFilter
          ? filteredPrompts.map((p) => (
              <div
                key={p.slug}
                className={`prompt-item ${p.slug === activeSlug ? "active" : ""}`}
                onClick={() => handleSelect(p.slug)}
              >
                <span className="prompt-item-name">{p.name}</span>
                <span className="prompt-item-agent">{p.slug}</span>
              </div>
            ))
          : Object.entries(promptsByAgent).map(([agent, items]) => (
              <div key={agent} className="prompt-group">
                <div className="prompt-group-title">{formatAgentLabel(agent)}</div>
                {items.map((p) => (
                  <div
                    key={p.slug}
                    className={`prompt-item ${p.slug === activeSlug ? "active" : ""}`}
                    onClick={() => handleSelect(p.slug)}
                  >
                    <span className="prompt-item-name">{p.name}</span>
                    <span className="prompt-item-agent">{p.slug}</span>
                  </div>
                ))}
              </div>
            ))}
      </div>

      <div className="prompts-editor">
        {activePrompt ? (
          <>
            <div className="editor-header">
              <div>
                <h2>{activePrompt.name}</h2>
                <p className="editor-desc">{activePrompt.description}</p>
                {activePrompt.variables && (
                  <p className="editor-vars">
                    Variables: {activePrompt.variables.split(",").map((v) => (
                      <code key={v}>{`{${v.trim()}}`}</code>
                    ))}
                  </p>
                )}
              </div>
              <div className="panel-actions">
                {status && <span className="panel-status">{status}</span>}
                <button
                  className="save-btn"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? "Saving..." : "Save"}
                </button>
              </div>
            </div>
            <textarea
              className="prompt-textarea"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
            />
          </>
        ) : (
          <div className="editor-empty">Select a prompt to edit</div>
        )}
      </div>
    </div>
  );
}
