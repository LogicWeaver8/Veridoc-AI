import { confidenceTone, statusLabel, statusTone } from "../utils/format.js";
import Icon from "./Icons.jsx";

export function StatusBadge({ status, label, tone }) {
  const resolvedTone = tone || statusTone(status);
  return (
    <span className={`status-badge status-${resolvedTone}`}>
      <span className="status-dot" aria-hidden="true" />
      {label || statusLabel(status)}
    </span>
  );
}

export function ConfidenceMeter({ confidence, status }) {
  const tone = confidenceTone(confidence);
  const value = Math.max(0, Math.min(100, confidence ?? 0));
  return (
    <div className={`confidence confidence-${tone}`}>
      <div className="confidence-head">
        <span className="confidence-label">Evidence confidence</span>
        <span className="confidence-value">
          {status ? statusLabel(status) : ""}
          {status ? " · " : ""}
          {value}%
        </span>
      </div>
      <div
        className="confidence-track"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Answer confidence"
      >
        <span className="confidence-fill" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export function Spinner({ size = 16, label = "Loading" }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-label={label} />;
}

export function EmptyState({ icon = "book", title, description, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon name={icon} size={24} />
      </div>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action}
    </div>
  );
}

export function Alert({ tone = "danger", title, children, onDismiss }) {
  return (
    <div className={`alert alert-${tone}`} role="alert">
      <Icon name={tone === "success" ? "check" : tone === "info" ? "info" : "alert"} size={17} />
      <div className="alert-body">
        {title ? <strong>{title}</strong> : null}
        {children ? <div>{children}</div> : null}
      </div>
      {onDismiss ? (
        <button type="button" className="icon-button" onClick={onDismiss} aria-label="Dismiss">
          <Icon name="close" size={15} />
        </button>
      ) : null}
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function MetricCard({ icon, label, value, hint, tone = "default" }) {
  return (
    <div className={`metric-card metric-${tone}`}>
      <div className="metric-icon">
        <Icon name={icon} size={19} />
      </div>
      <div>
        <span className="metric-label">{label}</span>
        <strong className="metric-value">{value}</strong>
        {hint ? <span className="metric-hint">{hint}</span> : null}
      </div>
    </div>
  );
}

export function formatTermList(question) {
  if (!question) return [];
  const stop = new Set([
    "what", "is", "are", "the", "a", "an", "of", "for", "in", "on", "to", "and",
    "does", "do", "how", "many", "company", "policy", "with", "was", "were", "can",
    "i", "my", "our", "we", "you", "about", "under", "per", "there", "this",
  ]);
  return Array.from(
    new Set(
      question
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, " ")
        .split(/\s+/)
        .filter((word) => word.length > 2 && !stop.has(word)),
    ),
  );
}

export function HighlightedExcerpt({ text, question }) {
  const terms = formatTermList(question);
  if (!terms.length) return <>{text}</>;
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  const parts = String(text).split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <mark key={index} className="excerpt-mark">
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
