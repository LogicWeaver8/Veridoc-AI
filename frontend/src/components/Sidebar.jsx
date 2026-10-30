import Icon from "./Icons.jsx";
import { formatRelative } from "../utils/format.js";

const NAV_ITEMS = [
  { id: "chat", label: "Ask VeriDox", icon: "chat" },
  { id: "dashboard", label: "Overview", icon: "grid" },
  { id: "documents", label: "Document library", icon: "file" },
  { id: "batch", label: "Batch Q&A", icon: "layers" },
  { id: "settings", label: "Settings", icon: "settings" },
];

export default function Sidebar({
  view,
  onNavigate,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  session,
  apiOnline,
  llmMock,
  onLogout,
  open,
  onClose,
  loadingConversations,
}) {
  const initials = (session?.email || "V").slice(0, 2).toUpperCase();

  function navigate(target) {
    onNavigate(target);
    onClose();
  }

  return (
    <>
      {open ? <button type="button" className="sidebar-scrim" aria-label="Close menu" onClick={onClose} /> : null}
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`} aria-label="Workspace navigation">
        <div className="sidebar-brand">
          <div className="brand-mark">V</div>
          <div className="sidebar-brand-text">
            <strong>VeriDox AI</strong>
            <span>Grounded knowledge</span>
          </div>
          <button type="button" className="icon-button sidebar-close" onClick={onClose} aria-label="Close menu">
            <Icon name="close" size={17} />
          </button>
        </div>

        <button type="button" className="new-chat-button" onClick={() => { onNewChat(); onClose(); }}>
          <Icon name="plus" size={17} />
          New conversation
        </button>

        <nav className="sidebar-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-item ${view === item.id ? "nav-item-active" : ""}`}
              onClick={() => navigate(item.id)}
            >
              <Icon name={item.icon} size={17} />
              <span>{item.label}</span>
              {item.id === "documents" ? <span className="nav-hint">PDF · TXT · MD</span> : null}
            </button>
          ))}
        </nav>

        <div className="sidebar-section">
          <div className="sidebar-section-head">
            <span>Recent conversations</span>
            {loadingConversations ? <span className="tiny-loader" aria-hidden="true" /> : null}
          </div>
          <div className="conversation-list">
            {conversations.length === 0 && !loadingConversations ? (
              <p className="sidebar-empty">No conversations yet. Ask your first question.</p>
            ) : null}
            {conversations.map((conversation) => (
              <div
                key={conversation.id}
                className={`conversation-item ${
                  conversation.id === activeConversationId && view === "chat" ? "conversation-item-active" : ""
                }`}
              >
                <button
                  type="button"
                  className="conversation-open"
                  onClick={() => {
                    onSelectConversation(conversation.id);
                    onClose();
                  }}
                  title={conversation.title}
                >
                  <Icon name="chat" size={14} />
                  <span className="conversation-text">
                    <span className="conversation-title">{conversation.title}</span>
                    <span className="conversation-meta">
                      {conversation.message_count} messages · {formatRelative(conversation.updated_at)}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  className="conversation-delete"
                  aria-label={`Delete conversation ${conversation.title}`}
                  onClick={() => onDeleteConversation(conversation)}
                >
                  <Icon name="trash" size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className={`connection-dot ${apiOnline ? "online" : "offline"}`} />
            {apiOnline ? "API connected" : "API offline"}
            <span className={`mode-chip ${llmMock ? "mode-mock" : "mode-live"}`}>
              {llmMock ? "Mock LLM" : "LLM live"}
            </span>
          </div>
          <div className="account-card">
            <div className="account-avatar">{initials}</div>
            <div className="account-text">
              <strong>{session?.email || "Local user"}</strong>
              <span>{session?.workspace || "workspace"}</span>
            </div>
            <button type="button" className="icon-button" onClick={onLogout} aria-label="Sign out" title="Sign out">
              <Icon name="logout" size={16} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
