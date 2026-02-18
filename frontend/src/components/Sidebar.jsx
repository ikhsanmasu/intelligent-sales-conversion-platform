export default function Sidebar({
  chats,
  activeChatId,
  activeTab,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onTabChange,
  isCollapsed,
  onToggleCollapse,
  theme,
  onToggleTheme,
}) {
  const navItems = [
    { key: "chat", label: "Chats", icon: <ChatIcon /> },
    { key: "conversations", label: "Conversations", icon: <ThreadsIcon /> },
    { key: "billing", label: "Billing", icon: <BillingIcon /> },
    { key: "config", label: "Config", icon: <ConfigIcon /> },
  ];

  return (
    <aside className={`sidebar ${isCollapsed ? "collapsed" : ""}`}>
      <div className="sidebar-top">
        <button
          className="icon-btn"
          onClick={onToggleCollapse}
          title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <PanelIcon collapsed={isCollapsed} />
        </button>

        {!isCollapsed && (
          <button className="brand" onClick={() => onTabChange("chat")} title="M Aget">
            <span className="brand-logo">
              <BrandLogo />
            </span>
            <span className="brand-label">Sales Agent</span>
          </button>
        )}
      </div>

      <div className="sidebar-primary-actions">
        <button className="new-chat-btn" onClick={onNewChat} title="New chat">
          <EditIcon />
          <span>New chat</span>
        </button>
      </div>

      {activeTab === "chat" && (
        <div className="chat-list">
          {!isCollapsed && <p className="chat-list-label">Chats</p>}
          {isCollapsed ? (
            <div className="chat-list-collapsed" title={`${chats.length} chats`}>
              {chats.length}
            </div>
          ) : chats.length === 0 ? (
            <p className="chat-empty">No chats yet</p>
          ) : (
            chats.map((chat) => (
              <div
                key={chat.id}
                className={`chat-item ${chat.id === activeChatId ? "active" : ""}`}
                onClick={() => onSelectChat(chat.id)}
                title={chat.title}
              >
                <span className="chat-item-title">{chat.title}</span>
                <span
                  className="chat-delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteChat(chat.id);
                  }}
                  role="button"
                  tabIndex={0}
                  aria-label="Delete chat"
                  title="Delete chat"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onDeleteChat(chat.id);
                    }
                  }}
                >
                  <TrashIcon />
                </span>
              </div>
            ))
          )}
        </div>
      )}

      <div className="sidebar-footer">
        {!isCollapsed && <p className="workspace-label">Workspace</p>}

        {navItems.map((tab) => (
          <button
            key={tab.key}
            className={`nav-btn ${activeTab === tab.key ? "active" : ""}`}
            onClick={() => onTabChange(tab.key)}
            title={tab.label}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}

        <button
          className="nav-btn"
          onClick={onToggleTheme}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          <span className="tab-icon">{theme === "dark" ? <SunIcon /> : <MoonIcon />}</span>
          <span className="tab-label">{theme === "dark" ? "Light mode" : "Dark mode"}</span>
        </button>
      </div>
    </aside>
  );
}

function BrandLogo() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3.2L16.8 6V11.5L12 14.3L7.2 11.5V6L12 3.2ZM12 9.8L14.6 8.3V5.3L12 3.8L9.4 5.3V8.3L12 9.8ZM12 14.2L16.8 11.4V16.9L12 19.7L7.2 16.9V11.4L12 14.2Z"
        fill="currentColor"
      />
    </svg>
  );
}

function PanelIcon({ collapsed }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      aria-hidden="true"
      style={{
        transform: collapsed ? "rotate(180deg)" : "rotate(0deg)",
        transition: "transform 0.2s ease",
      }}
    >
      <path
        d="M15.2 19L8.2 12L15.2 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
      <path
        d="M4 20H8L18.6 9.4C19.1 8.9 19.1 8.1 18.6 7.6L16.4 5.4C15.9 4.9 15.1 4.9 14.6 5.4L4 16V20Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden="true">
      <path
        d="M5 7H19M9 7V5.8C9 5.36 9.36 5 9.8 5H14.2C14.64 5 15 5.36 15 5.8V7M8.5 10V17M12 10V17M15.5 10V17"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
      <path
        d="M5.5 6.5H18.5C19.3 6.5 20 7.2 20 8V15C20 15.8 19.3 16.5 18.5 16.5H10L6.2 19.3V16.5H5.5C4.7 16.5 4 15.8 4 15V8C4 7.2 4.7 6.5 5.5 6.5Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ConfigIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
      <path
        d="M12 8.8C10.23 8.8 8.8 10.23 8.8 12C8.8 13.77 10.23 15.2 12 15.2C13.77 15.2 15.2 13.77 15.2 12C15.2 10.23 13.77 8.8 12 8.8Z"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path
        d="M4.7 13.2V10.8L6.4 10.4C6.55 9.95 6.74 9.53 6.99 9.15L6.08 7.65L7.75 5.98L9.25 6.89C9.63 6.64 10.05 6.45 10.5 6.3L10.9 4.6H13.1L13.5 6.3C13.95 6.45 14.37 6.64 14.75 6.89L16.25 5.98L17.92 7.65L17.01 9.15C17.26 9.53 17.45 9.95 17.6 10.4L19.3 10.8V13.2L17.6 13.6C17.45 14.05 17.26 14.47 17.01 14.85L17.92 16.35L16.25 18.02L14.75 17.11C14.37 17.36 13.95 17.55 13.5 17.7L13.1 19.4H10.9L10.5 17.7C10.05 17.55 9.63 17.36 9.25 17.11L7.75 18.02L6.08 16.35L6.99 14.85C6.74 14.47 6.55 14.05 6.4 13.6L4.7 13.2Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function BillingIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
      <path
        d="M4.5 7.5C4.5 6.4 5.4 5.5 6.5 5.5H17.5C18.6 5.5 19.5 6.4 19.5 7.5V16.5C19.5 17.6 18.6 18.5 17.5 18.5H6.5C5.4 18.5 4.5 17.6 4.5 16.5V7.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M4.5 9.5H19.5M8 14H12.8"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ThreadsIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
      <path
        d="M5 6.5H15C16.1 6.5 17 7.4 17 8.5V13.5C17 14.6 16.1 15.5 15 15.5H9.2L6 18V15.5H5C3.9 15.5 3 14.6 3 13.5V8.5C3 7.4 3.9 6.5 5 6.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9 3.5H19C20.1 3.5 21 4.4 21 5.5V10.5C21 11.6 20.1 12.5 19 12.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
      <path
        d="M19.5 14.4C18.67 14.86 17.72 15.12 16.7 15.12C13.5 15.12 10.9 12.52 10.9 9.32C10.9 8.03 11.32 6.83 12.03 5.86C8.5 6.52 5.8 9.62 5.8 13.35C5.8 17.55 9.2 20.95 13.4 20.95C17.1 20.95 20.17 18.28 20.84 14.78"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true">
      <path
        d="M12 17C14.76 17 17 14.76 17 12C17 9.24 14.76 7 12 7C9.24 7 7 9.24 7 12C7 14.76 9.24 17 12 17Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M12 3V5M12 19V21M21 12H19M5 12H3M18.36 5.64L16.95 7.05M7.05 16.95L5.64 18.36M18.36 18.36L16.95 16.95M7.05 7.05L5.64 5.64"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
