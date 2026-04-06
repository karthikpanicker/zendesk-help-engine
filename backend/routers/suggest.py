"""
POST /suggest — real-time suggestion endpoint called by the ZAF sidebar app.

Fast path: if the ticket carries no workflow tags, returns immediately
without any embedding or LLM call.
"""

from __future__ import annotations

import logging

from chromadb import Collection
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.dependencies import get_collection_dep
from backend.rag.suggester import generate_suggestion

logger = logging.getLogger(__name__)
router = APIRouter()


class SuggestRequest(BaseModel):
    ticket_id: str
    current_message: str
    ticket_tags: list[str] = []
    conversation_history: list[dict] = []


class SuggestResponse(BaseModel):
    is_workflow_question: bool
    suggestion: str | None
    sources: list[dict]
    retrieved_count: int


@router.post("/suggest", response_model=SuggestResponse)
async def suggest(
    req: SuggestRequest,
    settings: Settings = Depends(get_settings),
    collection: Collection = Depends(get_collection_dep),
) -> SuggestResponse:
    # --- Fast path: tag classification ---
    workflow_tag_set = set(settings.workflow.tags)
    ticket_tag_set = set(req.ticket_tags)
    is_workflow = bool(workflow_tag_set & ticket_tag_set)

    if not is_workflow:
        return SuggestResponse(
            is_workflow_question=False,
            suggestion=None,
            sources=[],
            retrieved_count=0,
        )

    if not req.current_message.strip():
        return SuggestResponse(
            is_workflow_question=True,
            suggestion=None,
            sources=[],
            retrieved_count=0,
        )

    # --- RAG path ---
    try:
        result = await generate_suggestion(
            current_message=req.current_message,
            collection=collection,
            settings=settings,
        )
    except Exception as e:
        logger.error("Suggestion generation failed for ticket %s: %s", req.ticket_id, e)
        raise HTTPException(status_code=500, detail="Suggestion generation failed")

    return SuggestResponse(
        is_workflow_question=True,
        suggestion=result["suggestion"],
        sources=result["sources"],
        retrieved_count=result["retrieved_count"],
    )
