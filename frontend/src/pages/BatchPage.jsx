import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import Icon from "../components/Icons.jsx";
import { Alert, EmptyState, PageHeader, Spinner, StatusBadge } from "../components/ui.jsx";
import { formatDate } from "../utils/format.js";

const RESULT_COLUMNS = [
  "question",
  "answer",
  "status",
  "source_document",
  "document_version",
  "page_number",
  "section",
];

const ACTIVE_STATUSES = new Set(["pending", "processing"]);

export default function BatchPage({ appSettings }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const [uploadError, setUploadError] = useState("");
  const fileRef = useRef(null);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const data = await api.listBatchJobs();
      setJobs(data.items);
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const hasActive = jobs.some((job) => ACTIVE_STATUSES.has(job.status));

  useEffect(() => {
    if (!hasActive) return undefined;
    const timer = window.setInterval(() => load({ silent: true }), 4000);
    return () => window.clearInterval(timer);
  }, [hasActive, load]);

  async function handleUpload(file) {
    if (!file || uploading) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setUploadError("Upload a CSV file containing a 'question' column.");
      return;
    }
    setUploading(true);
    setUploadError("");
    setNotice("");
    try {
      const job = await api.uploadBatch(file);
      setNotice(`Batch job created for "${job.filename}" with ${job.total_questions} question(s).`);
      await load({ silent: true });
    } catch (requestError) {
      setUploadError(requestError.message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function downloadSample() {
    const csv =
      "question\n" +
      '"What is the annual leave policy?"\n' +
      '"How many sick leave days are available?"\n' +
      '"What is the work-from-home policy?"\n';
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "veridox-batch-template.csv";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  const maxQuestions = appSettings?.max_batch_questions;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bulk knowledge checks"
        title="Batch question answering"
        description="Ask many policy questions at once and download a cited CSV. Jobs run in the background, so large files do not block the request."
        actions={
          <>
            <button type="button" className="button button-ghost" onClick={downloadSample}>
              <Icon name="download" size={15} />
              CSV template
            </button>
            <button type="button" className="button button-primary" onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? <Spinner size={15} /> : <Icon name="upload" size={15} />}
              Upload questions
            </button>
          </>
        }
      />

      <input
        ref={fileRef}
        type="file"
        accept=".csv,text/csv"
        className="visually-hidden"
        onChange={(event) => handleUpload(event.target.files?.[0])}
      />

      <div className="batch-layout">
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Submit a question file</h2>
              <p>
                One question per row under a <code>question</code> header. Up to{" "}
                {maxQuestions ? `${maxQuestions} questions` : "the configured limit"} per job.
              </p>
            </div>
          </div>

          <div
            className={`dropzone dropzone-compact ${uploading ? "dropzone-busy" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => !uploading && fileRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") fileRef.current?.click();
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              handleUpload(event.dataTransfer.files?.[0]);
            }}
          >
            <div className="dropzone-icon">
              {uploading ? <Spinner size={22} /> : <Icon name="layers" size={22} />}
            </div>
            <div>
              <strong>{uploading ? "Submitting batch job…" : "Drop a CSV here or click to choose a file"}</strong>
              <span>Each question runs through the same grounded pipeline as chat.</span>
            </div>
          </div>

          {notice ? <Alert tone="success" onDismiss={() => setNotice("")}>{notice}</Alert> : null}
          {uploadError ? <Alert tone="danger" onDismiss={() => setUploadError("")}>{uploadError}</Alert> : null}

          <div className="batch-columns">
            <div>
              <h3>Required input</h3>
              <div className="code-block">
                <span>question</span>
                <span>&quot;What is the annual leave policy?&quot;</span>
                <span>&quot;How many sick leave days are available?&quot;</span>
              </div>
            </div>
            <div>
              <h3>Output columns</h3>
              <div className="chip-list">
                {RESULT_COLUMNS.map((column) => (
                  <code key={column} className="column-chip">
                    {column}
                  </code>
                ))}
              </div>
            </div>
          </div>

          <div className="batch-steps">
            <div><span>1</span> Validate CSV</div>
            <div><span>2</span> Run retrieval + evidence checks</div>
            <div><span>3</span> Persist answers and citations</div>
            <div><span>4</span> Download the result CSV</div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Batch jobs</h2>
              <p>Progress is stored in the database and survives page reloads.</p>
            </div>
            <button type="button" className="button button-ghost button-small" onClick={() => load()} disabled={loading}>
              {loading ? <Spinner size={14} /> : <Icon name="refresh" size={14} />}
              Refresh
            </button>
          </div>

          {error ? <Alert tone="danger" title="Could not load batch jobs">{error}</Alert> : null}

          {loading && jobs.length === 0 ? (
            <div className="documents-loading">
              <Spinner size={20} />
              Loading batch jobs…
            </div>
          ) : null}

          {!loading && jobs.length === 0 ? (
            <EmptyState
              icon="layers"
              title="No batch jobs yet"
              description="Upload a CSV of questions to run a bulk knowledge check."
              action={
                <button type="button" className="button button-small button-primary" onClick={() => fileRef.current?.click()}>
                  Upload questions
                </button>
              }
            />
          ) : null}

          {jobs.length ? (
            <div className="job-list">
              {jobs.map((job) => (
                <article key={job.id} className="job-card">
                  <div className="job-head">
                    <span className="job-icon">
                      <Icon name="layers" size={16} />
                    </span>
                    <div className="job-title">
                      <strong title={job.filename}>{job.filename}</strong>
                      <span>{formatDate(job.created_at, true)}</span>
                    </div>
                    <StatusBadge status={job.status} />
                  </div>

                  <div className="job-progress">
                    <div className="job-progress-track">
                      <span style={{ width: `${job.progress_percent}%` }} />
                    </div>
                    <span className="job-progress-text">
                      {job.processed_questions} / {job.total_questions} processed
                      {job.failed_questions ? ` · ${job.failed_questions} failed` : ""}
                    </span>
                  </div>

                  {job.error_message ? <p className="job-error">{job.error_message}</p> : null}

                  <div className="job-actions">
                    <span className="job-id">Job {job.id.slice(0, 8)}</span>
                    {job.result_available ? (
                      <a className="button button-small button-ghost" href={api.batchDownloadUrl(job.id)} download>
                        <Icon name="download" size={14} />
                        Download results
                      </a>
                    ) : (
                      <span className="muted-text">Results available when processing completes</span>
                    )}
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
