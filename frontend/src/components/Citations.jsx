import { useState } from "react";
import Icon from "./Icons.jsx";
import { HighlightedExcerpt } from "./ui.jsx";

export function CitationCard({ citation, index, question, onOpenSource }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="citation-card">
      <button
        type="button"
        className="citation-summary"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span className="citation-index">{index}</span>
        <span className="citation-main">
          <span className="citation-doc">
            <Icon name="file" size={14} />
            {citation.document_name}
          </span>
          <span className="citation-meta">
            <span>Version {citation.version_label || "n/a"}</span>
            <span>{citation.page_number ? `Page ${citation.page_number}` : "No page number"}</span>
            {citation.section ? <span>{citation.section}</span> : null}
          </span>
        </span>
        <Icon name={expanded ? "chevronDown" : "chevronRight"} size={16} className="citation-chevron" />
      </button>

      {expanded ? (
        <div className="citation-body">
          <p className="citation-excerpt">
            <HighlightedExcerpt text={citation.excerpt} question={question} />
          </p>
          <div className="citation-actions">
            <span className="citation-id">Chunk {citation.chunk_id.slice(0, 8)}</span>
            <button type="button" className="button button-small button-ghost" onClick={() => onOpenSource(citation)}>
              <Icon name="eye" size={14} />
              Show source page
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function SourceViewer({ citation, question, onClose }) {
  if (!citation) return null;
  return (
    <div className="source-viewer" role="dialog" aria-label="Source document viewer">
      <div className="source-viewer-head">
        <div>
          <span className="eyebrow">Source viewer</span>
          <h2>{citation.document_name}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close source viewer">
          <Icon name="close" size={18} />
        </button>
      </div>

      <div className="source-meta">
        <div>
          <span>Version</span>
          <strong>{citation.version_label || "n/a"}</strong>
        </div>
        <div>
          <span>Page</span>
          <strong>{citation.page_number ?? "n/a"}</strong>
        </div>
        <div>
          <span>Section</span>
          <strong>{citation.section || "n/a"}</strong>
        </div>
      </div>

      <div className="source-page">
        <div className="source-page-head">
          <span>{citation.section || citation.document_name}</span>
          <span>{citation.page_number ? `Page ${citation.page_number}` : "Excerpt"}</span>
        </div>
        <p>
          <HighlightedExcerpt text={citation.excerpt} question={question} />
        </p>
      </div>

      <div className="source-note">
        <Icon name="info" size={14} />
        This is the indexed text excerpt used to ground the answer, not a rendered page image.
        Page and section values come from the ingestion pipeline.
      </div>

      <div className="source-foot">
        <span>Document ID</span>
        <code>{citation.document_id}</code>
      </div>
    </div>
  );
}
