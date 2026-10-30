import Icon from "./Icons.jsx";
import { CitationCard } from "./Citations.jsx";
import { ConfidenceMeter, StatusBadge } from "./ui.jsx";
import { formatTime } from "../utils/format.js";

export default function ChatMessage({ message, question, onOpenSource }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="message-row message-user">
        <div className="user-bubble">{message.content}</div>
        <span className="message-time">{formatTime(message.created_at)}</span>
      </div>
    );
  }

  const metadata = message.message_metadata || {};
  const isMock = metadata.provider === "mock";
  const notes = metadata.notes || [];
  const citations = message.citations || [];

  return (
    <div className="message-row message-assistant">
      <div className="assistant-avatar" aria-hidden="true">
        V
      </div>
      <div className="assistant-card">
        <div className="assistant-head">
          <div className="assistant-identity">
            <strong>VeriDox AI</strong>
            {message.answer_status ? <StatusBadge status={message.answer_status} /> : null}
            {metadata.requires_clarification ? (
              <span className="status-badge status-warning">
                <Icon name="alert" size={12} />
                Clarification needed
              </span>
            ) : null}
          </div>
          <span className="message-time">{formatTime(message.created_at)}</span>
        </div>

        {message.confidence != null && message.answer_status ? (
          <ConfidenceMeter confidence={message.confidence} status={message.answer_status} />
        ) : null}

        {isMock ? (
          <div className="mock-banner" title="LLM_PROVIDER=mock: answers are extractive, not model-generated">
            <Icon name="info" size={14} />
            Extractive answer from indexed evidence — no generation model is configured.
          </div>
        ) : null}

        <div className="assistant-text">{message.content}</div>

        {citations.length > 0 ? (
          <div className="citations">
            <div className="citations-head">
              <Icon name="quote" size={14} />
              Sources ({citations.length})
            </div>
            <div className="citation-list">
              {citations.map((citation, index) => (
                <CitationCard
                  key={`${citation.chunk_id}-${index}`}
                  citation={citation}
                  index={index + 1}
                  question={question}
                  onOpenSource={(citation) => onOpenSource(citation, question)}
                />
              ))}
            </div>
          </div>
        ) : (
          <div className="no-evidence-note">
            <Icon name="shield" size={14} />
            No supporting evidence was found, so no citation is shown.
          </div>
        )}

        <div className="assistant-footer">
          <span className={`provider-chip ${isMock ? "provider-mock" : "provider-live"}`}>
            {metadata.provider || "unknown"} · {metadata.model || "model n/a"}
          </span>
          {notes.length > 0 ? (
            <details className="notes">
              <summary>Retrieval notes ({notes.length})</summary>
              <ul>
                {notes.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      </div>
    </div>
  );
}
