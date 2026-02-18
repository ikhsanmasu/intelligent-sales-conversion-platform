import { useState, useCallback, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import Playground from "./components/Playground";
import ConfigPanel from "./components/ConfigPanel";

const API_BASE = import.meta.env.VITE_API_URL || "";
const USER_ID = "0";
const SIDEBAR_STORAGE_KEY = "playground.sidebarCollapsed";
const THEME_STORAGE_KEY = "playground.theme";

function getInitialSidebarState() {
  if (typeof window === "undefined") {
    return false;
  }

  try {
    const saved = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (saved !== null) {
      return saved === "true";
    }
  } catch {
    // ignore storage access issues
  }

  return window.innerWidth < 1024;
}

function getInitialTheme() {
  if (typeof window === "undefined") {
    return "dark";
  }

  try {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === "light" || saved === "dark") {
      return saved;
    }
  } catch {
    // ignore storage access issues
  }

  return "dark";
}

export default function App() {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [activeMessages, setActiveMessages] = useState([]);
  const [activeTab, setActiveTab] = useState("chat");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(
    getInitialSidebarState
  );
  const [theme, setTheme] = useState(getInitialTheme);

  // Load conversation list on mount
  useEffect(() => {
    fetch(`${API_BASE}/v1/chatbot/conversations/${USER_ID}`)
      .then((r) => r.json())
      .then((data) => setChats(data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    try {
      window.localStorage.setItem(
        SIDEBAR_STORAGE_KEY,
        String(isSidebarCollapsed)
      );
    } catch {
      // ignore storage access issues
    }
  }, [isSidebarCollapsed]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // ignore storage access issues
    }
  }, [theme]);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }

    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const mediaQuery = window.matchMedia("(max-width: 900px)");
    const handleMediaChange = (event) => {
      if (event.matches) {
        setIsSidebarCollapsed(true);
      }
    };

    mediaQuery.addEventListener("change", handleMediaChange);
    return () => mediaQuery.removeEventListener("change", handleMediaChange);
  }, []);

  const createNewChat = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/v1/chatbot/conversations/${USER_ID}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "New Chat" }),
        }
      );
      const conv = await res.json();
      setChats((prev) => [conv, ...prev]);
      setActiveChatId(conv.id);
      setActiveMessages([]);
      setActiveTab("chat");
      return conv;
    } catch {
      // fallback: local-only chat
      const id = Date.now().toString();
      const localChat = { id, title: "New Chat" };
      setChats((prev) => [localChat, ...prev]);
      setActiveChatId(id);
      setActiveMessages([]);
      setActiveTab("chat");
      return localChat;
    }
  }, []);

  const selectChat = useCallback(
    async (chatId) => {
      setActiveChatId(chatId);
      setActiveTab("chat");
      try {
        const res = await fetch(
          `${API_BASE}/v1/chatbot/conversations/${USER_ID}/${chatId}`
        );
        const data = await res.json();
        setActiveMessages(data.messages || []);
      } catch {
        setActiveMessages([]);
      }
    },
    []
  );

  const deleteChat = useCallback(
    async (chatId) => {
      try {
        await fetch(
          `${API_BASE}/v1/chatbot/conversations/${USER_ID}/${chatId}`,
          { method: "DELETE" }
        );
      } catch {
        // ignore
      }
      setChats((prev) => prev.filter((c) => c.id !== chatId));
      if (activeChatId === chatId) {
        setActiveChatId(null);
        setActiveMessages([]);
      }
    },
    [activeChatId]
  );

  const updateChat = useCallback((chatId, updater) => {
    setChats((prev) =>
      prev.map((c) => (c.id === chatId ? { ...c, ...updater(c) } : c))
    );
  }, []);

  const activeChat = chats.find((c) => c.id === activeChatId) || null;

  const renderMainPanel = () => {
    switch (activeTab) {
      case "config":
        return <ConfigPanel />;
      default:
        return (
          <Playground
            chat={activeChat}
            messages={activeMessages}
            setMessages={setActiveMessages}
            onUpdateChat={(updater) =>
              activeChatId && updateChat(activeChatId, updater)
            }
            onUpdateChatById={(chatId, updater) => updateChat(chatId, updater)}
            onNewChat={createNewChat}
            theme={theme}
          />
        );
    }
  };

  return (
    <div className={`app ${isSidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        activeTab={activeTab}
        onSelectChat={selectChat}
        onNewChat={createNewChat}
        onDeleteChat={deleteChat}
        onTabChange={setActiveTab}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed((prev) => !prev)}
        theme={theme}
        onToggleTheme={() =>
          setTheme((prev) => (prev === "dark" ? "light" : "dark"))
        }
      />
      <section className="main-panel">{renderMainPanel()}</section>
    </div>
  );
}
