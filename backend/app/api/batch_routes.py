"""CSV batch processing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_session
from app.api.serializers import batch_job_out
from app.schemas.batch import BatchJobListOut, BatchJobOut
from app.utils.files import delete_stored_file, save_upload

router = APIRouter(prefix="/batch", tags=["batch"])


@router.post("/upload", response_model=BatchJobOut, status_code=201)
async def upload_batch(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> BatchJobOut:
    container = get_container(request)
    stored = await save_upload(
        file,
        container.settings,
        allowed_extensions={".csv"},
        directory=container.settings.batch_upload_dir,
    )
    try:
        job = container.batch.create_job(session, stored)
    except Exception:
        delete_stored_file(stored.relative_path, container.settings)
        raise

    background_tasks.add_task(container.batch.process_job, job.id)
    return batch_job_out(job)


@router.get("/jobs", response_model=BatchJobListOut)
def list_batch_jobs(
    request: Request, limit: int = 50, session: Session = Depends(get_session)
) -> BatchJobListOut:
    container = get_container(request)
    jobs = container.batch.list_jobs(session, limit=min(max(limit, 1), 200))
    return BatchJobListOut(items=[batch_job_out(job) for job in jobs], total=len(jobs))


@router.get("/{job_id}/status", response_model=BatchJobOut)
def batch_status(
    job_id: str, request: Request, session: Session = Depends(get_session)
) -> BatchJobOut:
    container = get_container(request)
    job = container.batch.get_job(session, job_id)
    return batch_job_out(job)


@router.get("/{job_id}/download")
def download_batch_results(
    job_id: str, request: Request, session: Session = Depends(get_session)
) -> FileResponse:
    container = get_container(request)
    job = container.batch.get_job(session, job_id)
    path = container.batch.result_path(job)
    return FileResponse(
        path,
        media_type="text/csv",
        filename=f"veridox_batch_{job.id}.csv",
    )
