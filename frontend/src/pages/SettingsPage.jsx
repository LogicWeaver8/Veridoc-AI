import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import Icon from "../components/Icons.jsx";
import { Alert, PageHeader, Spinner } from "../components/ui.jsx";
import { formatBytes, formatDate } from "../utils/format.js";

function Fact({ label, value, mono = false }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd className={mono ? "mono" : ""}>{value ?? "—"}</dd>
    </div>
  );
}

export default function SettingsPage({ onDataChanged }) {
  const [settings, setSettings] = useState(null);
  const [index, setIndex] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rebuilding, setRebuilding] = useState(false);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [settingsData, indexData] = await Promise.all([api.appSettings(), api.indexStatus()]);
      setSettings(settingsData);
      setIndex(indexData);
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function rebuild() {
    const confirmed = window.confirm(
      "Rebuild the search index from the stored chunks? Answers will be unavailable briefly while this runs.",
    );
    if (!confirmed) return;
    setRebuilding(true);
    setNotice("");
    try {
      const result = await api.rebuildIndex();
      setNotice(`Index rebuilt with ${result.chunk_count} chunks using ${result.backend.toUpperCase()}.`);
      await load();
      onDataChanged?.();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRebuilding(false);
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Runtime configuration"
        title="Settings & diagnostics"
        description="These values are read-only here and come from the backend environment. Change them in your .env file and restart the API."
        actions={
          <button type="button" className="button button-ghost" onClick={load} disabled={loading}>
            {loading ? <Spinner size={15} /> : <Icon name="refresh" size={15} />}
            Refresh
          </button>
        }
      />

      {error ? <Alert tone="danger" title="Could not load settings">{error}</Alert> : null}
      {notice ? <Alert tone="success" onDismiss={() => setNotice("")}>{notice}</Alert> : null}

      {loading && !settings ? (
        <div className="documents-loading">
          <Spinner size={20} />
          Loading configuration…
        </div>
      ) : null}

      {settings ? (
        <div className="settings-grid">
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Answer generation</h2>
                <p>The provider used to compose grounded answers.</p>
              </div>
              <span className={`mode-chip ${settings.llm_is_mock ? "mode-mock" : "mode-live"}`}>
                {settings.llm_is_mock ? "Mock mode" : "LLM live"}
              </span>
            </div>

            {settings.llm_is_mock ? (
              <Alert tone="warning" title="No language model is configured">
                Answers are extractive and explicitly labelled as mock output. Set LLM_PROVIDER to
                gemini, openai or ollama (plus the provider key) to enable generated answers.
              </Alert>
            ) : null}

            <dl className="fact-list">
              <Fact label="Provider" value={settings.llm_display_name} />
              <Fact label="Provider key" value={settings.llm_provider} mono />
              <Fact label="Model" value={settings.llm_model || "provider default"} mono />
              <Fact label="Temperature" value={settings.llm_temperature ?? "—"} />
              <Fact label="Ollama endpoint" value={settings.ollama_base_url ?? "n/a"} mono />
            </dl>

            <div className="settings-note">
              <Icon name="info" size={14} />
              API keys are never returned by this endpoint. Configure them through environment
              variables.
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Retrieval</h2>
                <p>Hybrid embeddings + BM25 with reciprocal rank fusion.</p>
              </div>
            </div>
            <dl className="fact-list">
              <Fact label="Embedding provider" value={settings.embedding_provider} mono />
              <Fact label="Embedding model" value={settings.embedding_model} mono />
              <Fact label="Dimensions" value={settings.embedding_dimension} />
              <Fact label="Vector backend" value={settings.vector_backend} mono />
              <Fact label="retrieval_candidates" value={settings.retrieval_candidates} mono />
              <Fact label="final_evidence_chunks" value={settings.final_evidence_chunks} mono />
              <Fact label="CrossEncoder reranking" value={settings.reranker_enabled ? "Enabled" : "Disabled"} />
              <Fact label="FAISS installed" value={settings.faiss_available ? "Yes" : "No (NumPy fallback)"} />
            </dl>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Ingestion</h2>
                <p>Chunking, embeddings and OCR behaviour.</p>
              </div>
            </div>
            <dl className="fact-list">
              <Fact label="Chunk size (tokens)" value={settings.chunk_size_tokens} />
              <Fact label="Chunk overlap (tokens)" value={settings.chunk_overlap_tokens} />
              <Fact label="Embedding batch size" value={settings.embedding_batch_size} />
              <Fact label="OCR enabled" value={settings.ocr_enabled ? "Yes" : "No"} />
              <Fact label="OCR engine available" value={settings.ocr_available ? "Yes" : "No"} />
              <Fact label="Max upload size" value={`${settings.max_upload_mb} MB`} />
              <Fact label="Max batch questions" value={settings.max_batch_questions} />
            </dl>
            {!settings.ocr_available ? (
              <div className="settings-note">
                <Icon name="info" size={14} />
                Tesseract and pytesseract are optional. Without them, scanned PDF pages cannot be
                OCR&apos;d and are reported as warnings.
              </div>
            ) : null}
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Index administration</h2>
                <p>Vector and keyword indexes persisted under data/indexes.</p>
              </div>
              <button type="button" className="button button-small button-primary" onClick={rebuild} disabled={rebuilding}>
                {rebuilding ? <Spinner size={14} /> : <Icon name="refresh" size={14} />}
                Rebuild index
              </button>
            </div>

            {index?.needs_rebuild ? (
              <Alert tone="warning" title="Embedding change detected">
                The persisted index was built with a different embedding signature. Rebuild before
                relying on answers.
              </Alert>
            ) : null}

            <dl className="fact-list">
              <Fact label="Indexed chunks" value={index?.chunk_count ?? 0} />
              <Fact label="Documents in index" value={index?.document_count ?? 0} />
              <Fact label="Vector backend" value={index?.backend?.toUpperCase()} />
              <Fact label="Index size" value={formatBytes(index?.size_bytes ?? 0)} />
              <Fact label="Last updated" value={formatDate(index?.updated_at, true)} />
              <Fact label="Rebuild required" value={index?.needs_rebuild ? "Yes" : "No"} />
            </dl>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Workspace & environment</h2>
                <p>Service identity and limitations.</p>
              </div>
            </div>
            <dl className="fact-list">
              <Fact label="Application" value={settings.app_name} />
              <Fact label="Environment" value={settings.environment} />
              <Fact label="Authentication" value="Demo gate (not enforced server-side)" />
              <Fact label="Tenant isolation" value="Single workspace" />
            </dl>
            <div className="settings-note">
              <Icon name="shield" size={14} />
              This build is intended for a trusted internal deployment. Add SSO, per-tenant
              filtering and role-based access before exposing it to untrusted users.
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
