import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

const API_BASE = import.meta.env.VITE_API_URL || "";

const CHANNEL_OPTIONS = [
  { value: "all", label: "All channels" },
  { value: "web", label: "Web" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "telegram", label: "Telegram" },
];

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "ready_to_buy", label: "Ready to buy" },
  { value: "considering", label: "Considering" },
  { value: "needs_info", label: "Needs info" },
  { value: "not_interested", label: "Not interested" },
  { value: "unknown", label: "Unknown" },
];

function statusLabel(value) {
  return String(value || "unknown")
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function roleLabel(role) {
  return role === "assistant" ? "Assistant" : "User";
}

function formatCostUsd(usd) {
  if (usd == null) return null;
  if (usd === 0) return "$0.00";
  if (usd < 0.000001) return "<$0.000001";
  if (usd < 0.0001) return `$${usd.toFixed(6)}`;
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(3)}`;
}

function MessageTokenMeta({ metadata }) {
  if (!metadata) return null;
  const usage = metadata.usage || {};
  const model = metadata.model || {};
  const cost = metadata.cost || {};
  const inputTokens = usage.input_tokens ?? usage.prompt_tokens;
  const outputTokens = usage.output_tokens ?? usage.completion_tokens;
  const totalTokens = usage.total_tokens;
  const totalCost = cost.total_cost_usd;
  const pricingSource = cost.pricing_source;

  const hasAny =
    model?.provider || model?.name || inputTokens != null || totalCost != null;
  if (!hasAny) return null;

  return (
    <div className="token-meta">
      {(model?.provider || model?.name) && (
        <span>{model?.provider || "-"}/{model?.name || "-"}</span>
      )}
      {metadata?.stage ? <span>{metadata.stage}</span> : null}
      {inputTokens != null ? <span title="Input tokens">↑{inputTokens}</span> : null}
      {outputTokens != null ? <span title="Output tokens">↓{outputTokens}</span> : null}
      {totalTokens != null ? <span title="Total tokens">∑{totalTokens}</span> : null}
      {totalCost != null ? (
        <span
          className="token-cost"
          title={pricingSource ? `Pricing: ${pricingSource}` : "Estimated cost"}
        >
          {formatCostUsd(totalCost)}
        </span>
      ) : null}
    </div>
  );
}

function formatRelative(epochSeconds) {
  if (!epochSeconds) return "-";
  const delta = Date.now() - Number(epochSeconds) * 1000;
  const minutes = Math.floor(delta / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatDateTime(epochSeconds) {
  if (!epochSeconds) return "-";
  return new Date(Number(epochSeconds) * 1000).toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderChannel(value) {
  const normalized = String(value || "web").toLowerCase();
  if (normalized === "whatsapp") return "WhatsApp";
  if (normalized === "telegram") return "Telegram";
  return "Web";
}

export default function ConversationsPanel() {
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("all");
  const [leadStatus, setLeadStatus] = useState("all");
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [items, setItems] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function loadList() {
      setListLoading(true);
      setListError("");
      try {
        const params = new URLSearchParams({
          limit: "120",
          offset: "0",
          channel,
          lead_status: leadStatus,
          query,
        });
        const response = await fetch(
          `${API_BASE}/v1/chatbot/monitor/conversations?${params.toString()}`
        );
        if (!response.ok) {
          throw new Error("Failed to load conversation list");
        }
        const payload = await response.json();
        if (cancelled) return;
        setItems(Array.isArray(payload) ? payload : []);

        const ids = new Set((Array.isArray(payload) ? payload : []).map((item) => item.id));
        if (!selectedConversationId || !ids.has(selectedConversationId)) {
          setSelectedConversationId(payload?.[0]?.id || "");
        }
      } catch (error) {
        if (cancelled) return;
        setListError(error.message || "Failed to load conversation list");
        setItems([]);
        setSelectedConversationId("");
      } finally {
        if (!cancelled) {
          setListLoading(false);
        }
      }
    }

    loadList();
    return () => {
      cancelled = true;
    };
  }, [channel, leadStatus, query, reloadTick]);

  useEffect(() => {
    let cancelled = false;
    async function loadDetail() {
      if (!selectedConversationId) {
        setDetail(null);
        return;
      }

      setDetailLoading(true);
      try {
        const response = await fetch(
          `${API_BASE}/v1/chatbot/monitor/conversations/${encodeURIComponent(
            selectedConversationId
          )}`
        );
        if (!response.ok) {
          throw new Error("Failed to load conversation detail");
        }
        const payload = await response.json();
        if (!cancelled) {
          setDetail(payload);
        }
      } catch {
        if (!cancelled) {
          setDetail(null);
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    }

    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedConversationId]);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedConversationId) || null,
    [items, selectedConversationId]
  );

  return (
    <main className="conversations-panel">
      <header className="conversations-header">
        <div>
          <h1>Conversation Monitor</h1>
          <p>Inspect channel activity, buyer intent, and full chat timeline.</p>
        </div>
        <button
          type="button"
          className="billing-refresh-btn"
          onClick={() => setReloadTick((value) => value + 1)}
        >
          Refresh
        </button>
      </header>

      <div className="conversations-toolbar">
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search user, summary, or latest message..."
        />
        <select value={channel} onChange={(event) => setChannel(event.target.value)}>
          {CHANNEL_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select value={leadStatus} onChange={(event) => setLeadStatus(event.target.value)}>
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {listError ? <div className="billing-error">{listError}</div> : null}

      <div className="conversations-layout">
        <aside className="conversations-list">
          {listLoading ? (
            <div className="conversations-empty">Loading conversations...</div>
          ) : items.length === 0 ? (
            <div className="conversations-empty">No conversations found for this filter.</div>
          ) : (
            items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`conversation-card ${
                  item.id === selectedConversationId ? "active" : ""
                }`}
                onClick={() => setSelectedConversationId(item.id)}
              >
                <div className="conversation-card-top">
                  <span className="conversation-channel">{renderChannel(item.channel)}</span>
                  <span className={`conversation-status status-${item.lead_status}`}>
                    {statusLabel(item.lead_status)}
                  </span>
                  <span className="conversation-time">{formatRelative(item.updated_at)}</span>
                </div>
                <p className="conversation-user">{item.external_user_id || item.user_id}</p>

                <div className="conversation-preview-bubbles">
                  {item.last_user_message ? (
                    <div className="preview-bubble user">{item.last_user_message}</div>
                  ) : null}
                  {item.last_assistant_message ? (
                    <div className="preview-bubble assistant">{item.last_assistant_message}</div>
                  ) : null}
                </div>

                <p className="conversation-summary">{item.summary}</p>
              </button>
            ))
          )}
        </aside>

        <section className="conversation-detail">
          {!selectedItem ? (
            <div className="conversations-empty">Select a conversation to view detail.</div>
          ) : detailLoading ? (
            <div className="conversations-empty">Loading detail...</div>
          ) : !detail ? (
            <div className="conversations-empty">Conversation detail not available.</div>
          ) : (
            <>
              <div className="conversation-detail-head">
                <h2>{detail.title || "Conversation detail"}</h2>
                <div className="conversation-meta">
                  <span>{renderChannel(detail.channel)}</span>
                  <span>{detail.external_user_id || detail.user_id}</span>
                  <span>{statusLabel(detail.lead_status)}</span>
                  <span>{detail.message_count} messages</span>
                  <span>Updated {formatDateTime(detail.updated_at)}</span>
                </div>
                <p className="conversation-summary">{detail.summary}</p>
              </div>

              <div className="conversation-thread">
                {(detail.messages || []).length === 0 ? (
                  <div className="conversations-empty">No messages in this conversation.</div>
                ) : (
                  detail.messages.map((message, index) => (
                    <article
                      key={`${message.role}-${message.created_at || index}-${index}`}
                      className={`thread-message ${message.role === "user" ? "user" : "assistant"}`}
                    >
                      <div className="thread-meta">
                        <span>{roleLabel(message.role)}</span>
                        <span>{formatDateTime(message.created_at)}</span>
                      </div>
                      <div className="thread-bubble">
                        {message.role === "assistant" ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {String(message.content || "")}
                          </ReactMarkdown>
                        ) : (
                          <p>{message.content}</p>
                        )}
                        {message.role === "assistant" && (
                          <MessageTokenMeta metadata={message.metadata} />
                        )}
                      </div>
                    </article>
                  ))
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
