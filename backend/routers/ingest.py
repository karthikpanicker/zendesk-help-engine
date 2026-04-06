"""
POST /ingest   — trigger a background re-ingestion of all Zendesk data sources.
GET  /ingest/status/{task_id} — poll ingestion progress.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.ingestion.runner import IngestionProgress, run_ingestion

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task registry (fine for single-process deployment)
_tasks: dict[str, dict] = {}


class IngestResponse(BaseModel):
    task_id: str
    status: Literal["started"]


class IngestStatusResponse(BaseModel):
    task_id: str
    status: Literal["running", "completed", "failed"]
    progress: IngestionProgress | None = None
    error: str | None = None


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingest(
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "running", "progress": None, "error": None}
    background_tasks.add_task(_run_task, task_id, settings)
    return IngestResponse(task_id=task_id, status="started")


@router.get("/ingest/status/{task_id}", response_model=IngestStatusResponse)
async def ingest_status(task_id: str) -> IngestStatusResponse:
    task = _tasks.get(task_id)
    if task is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found")
    return IngestStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        error=task["error"],
    )


async def _run_task(task_id: str, settings: Settings) -> None:
    try:
        progress = await run_ingestion(settings)
        _tasks[task_id] = {"status": "completed", "progress": progress, "error": None}
        logger.info("Ingestion task %s completed: %s", task_id, progress)
    except Exception as e:
        logger.error("Ingestion task %s failed: %s", task_id, e)
        _tasks[task_id] = {"status": "failed", "progress": None, "error": str(e)}
