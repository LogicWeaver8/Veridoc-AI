import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import Icon from "../components/Icons.jsx";
import { Alert, Spinner, StatusBadge } from "../components/ui.jsx";
import { formatBytes, formatDate, isProcessingStatus } from "../utils/format.js";

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function DocumentDetailDrawer({ documentId, onClose, onChanged, onDeleted }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showVersionForm, setShowVersionForm] = useState(false);
  const [versionFile, setVersionFile] = useState(null);
  const [effectiveFrom, setEffectiveFrom] = useState(today());
  const [versionLabel, setVersionLabel] = useState("");
  const [supersedes, setSupersedes] = useState("");
  const [savingVersion, setSavingVersion] = useState(false);
  const [versionError, setVersionError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const fileRef = useRef(null);
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    setError("");
    api
      .getDocument(documentId)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        setSupersedes(data.active_version?.id || "");
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const processing = detail ? isProcessingStatus(detail.status) : false;

  useEffect(() => {
    if (!processing) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const data = await api.getDocument(documentId);
        setDetail(data);
        if (data.status === "completed" || data.status === "failed") {
          onChangedRef.current?.();
        }
      } catch {
        // Keep the last known snapshot; the user can retry manually.
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [processing, documentId]);

  async function refresh() {
    const data = await api.getDocument(documentId);
    setDetail(data);
  }

  async function handleVersionSubmit(event) {
    event.preventDefault();
    if (!versionFile) {
      setVersionError("Choose a file for the new version.");
      return;
    }
    setSavingVersion(true);
    setVersionError("");
    try {
      await api.addVersion(documentId, versionFile, {
        effective_from: effectiveFrom || undefined,
        version_label: versionLabel.trim() || undefined,
        supersedes_version_id: supersedes || undefined,
      });
      setShowVersionForm(false);
      setVersionFile(null);
      setVersionLabel("");
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
      onChanged?.();
    } catch (requestError) {
      setVersionError(requestError.message);
    } finally {
      setSavingVersion(false);
    }
  }

  async function handleDelete() {
    if (!detail) return;
    const confirmed = window.confirm(
      `Delete "${detail.filename}" and all of its versions, chunks and index entries?`,
    );
    if (!confirmed) return;
    setDeleting(true);
    try {
      await api.deleteDocument(documentId);
      await onDeleted?.();
    } catch (requestError) {
      setError(requestError.message);
      setDeleting(false);
    }
  }

  return (
    <div className="drawer-layer" role="dialog" aria-label={`Document details for ${detail?.filename || "document"}`}>
      <button type="button" className="drawer-scrim" onClick={onClose} aria-label="Close document details" />
      <aside className="drawer">
        <div className="drawer-head">
          <div className="drawer-title">
            <span className="eyebrow">Document details</span>
            <h2>{detail?.filename || "Loading…"}</h2>
            {detail ? (
              <div className="drawer-badges">
                <StatusBadge status={detail.status} />
                <span className="type-chip">{detail.file_type.toUpperCase()}</span>
                <span className="muted-text">{formatBytes(detail.size_bytes)}</span>
              </div>
            ) : null}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <Icon name="close" size={18} />
          </button>
        </div>

        <div className="drawer-body">
          {loading ? (
            <div className="drawer-loading">
              <Spinner size={20} />
              Loading document…
            </div>
          ) : null}

          {error ? (
            <Alert tone="danger" title="Could not load the document">
              {error}
            </Alert>
          ) : null}

          {detail ? (
            <>
              {detail.status === "failed" ? (
                <Alert tone="danger" title="Processing failed">
                  {detail.error_message || "The document could not be processed. Check the server logs."}
                </Alert>
              ) : null}

              {processing ? (
                <div className="processing-box">
                  <Spinner size={17} />
                  <div>
                    <strong>Processing in progress</strong>
                    <span>Current stage: {detail.status}. This panel refreshes automatically.</span>
                  </div>
                </div>
              ) : null}

              {detail.warnings?.length ? (
                <Alert tone="info" title="Extraction warnings">
                  <ul className="compact-list">
                    {detail.warnings.map((warning, index) => (
                      <li key={index}>{warning}</li>
                    ))}
                  </ul>
                </Alert>
              ) : null}

              <section className="detail-section">
                <h3>Metadata</h3>
                <dl className="detail-grid">
                  <div>
                    <dt>Document ID</dt>
                    <dd className="mono wrap">{detail.id}</dd>
                  </div>
                  <div>
                    <dt>Uploaded</dt>
                    <dd>{formatDate(detail.created_at, true)}</dd>
                  </div>
                  <div>
                    <dt>Pages</dt>
                    <dd>{detail.page_count}</dd>
                  </div>
                  <div>
                    <dt>Indexed chunks</dt>
                    <dd>{detail.chunk_count}</dd>
                  </div>
                  <div>
                    <dt>Versions</dt>
                    <dd>{detail.version_count}</dd>
                  </div>
                  <div>
                    <dt>SHA-256</dt>
                    <dd className="mono wrap">{detail.file_hash}</dd>
                  </div>
                </dl>
              </section>

              <section className="detail-section">
                <div className="detail-section-head">
                  <h3>Versions</h3>
                  <button
                    type="button"
                    className="button button-small button-ghost"
                    onClick={() => {
                      setShowVersionForm((value) => !value);
                      setVersionError("");
                    }}
                  >
                    <Icon name="plus" size={14} />
                    New version
                  </button>
                </div>

                {showVersionForm ? (
                  <form className="version-form" onSubmit={handleVersionSubmit}>
                    <label className="field">
                      <span>Version file</span>
                      <input
                        ref={fileRef}
                        type="file"
                        accept=".pdf,.txt,.md,.markdown"
                        onChange={(event) => setVersionFile(event.target.files?.[0] || null)}
                      />
                    </label>
                    <div className="field-row">
                      <label className="field">
                        <span>Effective from</span>
                        <input
                          type="date"
                          value={effectiveFrom}
                          onChange={(event) => setEffectiveFrom(event.target.value)}
                          required
                        />
                      </label>
                      <label className="field">
                        <span>Version label</span>
                        <input
                          type="text"
                          placeholder="Auto (e.g. 2026)"
                          value={versionLabel}
                          maxLength={64}
                          onChange={(event) => setVersionLabel(event.target.value)}
                        />
                      </label>
                    </div>
                    <label className="field">
                      <span>Supersedes</span>
                      <select value={supersedes} onChange={(event) => setSupersedes(event.target.value)}>
                        <option value="">Not specified</option>
                        {detail.versions.map((version) => (
                          <option key={version.id} value={version.id}>
                            v{version.version_label} · effective {version.effective_from}
                          </option>
                        ))}
                      </select>
                    </label>
                    {versionError ? <div className="form-error">{versionError}</div> : null}
                    <div className="form-actions">
                      <button type="button" className="button button-ghost button-small" onClick={() => setShowVersionForm(false)}>
                        Cancel
                      </button>
                      <button type="submit" className="button button-primary button-small" disabled={savingVersion}>
                        {savingVersion ? <Spinner size={14} /> : <Icon name="upload" size={14} />}
                        Upload version
                      </button>
                    </div>
                  </form>
                ) : null}

                <ul className="version-list">
                  {detail.versions.map((version) => (
                    <li key={version.id} className={version.id === detail.active_version?.id ? "version-current" : ""}>
                      <div className="version-main">
                        <strong>v{version.version_label}</strong>
                        <StatusBadge status={version.status} />
                        {version.id === detail.active_version?.id ? <span className="current-chip">Current</span> : null}
                      </div>
                      <div className="version-meta">
                        <span>#{version.version_number}</span>
                        <span>Effective {version.effective_from}</span>
                        {version.effective_to ? <span>Until {version.effective_to}</span> : <span>Open-ended</span>}
                        <span>{version.page_count} pages · {version.chunk_count} chunks</span>
                      </div>
                      {version.error_message ? <p className="version-error">{version.error_message}</p> : null}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="detail-section danger-zone">
                <h3>Danger zone</h3>
                <p>Removing this document deletes every version, chunk and index entry. Conversations remain, but their citations will reference a deleted source.</p>
                <button type="button" className="button button-danger button-small" onClick={handleDelete} disabled={deleting}>
                  {deleting ? <Spinner size={14} /> : <Icon name="trash" size={14} />}
                  Delete document
                </button>
              </section>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
