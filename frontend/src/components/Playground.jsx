import { useState, useRef, useEffect, useMemo } from "react";
import Chart from "react-apexcharts";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

const API_BASE = import.meta.env.VITE_API_URL || "";
const USER_ID = "0";

export default function Playground({
  chat,
  messages,
  setMessages,
  onUpdateChat,
  onUpdateChatById,
  onNewChat,
  theme,
}) {
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedThinkingId, setSelectedThinkingId] = useState(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages]);

  useEffect(() => {
    if (selectedThinkingId === null) {
      return;
    }

    const selectedMessage = resolveThinkingMessage(messages, selectedThinkingId);
    if (!selectedMessage || !selectedMessage.thinking) {
      setSelectedThinkingId(null);
    }
  }, [messages, selectedThinkingId]);

  const handleInput = (e) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 140) + "px";
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (chat) {
        handleSend();
      } else {
        handleStartChat();
      }
    }
  };

  const sendMessage = async ({ text, targetChat, historySource = [] }) => {
    if (!text || isStreaming || !targetChat) return;

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setIsStreaming(true);

    const isFirstMessage = historySource.length === 0;

    const pairId = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    const userMsg = { id: `u-${pairId}`, role: "user", content: text };
    const assistantMsg = {
      id: `a-${pairId}`,
      role: "assistant",
      content: "",
      thinking: "",
      isStreaming: true,
      thinkingDone: false,
      thinkingStartedAt: Date.now(),
      thinkingDurationMs: null,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    // Update title in sidebar immediately for first message
    if (isFirstMessage) {
      if (targetChat.id === chat?.id) {
        onUpdateChat(() => ({ title: text.slice(0, 40) }));
      } else {
        onUpdateChatById?.(targetChat.id, () => ({ title: text.slice(0, 40) }));
      }
    }

    let fullContent = "";
    let fullThinking = "";

    // Build history from existing messages (exclude the ones we just added)
    const history = historySource
      .filter((m) => m.role === "user" || m.role === "assistant")
      .filter((m) => m.content && m.content.length > 0)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const response = await fetch(`${API_BASE}/v1/chatbot/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history,
          user_id: USER_ID,
          conversation_id: targetChat.id,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("Failed to stream response");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let partial = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        partial += decoder.decode(value, { stream: true });
        const lines = partial.split("\n");
        partial = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;

          const data = JSON.parse(line.slice(6));

          if (data.type === "thinking") {
            fullThinking += data.content;
            setMessages((prev) => {
              const msgs = [...prev];
              const last = { ...msgs[msgs.length - 1] };
              last.thinking += data.content;
              msgs[msgs.length - 1] = last;
              return msgs;
            });
          }

          if (data.type === "content") {
            fullContent += data.content;
            setMessages((prev) => {
              const msgs = [...prev];
              const last = { ...msgs[msgs.length - 1] };
              if (!last.thinkingDone && last.thinking) {
                last.thinkingDone = true;
                if (!last.thinkingDurationMs && last.thinkingStartedAt) {
                  last.thinkingDurationMs = Date.now() - last.thinkingStartedAt;
                }
              }
              last.content += data.content;
              msgs[msgs.length - 1] = last;
              return msgs;
            });
          }
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const msgs = [...prev];
        const last = { ...msgs[msgs.length - 1] };
        last.content = `Error: ${err.message}`;
        last.isStreaming = false;
        msgs[msgs.length - 1] = last;
        return msgs;
      });
      setIsStreaming(false);
      return;
    }

    // Mark streaming done
    setMessages((prev) => {
      const msgs = [...prev];
      const last = { ...msgs[msgs.length - 1] };
      last.isStreaming = false;
      last.thinkingDone = true;
      if (!last.thinkingDurationMs && last.thinkingStartedAt) {
        last.thinkingDurationMs = Date.now() - last.thinkingStartedAt;
      }
      msgs[msgs.length - 1] = last;
      return msgs;
    });

    setIsStreaming(false);

    // Save messages to backend
    try {
      await fetch(
        `${API_BASE}/v1/chatbot/conversations/${USER_ID}/${targetChat.id}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_message: text,
            assistant_content: fullContent,
            assistant_thinking: fullThinking || null,
          }),
        }
      );
    } catch {
      // ignore save errors
    }

    // Update title on first message
    if (isFirstMessage) {
      const title = text.slice(0, 40);
      try {
        await fetch(
          `${API_BASE}/v1/chatbot/conversations/${USER_ID}/${targetChat.id}/title`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title }),
          }
        );
      } catch {
        // ignore title update errors
      }
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !chat) return;

    await sendMessage({ text, targetChat: chat, historySource: messages });
  };

  const handleStartChat = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    const newChat = await onNewChat();
    if (!newChat) return;

    await sendMessage({ text, targetChat: newChat, historySource: [] });
  };

  const handleOpenThinking = (messageId) => {
    setSelectedThinkingId(messageId);
  };

  const selectedThinkingMessage = resolveThinkingMessage(
    messages,
    selectedThinkingId
  );

  if (!chat) {
    return (
      <main className="playground">
        <div className="playground-empty">
          <div className="empty-logo">
            <EmptyStateLogo />
          </div>
          <h1>How can I help you today?</h1>
          <p>Ask anything to start a new chat</p>
          <div className="home-composer">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Message Agentic Chatbot"
              rows={1}
            />
            <button
              className="send-btn"
              onClick={handleStartChat}
              disabled={isStreaming || !input.trim()}
              aria-label="Send message"
            >
              &#8593;
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="playground">
      <div className="playground-header">
        <div>
          <h2>{chat.title || "New chat"}</h2>
          <p>Assistant Playground</p>
        </div>
        <span className={`playground-status ${isStreaming ? "live" : ""}`}>
          {isStreaming ? "Streaming" : "Ready"}
        </span>
      </div>

      <div className="chat-content">
        <div className="messages-area">
          {messages.map((msg, i) => {
            const messageKey = msg.id || `idx-${i}`;
            return (
              <MessageBubble
                key={messageKey}
                message={msg}
                messageKey={messageKey}
                isThinkingSelected={selectedThinkingId === messageKey}
                onOpenThinking={handleOpenThinking}
                theme={theme}
              />
            );
          })}
          <div ref={messagesEndRef} />
        </div>

        {selectedThinkingMessage && (
          <aside className="thinking-sidebar">
            <div className="thinking-sidebar-header">
              <div>
                <h3>Thought process</h3>
                <p>
                  {selectedThinkingMessage.isStreaming &&
                  !selectedThinkingMessage.thinkingDone
                    ? `Thinking: ${extractCurrentActivity(
                        selectedThinkingMessage.thinking
                      )}`
                    : `Thought for ${formatThinkingDuration(
                        selectedThinkingMessage.thinkingDurationMs
                      )}`}
                </p>
              </div>
              <button
                type="button"
                className="thinking-sidebar-close"
                onClick={() => setSelectedThinkingId(null)}
                aria-label="Close thought panel"
              >
                &times;
              </button>
            </div>
            <div className="thinking-sidebar-body">
              <ThinkingDetail text={selectedThinkingMessage.thinking} />
            </div>
          </aside>
        )}
      </div>

      <div className="input-area">
        <div className="input-form">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Message Agentic Chatbot"
            rows={1}
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            aria-label="Send message"
          >
            &#8593;
          </button>
        </div>
      </div>
    </main>
  );
}

function EmptyStateLogo() {
  return (
    <svg viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <rect
        x="2"
        y="2"
        width="60"
        height="60"
        rx="20"
        fill="currentColor"
        opacity="0.08"
      />
      <rect x="2" y="2" width="60" height="60" rx="20" stroke="currentColor" opacity="0.2" />
      <path
        d="M32 14L36.7 25.3L49 27L39.8 35.4L42.2 48L32 42L21.8 48L24.2 35.4L15 27L27.3 25.3L32 14Z"
        fill="currentColor"
      />
    </svg>
  );
}

function MessageBubble({
  message,
  messageKey,
  isThinkingSelected,
  onOpenThinking,
  theme,
}) {
  if (message.role === "user") {
    return <div className="message user">{message.content}</div>;
  }

  const hasThinking = message.thinking && message.thinking.length > 0;
  const hasContent = message.content && message.content.length > 0;
  const isThinkingActive = message.isStreaming && !message.thinkingDone;
  const reportPayload =
    !message.isStreaming && message.content ? parseReportPayload(message.content) : null;
  const chartPayload =
    !message.isStreaming && !reportPayload && message.content
      ? parseChartPayload(message.content)
      : null;

  // Streaming with nothing yet
  if (message.isStreaming && !hasThinking && !hasContent) {
    return (
      <div className="message assistant">
        <div className="thinking-pill active">
          <div className="thinking-pill-main" aria-live="polite">
            <ThinkingSpinner />
            <span>Thinking...</span>
          </div>
        </div>
      </div>
    );
  }

  const messageClass = [
    "message assistant",
    chartPayload?.chart ? "chart-message" : "",
    reportPayload ? "report-message" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={messageClass}>
      {hasThinking && (
        <button
          type="button"
          className={`thinking-pill ${isThinkingActive ? "active" : ""} ${
            isThinkingSelected ? "selected" : ""
          }`}
          onClick={() => onOpenThinking?.(messageKey)}
          aria-label="Open thought process panel"
        >
          <span className="thinking-pill-main">
            {isThinkingActive ? (
              <ThinkingSpinner />
            ) : (
              <span className="thinking-dot" />
            )}
            <span>
              {isThinkingActive
                ? `Thinking: ${extractCurrentActivity(message.thinking)}`
                : `Thought for ${formatThinkingDuration(message.thinkingDurationMs)}`}
            </span>
          </span>
          <span className="thinking-pill-open">Open</span>
        </button>
      )}
      {hasContent && !reportPayload && !chartPayload?.chart && !chartPayload?.error && (
        <div className={`content-block ${!hasThinking ? "only" : ""}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
            {message.content}
          </ReactMarkdown>
        </div>
      )}
      {reportPayload && <ReportBlock report={reportPayload} />}
      {chartPayload?.error && (
        <div className={`content-block ${!hasThinking ? "only" : ""}`}>
          <p>{chartPayload.error}</p>
        </div>
      )}
      {chartPayload?.chart && (
        <ChartBlock chart={chartPayload.chart} theme={theme} />
      )}
    </div>
  );
}

function ThinkingSpinner() {
  return (
    <span className="thinking-spinner">
      <span className="spinner-dot" />
      <span className="spinner-dot" />
      <span className="spinner-dot" />
    </span>
  );
}

function ThinkingDetail({ text }) {
  const lines = text.split("\n").filter((line) => line.trim() !== "");

  return (
    <ul className="thinking-detail-list">
      {lines.map((line, index) => (
        <li
          key={index}
          className={`thinking-detail-line ${line.startsWith("SQL:") ? "sql" : ""} ${
            isThinkingErrorLine(line) ? "error" : ""
          }`}
        >
          {line}
        </li>
      ))}
    </ul>
  );
}

function formatThinkingDuration(durationMs) {
  if (!durationMs || durationMs < 700) {
    return "a few seconds";
  }

  const seconds = Math.max(1, Math.round(durationMs / 1000));
  return `${seconds}s`;
}

function extractCurrentActivity(thinkingText) {
  if (!thinkingText) {
    return "working";
  }

  const lines = thinkingText
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (lines.length === 0) {
    return "working";
  }

  const latestLine = lines[lines.length - 1];
  if (latestLine.length <= 72) {
    return latestLine;
  }

  return `${latestLine.slice(0, 72)}...`;
}

function isThinkingErrorLine(line) {
  return (
    line.startsWith("Parse error:") ||
    line.startsWith("Validation failed:") ||
    line.startsWith("Execution error:") ||
    line.startsWith("Error:")
  );
}

function resolveThinkingMessage(messageList, selectionId) {
  if (selectionId === null) {
    return null;
  }

  if (String(selectionId).startsWith("idx-")) {
    const index = Number(String(selectionId).slice(4));
    const message = messageList[index];
    if (message?.role === "assistant" && message.thinking) {
      return message;
    }
    return null;
  }

  return (
    messageList.find(
      (m) => m.id === selectionId && m.role === "assistant" && m.thinking
    ) || null
  );
}

function parseChartPayload(content) {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
    return null;
  }
  try {
    const payload = JSON.parse(trimmed);
    if (payload?.error) {
      return { error: String(payload.error) };
    }
    if (payload?.chart) {
      return { chart: payload.chart };
    }
    if (payload?.type && payload?.series) {
      return { chart: payload };
    }
  } catch {
    return null;
  }
  return null;
}

function parseReportPayload(content) {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
    return null;
  }
  try {
    const payload = JSON.parse(trimmed);
    if (payload?.report) {
      return payload.report;
    }
  } catch {
    return null;
  }
  return null;
}

function downloadBase64File(base64, filename, mimeType) {
  try {
    const binary = atob(base64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    const blob = new Blob([bytes], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("Failed to download file", err);
  }
}

function ReportBlock({ report }) {
  const [showPreview, setShowPreview] = useState(true);
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);
  const rawFilename = report?.filename || "report.md";
  const content = report?.content || "";

  const handleDownloadPdf = async () => {
    if (isDownloadingPdf) return;

    const pdfFilename = rawFilename.toLowerCase().endsWith(".pdf")
      ? rawFilename
      : rawFilename.replace(/\.[^.]+$/, "") + ".pdf";

    if (report?.pdf_base64) {
      downloadBase64File(report.pdf_base64, pdfFilename, "application/pdf");
      return;
    }

    if (!report?.content) {
      return;
    }

    try {
      setIsDownloadingPdf(true);
      const response = await fetch(`${API_BASE}/v1/report/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report: {
            title: report?.title || "Report",
            period: report?.period || "",
            content: report?.content || "",
            filename: report?.filename || "report.pdf",
          },
        }),
      });
      if (!response.ok) {
        throw new Error("Failed to generate PDF");
      }
      const data = await response.json();
      if (data?.report?.pdf_base64) {
        const resolvedName =
          data.report.filename && data.report.filename.endsWith(".pdf")
            ? data.report.filename
            : pdfFilename;
        downloadBase64File(data.report.pdf_base64, resolvedName, "application/pdf");
        return;
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsDownloadingPdf(false);
    }
  };

  return (
    <div className="report-block">
      <div className="report-header">
        <div>
          <h4>{report?.title || "Report"}</h4>
          {report?.period && <p className="report-period">{report.period}</p>}
        </div>
        <div className="report-actions">
          <button
            type="button"
            className="report-btn ghost"
            onClick={() => setShowPreview((prev) => !prev)}
          >
            {showPreview ? "Hide preview" : "Show preview"}
          </button>
          <button
            type="button"
            className="report-btn"
            onClick={handleDownloadPdf}
            disabled={isDownloadingPdf}
          >
            {isDownloadingPdf ? "Preparing PDF..." : "Download PDF"}
          </button>
        </div>
      </div>
      {showPreview && (
        <div className="report-preview">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
            {content}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}

function formatChartNumber(val) {
  if (val === null || val === undefined) return "0";
  return new Intl.NumberFormat("id-ID", {
    maximumFractionDigits: 2,
  }).format(val);
}

function ChartBlock({ chart, theme }) {
  const type = normalizeChartType(chart?.type);
  const normalized = useMemo(() => normalizeApexSeries(chart, type), [chart, type]);
  const unit = chart?.unit || "";

  const options = useMemo(() => {
    const textMuted = getCssVar("--text-muted", "#717171");
    const textPrimary = getCssVar("--text-primary", "#141414");
    const border = getCssVar("--border", "#e8e8e8");
    const resolvedTheme = theme || getCurrentTheme();
    const isDark = resolvedTheme === "dark";
    const isSingleSeries = normalized.series.length <= 1;

    const baseOptions = {
      chart: {
        type: type === "area" ? "area" : type,
        toolbar: { show: false },
        foreColor: textMuted,
        fontFamily: "Inter, Segoe UI, sans-serif",
        background: "transparent",
      },
      colors: CHART_COLORS,
      grid: {
        borderColor: border,
        strokeDashArray: 4,
      },
      legend: {
        show: type === "pie" || !isSingleSeries,
        position: "bottom",
        labels: { colors: textMuted },
      },
      dataLabels: { enabled: false },
      theme: { mode: isDark ? "dark" : "light" },
      tooltip: {
        theme: isDark ? "dark" : "light",
        y: {
          formatter: (val) => formatChartNumber(val) + (unit ? ` ${unit}` : ""),
        },
      },
      responsive: [
        {
          breakpoint: 640,
          options: {
            chart: { height: 300 },
            xaxis: { labels: { style: { fontSize: "10px" } } },
            yaxis: { labels: { style: { fontSize: "10px" } } },
          },
        },
      ],
    };

    // Pie / Donut
    if (type === "pie") {
      return {
        ...baseOptions,
        labels: normalized.labels,
        dataLabels: {
          enabled: true,
          formatter: (val) => val.toFixed(1) + "%",
          style: { fontSize: "12px", fontWeight: 500, colors: [textPrimary] },
          dropShadow: { enabled: false },
        },
        plotOptions: {
          pie: {
            donut: { size: "58%" },
            expandOnClick: true,
          },
        },
        tooltip: {
          y: {
            formatter: (val) => formatChartNumber(val) + (unit ? ` ${unit}` : ""),
          },
        },
      };
    }

    // Build annotations from chart.annotations
    const annotations = {};
    if (Array.isArray(chart?.annotations) && chart.annotations.length > 0) {
      annotations.yaxis = chart.annotations.map((a) => ({
        y: a.y,
        borderColor: a.color || "#ef4444",
        strokeDashArray: 4,
        label: {
          text: a.label || "",
          position: "left",
          borderColor: a.color || "#ef4444",
          style: {
            color: "#fff",
            background: a.color || "#ef4444",
            fontSize: "11px",
            padding: { left: 6, right: 6, top: 2, bottom: 2 },
          },
        },
      }));
    }

    // Bar / Line / Area
    return {
      ...baseOptions,
      annotations,
      xaxis: {
        type: "category",
        title: { text: chart?.x_label || "", style: { color: textPrimary } },
        labels: { rotate: -25, style: { fontSize: "11px", colors: textMuted } },
        axisBorder: { color: border },
        axisTicks: { color: border },
      },
      yaxis: {
        title: { text: chart?.y_label || "", style: { color: textPrimary } },
        labels: {
          style: { colors: textMuted },
          formatter: (val) => formatChartNumber(val),
        },
      },
      plotOptions: {
        bar: {
          borderRadius: 4,
          columnWidth: isSingleSeries ? "50%" : "55%",
          distributed: isSingleSeries && type === "bar",
        },
      },
      stroke: {
        curve: "smooth",
        width: type === "bar" ? 0 : 3,
      },
      fill: {
        type: type === "area" ? "gradient" : "solid",
        gradient: {
          shadeIntensity: 1,
          opacityFrom: 0.3,
          opacityTo: 0.05,
          stops: [0, 90, 100],
        },
      },
      markers: {
        size: 0,
        hover: { size: 5, sizeOffset: 3 },
      },
    };
  }, [chart, type, normalized.labels, normalized.series.length, unit, theme]);

  const height = type === "pie" ? 360 : 420;

  return (
    <div className="chart-block">
      <div className="chart-header">
        <div>
          <h4>{chart?.title || "Chart"}</h4>
          {chart?.subtitle && <p className="chart-subtitle">{chart.subtitle}</p>}
        </div>
        {unit && <span className="chart-unit">{unit}</span>}
      </div>
      <div className="chart-canvas">
        <Chart
          options={options}
          series={normalized.series}
          type={type === "area" ? "area" : type}
          height={height}
          width="100%"
        />
      </div>
    </div>
  );
}

const CHART_COLORS = [
  "#2563eb",
  "#16a34a",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#ec4899",
  "#f97316",
];

function normalizeChartType(type) {
  if (type === "line" || type === "pie" || type === "area") return type;
  return "bar";
}

function normalizeApexSeries(chart, type) {
  const rawSeries = Array.isArray(chart?.series) ? chart.series : [];
  if (type === "pie") {
    const data = rawSeries[0]?.data || [];
    const labels = data.map((point) => String(point?.x ?? ""));
    const series = data.map((point) => toNumber(point?.y));
    return { labels, series };
  }

  const series = rawSeries.map((item, idx) => ({
    name: item?.name || `Series ${idx + 1}`,
    data: Array.isArray(item?.data)
      ? item.data.map((point) => ({
          x: String(point?.x ?? ""),
          y: toNumber(point?.y),
        }))
      : [],
  }));

  return { labels: [], series };
}

function toNumber(value) {
  if (value === null || value === undefined) return 0;
  const num = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(num) ? num : 0;
}

function getCssVar(name, fallback) {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name);
  return value ? value.trim() : fallback;
}

function getCurrentTheme() {
  if (typeof document === "undefined") return "light";
  return document.documentElement.getAttribute("data-theme") || "light";
}
