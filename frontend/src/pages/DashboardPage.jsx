import Icon from "../components/Icons.jsx";
import {
  EmptyState,
  MetricCard,
  PageHeader,
  Spinner,
  StatusBadge,
} from "../components/ui.jsx";
import { formatBytes, formatDate, formatRelative, isProcessingStatus, pluralize } from "../utils/format.js";

const PIPELINE_ORDER = ["completed", "uploaded", "extracting", "chunking", "embedding", "indexing", "failed"];
const PIPELINE_LABELS = {
  completed: "Completed",
  uploaded: "Queued",
  extracting: "Extracting",
  chunking: "Chunking",
  embedding: "Embedding",
  indexing: "Indexing",
  failed: "Failed",
};

export default function DashboardPage({
  stats,
  loading,
  error,
  onRefresh,
  onNavigate,
  onOpenDocument,
  onOpenConversation,
}) {
  const totals = stats?.totals;
  const byStatus = stats?.documents_by_status || {};
  const maxStatus = Math.max(1, ...Object.values(byStatus));

  return (
    <div className="page">
      <PageHeader
        eyebrow="Workspace overview"
        title="Knowledge operations"
        description="Monitor ingestion, the retrieval index and the latest activity across your document corpus."
        actions={
          <>
            <button type="button" className="button button-ghost" onClick={onRefresh} disabled={loading}>
              {loading ? <Spinner size={15} /> : <Icon name="refresh" size={15} />}
              Refresh
            </button>
            <button type="button" className="button button-primary" onClick={() => onNavigate("documents")}>
              <Icon name="upload" size={15} />
              Upload documents
            </button>
          </>
        }
      />

      {error ? (
        <div className="panel panel-error">
          <Icon name="alert" size={17} />
          <div>
            <strong>Could not load workspace statistics</strong>
            <p>{error}</p>
          </div>
          <button type="button" className="button button-small" onClick={onRefresh}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="metric-grid">
        <MetricCard
          icon="file"
          label="Documents"
          value={loading && !totals ? "—" : totals?.documents ?? 0}
          hint={totals ? `${totals.documents_completed} processed · ${totals.documents_failed} failed` : ""}
        />
        <MetricCard
          icon="database"
          label="Indexed chunks"
          value={loading && !totals ? "—" : totals?.chunks ?? 0}
          hint={stats?.index ? `${stats.index.backend.toUpperCase()} · ${stats.index.dimension} dimensions` : ""}
          tone="accent"
        />
        <MetricCard
          icon="chat"
          label="Conversations"
          value={loading && !totals ? "—" : totals?.conversations ?? 0}
          hint={totals ? pluralize(totals.messages, "message") : ""}
        />
        <MetricCard
          icon="layers"
          label="Original files"
          value={loading && !totals ? "—" : formatBytes(totals?.storage_bytes ?? 0)}
          hint="Stored outside the database"
        />
      </div>

      {stats?.index?.needs_rebuild ? (
        <div className="panel panel-warning">
          <Icon name="alert" size={18} />
          <div>
            <strong>The search index needs to be rebuilt</strong>
            <p>
              The configured embedding model or dimension changed since the index was written.
              Rebuild it from the stored chunks before asking questions.
            </p>
          </div>
          <button type="button" className="button button-small" onClick={() => onNavigate("settings")}>
            Open index tools
          </button>
        </div>
      ) : null}

      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Processing pipeline</h2>
              <p>Current document status distribution.</p>
            </div>
            <button type="button" className="text-button" onClick={() => onNavigate("documents")}>
              Document library <Icon name="chevronRight" size={14} />
            </button>
          </div>

          {Object.keys(byStatus).length === 0 ? (
            <EmptyState
              icon="file"
              title="No documents yet"
              description="Upload PDF, TXT or Markdown files to build your knowledge base."
              action={
                <button type="button" className="button button-small button-primary" onClick={() => onNavigate("documents")}>
                  Upload documents
                </button>
              }
            />
          ) : (
            <div className="status-bars">
              {PIPELINE_ORDER.filter((status) => byStatus[status]).map((status) => (
                <div className="status-bar-row" key={status}>
                  <span className="status-bar-label">{PIPELINE_LABELS[status] || status}</span>
                  <div className="status-bar-track">
                    <span
                      className={`status-bar-fill bar-${status}`}
                      style={{ width: `${Math.round((byStatus[status] / maxStatus) * 100)}%` }}
                    />
                  </div>
                  <span className="status-bar-count">{byStatus[status]}</span>
                </div>
              ))}
            </div>
          )}

          <div className="index-card">
            <div className="index-card-head">
              <Icon name="database" size={16} />
              <strong>Retrieval index</strong>
              <span className="index-healthy">
                <span className="connection-dot online" />
                {stats?.index?.needs_rebuild ? "Needs rebuild" : "Healthy"}
              </span>
            </div>
            <dl className="index-facts">
              <div>
                <dt>Backend</dt>
                <dd>{stats?.index?.backend?.toUpperCase() || "—"}</dd>
              </div>
              <div>
                <dt>Embeddings</dt>
                <dd>{stats?.index?.embedding_provider || "—"}</dd>
              </div>
              <div>
                <dt>Chunks</dt>
                <dd>{stats?.index?.chunk_count ?? 0}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{formatDate(stats?.index?.updated_at, true)}</dd>
              </div>
            </dl>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Recent documents</h2>
              <p>Latest uploads and their ingestion status.</p>
            </div>
          </div>
          {stats?.recent_documents?.length ? (
            <ul className="recent-list">
              {stats.recent_documents.map((document) => (
                <li key={document.id}>
                  <button type="button" className="recent-row" onClick={() => onOpenDocument(document.id)}>
                    <span className="recent-icon">
                      <Icon name="file" size={16} />
                    </span>
                    <span className="recent-main">
                      <strong title={document.filename}>{document.filename}</strong>
                      <span>
                        {document.file_type.toUpperCase()} · {formatRelative(document.created_at)}
                      </span>
                    </span>
                    <StatusBadge
                      status={document.status}
                      label={isProcessingStatus(document.status) ? "Processing" : undefined}
                    />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon="file" title="No documents yet" description="Your uploads will appear here." />
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Recent conversations</h2>
              <p>Continue a previous investigation.</p>
            </div>
            <button type="button" className="text-button" onClick={() => onNavigate("chat")}>
              Open chat <Icon name="chevronRight" size={14} />
            </button>
          </div>
          {stats?.recent_conversations?.length ? (
            <ul className="recent-list">
              {stats.recent_conversations.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    className="recent-row"
                    onClick={() => onOpenConversation(conversation.id)}
                  >
                    <span className="recent-icon recent-icon-chat">
                      <Icon name="chat" size={16} />
                    </span>
                    <span className="recent-main">
                      <strong title={conversation.title}>{conversation.title}</strong>
                      <span>
                        {conversation.message_count} messages · {formatRelative(conversation.updated_at)}
                      </span>
                    </span>
                    <Icon name="chevronRight" size={15} className="recent-chevron" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon="chat"
              title="No conversations yet"
              description="Ask a question grounded in your uploaded policies."
              action={
                <button type="button" className="button button-small button-primary" onClick={() => onNavigate("chat")}>
                  Start a conversation
                </button>
              }
            />
          )}
        </section>

        <section className="panel panel-quick">
          <div className="panel-head">
            <div>
              <h2>Quick actions</h2>
              <p>Common knowledge operations.</p>
            </div>
          </div>
          <div className="quick-actions">
            <button type="button" onClick={() => onNavigate("documents")}>
              <Icon name="upload" size={18} />
              <strong>Upload documents</strong>
              <span>PDF, TXT or Markdown</span>
            </button>
            <button type="button" onClick={() => onNavigate("chat")}>
              <Icon name="chat" size={18} />
              <strong>Ask the corpus</strong>
              <span>Grounded answers with citations</span>
            </button>
            <button type="button" onClick={() => onNavigate("batch")}>
              <Icon name="layers" size={18} />
              <strong>Batch questions</strong>
              <span>CSV in, cited CSV out</span>
            </button>
            <button type="button" onClick={() => onNavigate("settings")}>
              <Icon name="settings" size={18} />
              <strong>System settings</strong>
              <span>Providers, retrieval, index</span>
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
