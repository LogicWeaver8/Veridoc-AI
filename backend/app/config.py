"""Application configuration.

Every value can be overridden with an environment variable (see .env.example).
Nothing secret is hardcoded here; API keys come from the environment only.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/ -> repository root
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and .env files."""

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "VeriDox AI"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api"
    cors_origins: str = "*"  # comma separated list, "*" for local development

    # --- Storage -----------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data"
    database_url: str | None = None  # defaults to SQLite inside data_dir
    max_upload_mb: int = Field(default=25, ge=1, le=200)
    max_batch_questions: int = Field(default=500, ge=1, le=5000)

    # --- Chunking ----------------------------------------------------------
    chunk_size_tokens: int = Field(default=650, ge=100)
    chunk_overlap_tokens: int = Field(default=90, ge=0)
    embedding_batch_size: int = Field(default=32, ge=1, le=256)

    # --- Embeddings --------------------------------------------------------
    # "hashing" works offline with zero downloads and is the safe default.
    # "sentence-transformers" loads a real neural embedding model.
    embedding_provider: str = "hashing"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = Field(default=384, ge=32)

    # --- Vector index ------------------------------------------------------
    # "auto" uses FAISS when installed, otherwise a NumPy cosine index.
    vector_backend: str = "auto"

    # --- Retrieval ---------------------------------------------------------
    retrieval_candidates: int = Field(default=15, ge=1, le=100)
    final_evidence_chunks: int = Field(default=6, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1)
    min_vector_similarity: float = Field(default=0.10, ge=0.0, le=1.0)
    # Below this best-chunk similarity an otherwise covered answer is downgraded
    # to "partially_answered". Hashing embeddings score lower than neural ones.
    min_answer_similarity: float = Field(default=0.20, ge=0.0, le=1.0)
    reranker_enabled: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Generation / LLM --------------------------------------------------
    # "mock" is a clearly labelled extractive provider that needs no API key.
    llm_provider: str = "mock"
    llm_model: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    llm_timeout_seconds: float = Field(default=45.0, ge=1.0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)

    # --- Extraction --------------------------------------------------------
    ocr_enabled: bool = True
    ocr_min_chars_per_page: int = Field(default=40, ge=0)

    # --- Batch -------------------------------------------------------------
    batch_progress_commit_every: int = Field(default=5, ge=1)

    # ----------------------------------------------------------------------
    # Derived paths
    # ----------------------------------------------------------------------
    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def batch_results_dir(self) -> Path:
        return self.data_dir / "batch_results"

    @property
    def batch_upload_dir(self) -> Path:
        return self.data_dir / "batch_uploads"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = (self.data_dir / "knowledge.db").as_posix()
        return f"sqlite:///{db_path}"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def allowed_extensions(self) -> set[str]:
        return {".pdf", ".txt", ".md", ".markdown"}

    def ensure_directories(self) -> None:
        """Create the storage folders the application expects."""
        for directory in (
            self.data_dir,
            self.upload_dir,
            self.index_dir,
            self.batch_results_dir,
            self.batch_upload_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    """Create settings and make sure storage folders exist."""
    settings = Settings()
    settings.ensure_directories()
    return settings
