import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import ChatMessage from "../components/ChatMessage.jsx";
import Icon from "../components/Icons.jsx";
import { Alert, Spinner } from "../components/ui.jsx";
import { formatRelative } from "../utils/format.js";

const SUGGESTIONS = [
  {
    icon: "clock",
    label: "Leave policy",
    question: "What is the company's annual leave policy?",
  },
  {
    icon: "users",
    label: "Sick leave",
    question: "How many sick leave days are employees entitled to?",
  },
  {
    icon: "shield",
    label: "Remote work",
    question: "What is the work-from-home policy?",
  },
  {
    icon: "file",
    label: "Reimbursement",
    question: "What is the process for reimbursing business expenses?",
  },
  {
    icon: "book",
    label: "Attendance",
    question: "What are the employee attendance rules?",
  },
];

export default function ChatPage({
  conversationId,
  conversationTitle,
  onConversationChange,
  onConversationsChanged,
  onOpenSource,
  stats,
  session,
}) {
  const [messages, setMessages] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    setError("");
    if (!conversationId) {
      setMessages([]);
      return;
    }

    let cancelled = false;
    setLoadingHistory(true);
    api
      .getConversation(conversationId)
      .then((conversation) => {
        if (cancelled) return;
        setMessages(conversation.messages || []);
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message);
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    const element = scrollRef.current;
    if (element && (messages.length > 0 || sending)) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, sending]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [input]);

  async function submitQuestion(text) {
    const question = text.trim();
    if (!question || sending) return;

    const localId = `local-${Date.now()}`;
    const optimistic = {
      id: localId,
      role: "user",
      content: question,
      created_at: new Date().toISOString(),
    };

    setMessages((previous) => [...previous, optimistic]);
    setInput("");
    setSending(true);
    setError("");

    try {
      const result = await api.ask({
        question,
        conversation_id: conversationId || null,
      });

      const userMessage = {
        id: result.user_message_id,
        role: "user",
        content: question,
        created_at: result.created_at,
      };
      const assistantMessage = {
        id: result.assistant_message_id,
        role: "assistant",
        content: result.answer,
        answer_status: result.answer_status,
        confidence: result.confidence,
        citations: result.citations || [],
        message_metadata: {
          notes: result.notes || [],
          provider: result.provider,
          model: result.model,
          requires_clarification: result.requires_clarification,
          evidence: result.evidence || [],
        },
        created_at: result.created_at,
      };

      setMessages((previous) => [
        ...previous.filter((message) => message.id !== localId),
        userMessage,
        assistantMessage,
      ]);
      onConversationChange(result.conversation_id);
      onConversationsChanged();
    } catch (requestError) {
      setMessages((previous) => previous.filter((message) => message.id !== localId));
      setError(requestError.message);
      setInput(question);
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    submitQuestion(input);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submitQuestion(input);
    }
  }

  const isWelcome = messages.length === 0 && !loadingHistory && !sending;
  const completedDocuments = stats?.totals?.documents_completed ?? 0;
  const indexedChunks = stats?.totals?.chunks ?? 0;

  let precedingQuestion = "";

  return (
    <section className="chat-page">
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-column">
          {isWelcome ? (
            <div className="welcome">
              <div className="welcome-mark">
                <span>V</span>
                <div className="welcome-pulse" aria-hidden="true" />
              </div>
              <span className="eyebrow">Evidence-grounded knowledge assistant</span>
              <h1>Ask your organisation&apos;s documents</h1>
              <p className="welcome-copy">
                Every answer is retrieved from indexed policy documents and checked against the
                evidence before it is shown. If the documents do not cover a question, VeriDox says
                so instead of guessing.
              </p>

              <div className="welcome-stats">
                <span>
                  <Icon name="file" size={14} />
                  {completedDocuments} processed documents
                </span>
                <span>
                  <Icon name="database" size={14} />
                  {indexedChunks} indexed chunks
                </span>
                <span>
                  <Icon name="shield" size={14} />
                  Citations on every grounded claim
                </span>
              </div>

              <div className="suggestion-grid">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion.label}
                    type="button"
                    className="suggestion-card"
                    onClick={() => submitQuestion(suggestion.question)}
                  >
                    <span className="suggestion-icon">
                      <Icon name={suggestion.icon} size={17} />
                    </span>
                    <span>
                      <strong>{suggestion.label}</strong>
                      <span>{suggestion.question}</span>
                    </span>
                    <Icon name="chevronRight" size={15} className="suggestion-chevron" />
                  </button>
                ))}
              </div>

              <p className="welcome-note">
                Signed in as {session?.email || "local user"}. Suggested questions are examples —
                answers come only from your uploaded documents.
              </p>
            </div>
          ) : null}

          {loadingHistory ? (
            <div className="history-loading">
              <Spinner size={18} />
              Loading conversation…
            </div>
          ) : null}

          {!isWelcome && messages.length > 0 ? (
            <div className="conversation-header">
              <span>
                <Icon name="chat" size={14} />
                {conversationTitle || "Conversation"}
              </span>
              <span className="conversation-updated">
                {messages.length > 0 ? formatRelative(messages[messages.length - 1].created_at) : ""}
              </span>
            </div>
          ) : null}

          <div className="message-list">
            {messages.map((message) => {
              if (message.role === "user") precedingQuestion = message.content;
              return (
                <ChatMessage
                  key={message.id}
                  message={message}
                  question={message.role === "user" ? message.content : precedingQuestion}
                  onOpenSource={onOpenSource}
                />
              );
            })}

            {sending ? (
              <div className="message-row message-assistant">
                <div className="assistant-avatar" aria-hidden="true">
                  V
                </div>
                <div className="assistant-card assistant-thinking">
                  <div className="typing-dots" aria-label="Generating answer">
                    <span />
                    <span />
                    <span />
                  </div>
                  <p>Searching documents and verifying evidence…</p>
                </div>
              </div>
            ) : null}
          </div>

          {error ? (
            <div className="chat-error">
              <Alert tone="danger" title="The request could not be completed" onDismiss={() => setError("")}>
                {error}
              </Alert>
            </div>
          ) : null}
        </div>
      </div>

      <div className="composer-wrap">
        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder={
              conversationId
                ? "Ask a follow-up question about your documents…"
                : "Ask a question about your organisation's policies…"
            }
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={sending}
            maxLength={4000}
            aria-label="Question"
          />
          <button
            type="submit"
            className="send-button"
            disabled={sending || !input.trim()}
            aria-label="Send question"
          >
            <Icon name="send" size={17} />
          </button>
        </form>
        <div className="composer-hint">
          <span>Enter to send · Shift + Enter for a new line</span>
          <span className="composer-guard">
            <Icon name="shield" size={12} />
            Answers restricted to indexed documents
          </span>
        </div>
      </div>
    </section>
  );
}
