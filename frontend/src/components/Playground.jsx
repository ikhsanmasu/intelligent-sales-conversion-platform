import { useState, useRef, useEffect } from "react";
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
    if (selectedThinkingId === null) return;

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
      metadata: null,
      isStreaming: true,
      thinkingDone: false,
      thinkingStartedAt: Date.now(),
      thinkingDurationMs: null,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    if (isFirstMessage) {
      if (targetChat.id === chat?.id) {
        onUpdateChat(() => ({ title: text.slice(0, 40) }));
      } else {
        onUpdateChatById?.(targetChat.id, () => ({ title: text.slice(0, 40) }));
      }
    }

    let fullContent = "";
    let fullThinking = "";
    let latestMetadata = null;

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
              const next = [...prev];
              const last = { ...next[next.length - 1] };
              last.thinking += data.content;
              next[next.length - 1] = last;
              return next;
            });
          }

          if (data.type === "content") {
            fullContent += data.content;
            setMessages((prev) => {
              const next = [...prev];
              const last = { ...next[next.length - 1] };
              if (!last.thinkingDone && last.thinking) {
                last.thinkingDone = true;
                if (!last.thinkingDurationMs && last.thinkingStartedAt) {
                  last.thinkingDurationMs = Date.now() - last.thinkingStartedAt;
                }
              }
              last.content += data.content;
              next[next.length - 1] = last;
              return next;
            });
          }

          if (data.type === "meta") {
            latestMetadata = data.metadata || null;
            setMessages((prev) => {
              const next = [...prev];
              const last = { ...next[next.length - 1] };
              last.metadata = data.metadata || null;
              next[next.length - 1] = last;
              return next;
            });
          }
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        const last = { ...next[next.length - 1] };
        last.content = `Error: ${err.message}`;
        last.isStreaming = false;
        next[next.length - 1] = last;
        return next;
      });
      setIsStreaming(false);
      return;
    }

    setMessages((prev) => {
      const next = [...prev];
      const last = { ...next[next.length - 1] };
      last.isStreaming = false;
      last.thinkingDone = true;
      if (!last.thinkingDurationMs && last.thinkingStartedAt) {
        last.thinkingDurationMs = Date.now() - last.thinkingStartedAt;
      }
      next[next.length - 1] = last;
      return next;
    });

    setIsStreaming(false);

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
            assistant_metadata: latestMetadata,
          }),
        }
      );
    } catch {
      // ignore save errors
    }

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

  const selectedThinkingMessage = resolveThinkingMessage(messages, selectedThinkingId);

  if (!chat) {
    return (
      <main className="playground">
        <div className="playground-empty">
          <div className="empty-logo">
            <EmptyStateLogo />
          </div>
          <h1>Halo, ada yang bisa saya bantu?</h1>
          <p>Ceritain masalah kulitmu, nanti aku bantu cari solusi yang cocok.</p>
          <div className="home-composer">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Contoh: Kulitku berminyak dan jerawatan, cocok pakai ini?"
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
                onOpenThinking={setSelectedThinkingId}
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
                  {selectedThinkingMessage.isStreaming && !selectedThinkingMessage.thinkingDone
                    ? `Thinking: ${extractCurrentActivity(selectedThinkingMessage.thinking)}`
                    : `Thought for ${formatThinkingDuration(selectedThinkingMessage.thinkingDurationMs)}`}
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
            placeholder="Tulis pertanyaanmu soal jerawat dan kebutuhan kulit..."
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
      <rect x="2" y="2" width="60" height="60" rx="20" fill="currentColor" opacity="0.08" />
      <rect x="2" y="2" width="60" height="60" rx="20" stroke="currentColor" opacity="0.2" />
      <path
        d="M32 14L36.7 25.3L49 27L39.8 35.4L42.2 48L32 42L21.8 48L24.2 35.4L15 27L27.3 25.3L32 14Z"
        fill="currentColor"
      />
    </svg>
  );
}

function MessageBubble({ message, messageKey, isThinkingSelected, onOpenThinking }) {
  if (message.role === "user") {
    return <div className="message user">{message.content}</div>;
  }

  const hasThinking = Boolean(message.thinking);
  const hasContent = Boolean(message.content);
  const messageMeta = message.metadata || null;
  const isThinkingActive = message.isStreaming && !message.thinkingDone;

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

  return (
    <div className="message assistant">
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
            {isThinkingActive ? <ThinkingSpinner /> : <span className="thinking-dot" />}
            <span>
              {isThinkingActive
                ? `Thinking: ${extractCurrentActivity(message.thinking)}`
                : `Thought for ${formatThinkingDuration(message.thinkingDurationMs)}`}
            </span>
          </span>
          <span className="thinking-pill-open">Open</span>
        </button>
      )}

      {hasContent && (
        <div className={`content-block ${!hasThinking ? "only" : ""}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{message.content}</ReactMarkdown>
        </div>
      )}

      {messageMeta && <TokenMeta metadata={messageMeta} />}
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

function TokenMeta({ metadata }) {
  const usage = metadata?.usage || {};
  const model = metadata?.model || {};
  const inputTokens = usage.input_tokens ?? usage.prompt_tokens;
  const outputTokens = usage.output_tokens ?? usage.completion_tokens;
  const totalTokens = usage.total_tokens;

  return (
    <div className="token-meta">
      {(model?.provider || model?.name) && (
        <span>
          Model: {model?.provider || "-"}
          {model?.name ? `/${model.name}` : ""}
        </span>
      )}
      {metadata?.stage ? <span>Tahap: {metadata.stage}</span> : null}
      {inputTokens !== undefined ? <span>Input: {inputTokens}</span> : null}
      {outputTokens !== undefined ? <span>Output: {outputTokens}</span> : null}
      {totalTokens !== undefined ? <span>Total: {totalTokens}</span> : null}
    </div>
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
  if (!durationMs || durationMs < 700) return "a few seconds";
  const seconds = Math.max(1, Math.round(durationMs / 1000));
  return `${seconds}s`;
}

function extractCurrentActivity(thinkingText) {
  if (!thinkingText) return "working";

  const lines = thinkingText
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (lines.length === 0) return "working";

  const latestLine = lines[lines.length - 1];
  if (latestLine.length <= 72) return latestLine;
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
  if (selectionId === null) return null;

  if (String(selectionId).startsWith("idx-")) {
    const index = Number(String(selectionId).slice(4));
    const message = messageList[index];
    if (message?.role === "assistant" && message.thinking) return message;
    return null;
  }

  return (
    messageList.find((m) => m.id === selectionId && m.role === "assistant" && m.thinking) || null
  );
}
