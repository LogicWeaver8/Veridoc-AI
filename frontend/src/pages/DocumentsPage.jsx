import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import Icon from "../components/Icons.jsx";
import { Alert, EmptyState, PageHeader, Spinner, StatusBadge } from "../components/ui.jsx";
import DocumentDetailDrawer from "./DocumentDetailDrawer.jsx";
import { formatBytes, formatDate, isProcessingStatus } from "../utils/format.js";

const TYPE_OPTIONS = [
  { value: "", label: "All types" },
  { value: "pdf", label: "PDF" },
  { value: "txt", label: "TXT" },
  { value: "markdown", label: "Markdown" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "uploaded", label: "Queued" },
  { value: "extracting", label: "Extracting" },
  { value: "chunking", label: "Chunking" },
  { value: "embedding", label: "Embedding" },
  { value: "indexing", label: "Indexing" },
];

const ALLOWED_EXTENSIONS = [".pdf", ".txt", ".md", ".markdown"];

export default function DocumentsPage({ selectedDocumentId, onSelectDocument, onDataChanged }) {
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadNotice, setUploadNotice] = useState("");
  const [uploadErrors, setUploadErrors] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);
  const filtersRef = useRef({ search, typeFilter, statusFilter });

  filtersRef.current = { search, typeFilter, statusFilter };

  const load = useCallback(
    async ({ silent = false } = {}) => {
      const filters = filtersRef.current;
      if (!silent) setLoading(true);
      try {
        const data = await api.listDocuments({
          search: filters.search || undefined,
          file_type: filters.typeFilter || undefined,
          status: filters.statusFilter || undefined,
          limit: 100,
        });
        setDocuments(data.items);
        setTotal(data.total);
        setError("");
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    load();
  }, [load, search, typeFilter, statusFilter]);

  const hasProcessing = documents.some((document) => isProcessingStatus(document.status));

  useEffect(() => {
    if (!hasProcessing) return undefined;
    const timer = window.setInterval(() => {
      load({ silent: true });
      onDataChanged?.();
    }, 3500);
    return () => window.clearInterval(timer);
  }, [hasProcessing, load, onDataChanged]);

  async function handleFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length || uploading) return;

    const invalid = files.filter(
      (file) => !ALLOWED_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension)),
    );
    if (invalid.length) {
      setUploadErrors(
        invalid.map((file) => ({
          filename: file.name,
          message: "Unsupported file type. Upload PDF, TXT or Markdown files.",
        })),
      );
      return;
    }

    setUploading(true);
    setUploadNotice("");
    setUploadErrors([]);

    try {
      if (files.length === 1) {
        const document = await api.uploadDocument(files[0]);
        setUploadNotice(`"${document.filename}" uploaded and queued for processing.`);
      } else {
        const result = await api.uploadDocuments(files);
        const uploadedCount = result.uploaded.length;
        const duplicateCount = result.duplicates.length;
        setUploadNotice(
          `${uploadedCount} file(s) uploaded${duplicateCount ? `, ${duplicateCount} duplicate(s) skipped` : ""}.`,
        );
        setUploadErrors(
          [...result.duplicates, ...result.errors].map((item) => ({
            filename: item.filename,
            message: item.message,
          })),
        );
        if (result.uploaded.length) onSelectDocument(result.uploaded[0].id);
      }
      await load({ silent: true });
      onDataChanged?.();
    } catch (uploadError) {
      setUploadErrors([{ filename: files[0].name, message: uploadError.message }]);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragActive(false);
    handleFiles(event.dataTransfer.files);
  }

  async function handleDelete(document) {
    const confirmed = window.confirm(
      `Delete "${document.filename}" and all of its versions, chunks and index entries? This cannot be undone.`,
    );
    if (!confirmed) return;
    try {
      await api.deleteDocument(document.id);
      if (selectedDocumentId === document.id) onSelectDocument(null);
      await load({ silent: true });
      onDataChanged?.();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  function resetFilters() {
    setSearchInput("");
    setSearch("");
    setTypeFilter("");
    setStatusFilter("");
  }

  const filtersActive = Boolean(search || typeFilter || statusFilter);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Document management"
        title="Document library"
        description={`Upload organisational policies and inspect versions, processing status and indexed metadata.${total ? ` ${total} document(s) in the workspace.` : ""}`}
        actions={
          <button
            type="button"
            className="button button-primary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? <Spinner size={15} /> : <Icon name="upload" size={15} />}
            Upload documents
          </button>
        }
      />

      <input
        ref={fileInputRef}
        type="file"
        className="visually-hidden"
        accept={ALLOWED_EXTENSIONS.join(",")}
        multiple
        onChange={(event) => handleFiles(event.target.files)}
      />

      <div
        className={`dropzone ${dragActive ? "dropzone-active" : ""} ${uploading ? "dropzone-busy" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") fileInputRef.current?.click();
        }}
      >
        <div className="dropzone-icon">
          {uploading ? <Spinner size={22} /> : <Icon name="upload" size={22} />}
        </div>
        <div>
          <strong>{uploading ? "Uploading and queuing documents…" : "Drop files here or click to browse"}</strong>
          <span>PDF, TXT and Markdown · multiple files supported · duplicates are detected by SHA-256</span>
        </div>
      </div>

      {uploadNotice ? (
        <Alert tone="success" onDismiss={() => setUploadNotice("")}>
          {uploadNotice}
        </Alert>
      ) : null}

      {uploadErrors.length ? (
        <Alert tone="danger" title="Some files could not be added" onDismiss={() => setUploadErrors([])}>
          <ul className="compact-list">
            {uploadErrors.map((item, index) => (
              <li key={index}>
                <strong>{item.filename}:</strong> {item.message}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <div className="panel documents-panel">
        <div className="documents-toolbar">
          <form
            className="search-form"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchInput.trim());
            }}
          >
            <Icon name="search" size={16} />
            <input
              type="search"
              placeholder="Search by filename…"
              value={searchInput}
              onChange={(event) => {
                setSearchInput(event.target.value);
                if (!event.target.value) setSearch("");
              }}
              aria-label="Search documents by filename"
            />
          </form>

          <div className="toolbar-filters">
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} aria-label="Filter by file type">
              {TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              aria-label="Filter by status"
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button type="button" className="button button-ghost button-small" onClick={() => load()}>
              <Icon name="refresh" size={14} />
              Refresh
            </button>
            {filtersActive ? (
              <button type="button" className="text-button" onClick={resetFilters}>
                Clear
              </button>
            ) : null}
          </div>
        </div>

        {error ? <Alert tone="danger" title="Could not load documents">{error}</Alert> : null}

        {loading && documents.length === 0 ? (
          <div className="documents-loading">
            <Spinner size={20} />
            Loading documents…
          </div>
        ) : null}

        {!loading && documents.length === 0 ? (
          filtersActive ? (
            <EmptyState icon="search" title="No documents match these filters" description="Try a different search term or clear the filters." action={<button type="button" className="button button-small" onClick={resetFilters}>Clear filters</button>} />
          ) : (
            <EmptyState
              icon="file"
              title="Your library is empty"
              description="Upload employee handbooks, HR policies, SOPs or technical documentation to start grounding answers."
              action={
                <button type="button" className="button button-small button-primary" onClick={() => fileInputRef.current?.click()}>
                  Upload your first document
                </button>
              }
            />
          )
        ) : null}

        {documents.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Status</th>
                  <th>Versions</th>
                  <th>Pages / chunks</th>
                  <th>Size</th>
                  <th>Uploaded</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => (
                  <tr
                    key={document.id}
                    className={selectedDocumentId === document.id ? "row-selected" : ""}
                    onClick={() => onSelectDocument(document.id)}
                  >
                    <td>
                      <button type="button" className="document-cell" onClick={() => onSelectDocument(document.id)}>
                        <span className={`file-icon file-${document.file_type}`}>
                          {document.file_type === "pdf" ? "PDF" : document.file_type === "markdown" ? "MD" : "TXT"}
                        </span>
                        <span className="document-cell-text">
                          <strong title={document.filename}>{document.filename}</strong>
                          <span>{document.active_version ? `Active v${document.active_version.version_label}` : "No active version"}</span>
                        </span>
                      </button>
                    </td>
                    <td>
                      <StatusBadge
                        status={document.status}
                        label={isProcessingStatus(document.status) ? "Processing" : undefined}
                      />
                      {document.error_message ? (
                        <span className="row-error" title={document.error_message}>
                          <Icon name="alert" size={13} />
                          Failed
                        </span>
                      ) : null}
                    </td>
                    <td>{document.version_count}</td>
                    <td>
                      {document.page_count} / {document.chunk_count}
                    </td>
                    <td>{formatBytes(document.size_bytes)}</td>
                    <td>{formatDate(document.created_at, true)}</td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="icon-button"
                          title="Open details"
                          aria-label={`Open details for ${document.filename}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            onSelectDocument(document.id);
                          }}
                        >
                          <Icon name="eye" size={15} />
                        </button>
                        <button
                          type="button"
                          className="icon-button icon-danger"
                          title="Delete document"
                          aria-label={`Delete ${document.filename}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleDelete(document);
                          }}
                        >
                          <Icon name="trash" size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {selectedDocumentId ? (
        <DocumentDetailDrawer
          documentId={selectedDocumentId}
          onClose={() => onSelectDocument(null)}
          onChanged={async () => {
            await load({ silent: true });
            onDataChanged?.();
          }}
          onDeleted={async () => {
            onSelectDocument(null);
            await load({ silent: true });
            onDataChanged?.();
          }}
        />
      ) : null}
    </div>
  );
}
