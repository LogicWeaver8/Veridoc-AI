import os
import tempfile

# Keep the module-level default app (imported by test discovery) away from the
# repository's real data folder.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="veridox-boot-"))
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")
os.environ.setdefault("OCR_ENABLED", "false")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.sample_docs import LEAVE_DOC, TRAVEL_DOC, WIFI_DOC  # noqa: E402,F401


def make_settings(data_dir: Path, **overrides) -> Settings:
    values = dict(
        data_dir=data_dir,
        embedding_provider="hashing",
        llm_provider="mock",
        cors_origins="*",
        embedding_batch_size=8,
        retrieval_candidates=12,
        final_evidence_chunks=5,
        chunk_size_tokens=220,
        chunk_overlap_tokens=40,
        min_vector_similarity=0.05,
        batch_progress_commit_every=2,
        ocr_enabled=False,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path / "data")


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def settings_factory(tmp_path: Path):
    def _make(name: str, **overrides) -> Settings:
        return make_settings(tmp_path / name, **overrides)

    return _make


@pytest.fixture
def client_factory(settings_factory):
    stack: list[TestClient] = []

    def _make(**overrides) -> TestClient:
        settings = settings_factory(f"app-{len(stack)}", **overrides)
        test_app = create_app(settings)
        test_client = TestClient(test_app)
        test_client.__enter__()
        stack.append(test_client)
        return test_client

    yield _make
    for test_client in reversed(stack):
        test_client.__exit__(None, None, None)


@pytest.fixture
def upload():
    def _upload(client: TestClient, filename: str, content: bytes, data: dict | None = None):
        return client.post(
            "/api/documents/upload",
            files={"file": (filename, content, "application/octet-stream")},
            data=data or {},
        )

    return _upload
