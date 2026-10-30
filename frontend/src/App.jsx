import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { IngestionBar, TopBar } from "./components/AppChrome.jsx";
import LoginPage from "./components/LoginPage.jsx";
import Sidebar from "./components/Sidebar.jsx";
import SourceViewer from "./components/Citations.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import DocumentsPage from "./pages/DocumentsPage.jsx";
import BatchPage from "./pages/BatchPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

const SESSION_KEY = "veridox.session";

function readSession() {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [session, setSession] = useState(readSession);
  const [view, setView] = useState("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState("");
  const [appSettings, setAppSettings] = useState(null);
  const [apiOnline, setApiOnline] = useState(true);
  const [source, setSource] = useState(null);
  const [viewerOpen, setViewerOpen] = useState(false);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refreshConversations = useCallback(async () => {
    setConversationsLoading(true);
    try {
      const data = await api.listConversations();
      if (mounted.current) setConversations(data);
    } catch {
      // The sidebar is non-critical; connection state is reported separately.
    } finally {
      if (mounted.current) setConversationsLoading(false);
    }
  }, []);

  const refreshStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const data = await api.stats();
      if (mounted.current) {
        setStats(data);
        setStatsError("");
      }
    } catch (requestError) {
      if (mounted.current) setStatsError(requestError.message);
    } finally {
      if (mounted.current) setStatsLoading(false);
    }
  }, []);

  const handleDataChanged = useCallback(() => {
    refreshStats();
    refreshConversations();
  }, [refreshStats, refreshConversations]);

  useEffect(() => {
    if (!session) return undefined;

    refreshConversations();
    refreshStats();

    api
      .appSettings()
      .then((data) => mounted.current && setAppSettings(data))
      .catch(() => {});

    api
      .health()
      .then(() => mounted.current && setApiOnline(true))
      .catch(() => mounted.current && setApiOnline(false));

    const statsTimer = window.setInterval(refreshStats, 12000);
    const healthTimer = window.setInterval(() => {
      api
        .health()
        .then(() => mounted.current && setApiOnline(true))
        .catch(() => mounted.current && setApiOnline(false));
    }, 30000);

    return () => {
      window.clearInterval(statsTimer);
      window.clearInterval(healthTimer);
    };
  }, [session, refreshConversations, refreshStats]);

  function handleLogin(nextSession) {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(nextSession));
    setSession(nextSession);
  }

  function handleLogout() {
    window.sessionStorage.removeItem(SESSION_KEY);
    setSession(null);
    setConversations([]);
    setStats(null);
    setAppSettings(null);
    setActiveConversationId(null);
    setSelectedDocumentId(null);
    setSource(null);
    setViewerOpen(false);
    setView("chat");
  }

  function startNewChat() {
    setActiveConversationId(null);
    setView("chat");
    setViewerOpen(false);
    setSidebarOpen(false);
  }

  function openConversation(conversationId) {
    setActiveConversationId(conversationId);
    setView("chat");
    setSidebarOpen(false);
  }

  async function deleteConversation(conversation) {
    const confirmed = window.confirm(`Delete the conversation "${conversation.title}"?`);
    if (!confirmed) return;
    try {
      await api.deleteConversation(conversation.id);
      if (activeConversationId === conversation.id) setActiveConversationId(null);
      setConversations((previous) => previous.filter((item) => item.id !== conversation.id));
      refreshStats();
    } catch (requestError) {
      window.alert(requestError.message);
    }
  }

  function openDocument(documentId) {
    setSelectedDocumentId(documentId);
    setView("documents");
  }

  function openSource(citation, question) {
    setSource({ citation, question });
    setViewerOpen(true);
  }

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId),
    [conversations, activeConversationId],
  );

  if (!session) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="app-shell">
      <Sidebar
        view={view}
        onNavigate={setView}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={openConversation}
        onNewChat={startNewChat}
        onDeleteConversation={deleteConversation}
        session={session}
        apiOnline={apiOnline}
        llmMock={Boolean(appSettings?.llm_is_mock)}
        onLogout={handleLogout}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        loadingConversations={conversationsLoading}
      />

      <div className="main-shell">
        <TopBar
          onOpenMenu={() => setSidebarOpen(true)}
          apiOnline={apiOnline}
          viewerAvailable={Boolean(source)}
          viewerOpen={viewerOpen && Boolean(source)}
          onToggleViewer={() => setViewerOpen((value) => !value)}
        />
        <IngestionBar counts={stats?.ingestion_counts} onOpenDocuments={() => setView("documents")} />

        <main className={`main-content ${view === "chat" ? "main-content-chat" : ""}`}>
          {view === "chat" ? (
            <ChatPage
              conversationId={activeConversationId}
              conversationTitle={activeConversation?.title}
              onConversationChange={setActiveConversationId}
              onConversationsChanged={handleDataChanged}
              onOpenSource={openSource}
              stats={stats}
              session={session}
            />
          ) : null}

          {view === "dashboard" ? (
            <DashboardPage
              stats={stats}
              loading={statsLoading}
              error={statsError}
              onRefresh={refreshStats}
              onNavigate={setView}
              onOpenDocument={openDocument}
              onOpenConversation={openConversation}
            />
          ) : null}

          {view === "documents" ? (
            <DocumentsPage
              selectedDocumentId={selectedDocumentId}
              onSelectDocument={setSelectedDocumentId}
              onDataChanged={handleDataChanged}
            />
          ) : null}

          {view === "batch" ? <BatchPage appSettings={appSettings} /> : null}

          {view === "settings" ? (
            <SettingsPage onDataChanged={handleDataChanged} />
          ) : null}
        </main>
      </div>

      {viewerOpen && source ? (
        <SourceViewer
          citation={source.citation}
          question={source.question}
          onClose={() => setViewerOpen(false)}
        />
      ) : null}
    </div>
  );
}
