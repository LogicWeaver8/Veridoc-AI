"""Upload the demo policy corpus into a running VeriDox instance.

The script is idempotent: documents that already exist are reported and reused.

Usage:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --base-url http://127.0.0.1:8000 --ask --batch
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
import time
from pathlib import Path

import httpx

DEMO_DIR = Path(__file__).resolve().parent / "demo_documents"
BATCH_CSV = Path(__file__).resolve().parent / "demo_batch_questions.csv"

# Leave Policy 2026 is uploaded as a new version of the 2025 document so the
# version-intelligence flow can be demonstrated end to end.
VERSION_DOCUMENT = "Leave_Policy_2026.md"
BASE_DOCUMENT = ("Leave_Policy_2025.md", "2025-01-01", "2025.1")
OTHER_DOCUMENTS = (
    ("Employee_Handbook_2026.md", "2026-01-01", "2026.1"),
    ("Travel_and_Expense_Policy_2026.txt", "2026-01-01", "2026.1"),
    ("Remote_Work_SOP_2026.md", "2026-01-01", "2026.1"),
    ("IT_Security_Policy_2026.md", "2026-01-01", "2026.1"),
    ("Code_of_Conduct_2026.md", "2026-01-01", "2026.1"),
    ("Learning_and_Development_Policy_2026.md", "2026-01-01", "2026.1"),
    ("Office_Access_and_Facilities_2026.pdf", "2026-01-01", "2026.1"),
)
DEFAULT_QUESTION = "How many annual leave days do employees get in 2026?"


def file_part(path: Path) -> tuple:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return (path.name, path.read_bytes(), mime)


def error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(body)[:200]


def check_health(client: httpx.Client, base_url: str) -> None:
    try:
        response = client.get(f"{base_url}/health")
    except httpx.HTTPError as exc:
        raise SystemExit(
            f"Could not reach the backend at {base_url}. Start it first:\n"
            f"  uvicorn app.main:app --reload   (from backend/)\nError: {exc}"
        ) from exc
    if response.status_code != 200:
        raise SystemExit(f"Health check failed with HTTP {response.status_code}.")
    body = response.json()
    print(
        f"Connected to {body.get('app')} {body.get('version')} "
        f"(LLM: {body.get('llm_provider')}, embeddings: {body.get('embedding_provider')})."
    )


def upload_document(
    client: httpx.Client,
    base_url: str,
    filename: str,
    effective_from: str,
    version_label: str,
) -> tuple[str | None, bool]:
    """Return (document id, created). Existing documents are reused."""
    path = DEMO_DIR / filename
    if not path.exists():
        print(f"  ! Missing demo file: {path}")
        return None, False

    response = client.post(
        f"{base_url}/api/documents/upload",
        files={"file": file_part(path)},
        data={"effective_from": effective_from, "version_label": version_label},
    )
    if response.status_code == 409:
        existing = response.json().get("error", {}).get("details", {}).get("existing_document_id")
        print(f"  = {filename}: already indexed, reusing document {existing}")
        return existing, False
    if response.status_code >= 400:
        print(f"  ! {filename}: {error_message(response)}")
        return None, False

    document = response.json()
    print(f"  + {filename}: uploaded (document {document['id']})")
    return document["id"], True


def add_version(
    client: httpx.Client,
    base_url: str,
    document_id: str,
    filename: str,
    effective_from: str,
    version_label: str,
    supersedes_version_id: str | None,
) -> bool:
    path = DEMO_DIR / filename
    data = {"effective_from": effective_from, "version_label": version_label}
    if supersedes_version_id:
        data["supersedes_version_id"] = supersedes_version_id
    response = client.post(
        f"{base_url}/api/documents/{document_id}/versions",
        files={"file": file_part(path)},
        data=data,
    )
    if response.status_code == 409:
        print(f"  = {filename}: version already present, reusing it")
        return False
    if response.status_code >= 400:
        print(f"  ! {filename}: {error_message(response)}")
        return False
    print(f"  + {filename}: uploaded as version {version_label}")
    return True


def wait_for_document(
    client: httpx.Client, base_url: str, document_id: str, timeout: float
) -> dict | None:
    deadline = time.monotonic() + timeout
    last_status = ""
    while time.monotonic() < deadline:
        response = client.get(f"{base_url}/api/documents/{document_id}")
        if response.status_code >= 400:
            print(f"  ! Could not read document {document_id}: {error_message(response)}")
            return None
        document = response.json()
        if document["status"] != last_status:
            last_status = document["status"]
            print(f"    {document['filename']}: {last_status}")
        if document["status"] in {"completed", "failed"}:
            return document
        time.sleep(0.4)
    print(f"  ! Timed out waiting for {document_id}")
    return None


def first_version_id(document: dict) -> str | None:
    versions = document.get("versions") or []
    return versions[0]["id"] if versions else None


def run_batch(client: httpx.Client, base_url: str, timeout: float) -> None:
    if not BATCH_CSV.exists():
        print(f"  ! Batch sample not found: {BATCH_CSV}")
        return
    response = client.post(
        f"{base_url}/api/batch/upload", files={"file": file_part(BATCH_CSV)}
    )
    if response.status_code >= 400:
        print(f"  ! Batch upload failed: {error_message(response)}")
        return
    job = response.json()
    print(f"  + Batch job {job['id']} queued ({job['total_questions']} questions)")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"{base_url}/api/batch/{job['id']}/status")
        if status.status_code >= 400:
            print(f"  ! Batch status failed: {error_message(status)}")
            return
        job = status.json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.5)

    print(
        f"    status={job['status']} progress={job['progress_percent']}% "
        f"failed={job['failed_questions']}"
    )
    if job["result_available"]:
        print(f"    results: {base_url}/api/batch/{job['id']}/download")


def ask(client: httpx.Client, base_url: str, question: str) -> None:
    response = client.post(f"{base_url}/api/chat/ask", json={"question": question})
    if response.status_code >= 400:
        print(f"  ! Question failed: {error_message(response)}")
        return
    answer = response.json()
    print(f"\nQ: {question}")
    print(
        f"A [{answer['answer_status']}, confidence {answer['confidence']}%, "
        f"provider {answer['provider']}]:"
    )
    print(answer["answer"][:900])
    for citation in answer["citations"][:4]:
        location = citation.get("section") or citation.get("page_number") or "n/a"
        print(
            f"  - {citation['document_name']} ({citation['version_label']}) "
            f"| {location} | relevance {citation['relevance']:.2f}"
        )
    if answer["notes"]:
        print("  Notes: " + "; ".join(answer["notes"]))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Seed VeriDox with the demo corpus.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--ask", action="store_true", help="Ask one sample question")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--batch", action="store_true", help="Run the sample CSV batch job")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(timeout=args.timeout) as client:
        check_health(client, base_url)
        print("\nUploading the demo corpus:")
        base_name, base_effective, base_label = BASE_DOCUMENT
        base_id, _ = upload_document(client, base_url, base_name, base_effective, base_label)
        if not base_id:
            raise SystemExit("The base Leave Policy document could not be uploaded.")

        base_document = wait_for_document(client, base_url, base_id, args.timeout)
        supersedes = first_version_id(base_document) if base_document else None
        if add_version(
            client,
            base_url,
            base_id,
            VERSION_DOCUMENT,
            "2026-01-01",
            "2026.1",
            supersedes,
        ):
            wait_for_document(client, base_url, base_id, args.timeout)

        document_ids = [base_id]
        for filename, effective_from, label in OTHER_DOCUMENTS:
            document_id, _ = upload_document(
                client, base_url, filename, effective_from, label
            )
            if document_id:
                document_ids.append(document_id)

        print("\nWaiting for processing:")
        documents = [wait_for_document(client, base_url, doc_id, args.timeout) for doc_id in document_ids]

        print("\nWorkspace summary:")
        completed = 0
        for document in documents:
            if not document:
                continue
            if document["status"] == "completed":
                completed += 1
            active = document.get("active_version") or {}
            print(
                f"  {document['filename']}: {document['status']} | "
                f"versions={document['version_count']} | "
                f"active={active.get('version_label', 'n/a')} | "
                f"pages={document['page_count']} | chunks={document['chunk_count']}"
            )
            if document["status"] == "failed":
                print(f"    error: {document.get('error_message')}")
        print(f"\n{completed}/{len(documents)} documents completed.")

        if args.ask:
            ask(client, base_url, args.question)
        if args.batch:
            print("\nBatch Q&A:")
            run_batch(client, base_url, args.timeout)


if __name__ == "__main__":
    main()
