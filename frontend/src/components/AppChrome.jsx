import Icon from "./Icons.jsx";
import { pluralize } from "../utils/format.js";

export function TopBar({ onOpenMenu, apiOnline, viewerAvailable, viewerOpen, onToggleViewer }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button type="button" className="icon-button menu-button" onClick={onOpenMenu} aria-label="Open menu">
          <Icon name="menu" size={19} />
        </button>
        <div className="brand-mark">V</div>
        <div className="topbar-brand">
          <strong>VeriDox AI</strong>
          <span className="grounding-chip">
            <Icon name="shield" size={12} />
            Grounding assistant
          </span>
        </div>
      </div>

      <div className="topbar-right">
        <span className={`api-pill ${apiOnline ? "api-online" : "api-offline"}`}>
          <span className="connection-dot" />
          {apiOnline ? "API online" : "API offline"}
        </span>
        <button
          type="button"
          className={`button button-ghost ${viewerOpen ? "button-ghost-active" : ""}`}
          onClick={onToggleViewer}
          disabled={!viewerAvailable && !viewerOpen}
          title={
            viewerAvailable || viewerOpen
              ? "Show or hide the source document viewer"
              : "Ask a question with citations to inspect a source"
          }
        >
          <Icon name="book" size={16} />
          {viewerOpen ? "Hide sources" : "Source viewer"}
        </button>
      </div>
    </header>
  );
}

const PILLS = [
  { key: "processed", label: "Processed", tone: "success", icon: "check" },
  { key: "processing", label: "Processing", tone: "info", icon: "refresh" },
  { key: "pending", label: "Pending", tone: "neutral", icon: "clock" },
  { key: "failed", label: "Failed", tone: "danger", icon: "alert" },
];

export function IngestionBar({ counts, onOpenDocuments }) {
  const safe = counts || {};
  return (
    <div className="ingestion-bar">
      <span className="ingestion-title">
        <Icon name="database" size={15} />
        Ingestion engine
      </span>
      <div className="ingestion-pills">
        {PILLS.map((pill) => (
          <button
            key={pill.key}
            type="button"
            className={`ingestion-pill pill-${pill.tone}`}
            onClick={onOpenDocuments}
            title={`Open the document library`}
          >
            <Icon name={pill.icon} size={13} />
            {safe[pill.key] || 0} {pill.label}
          </button>
        ))}
      </div>
      <span className="ingestion-total">
        {pluralize((safe.processed || 0) + (safe.processing || 0) + (safe.pending || 0), "document")}
      </span>
    </div>
  );
}
