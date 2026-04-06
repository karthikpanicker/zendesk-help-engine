from __future__ import annotations

from chromadb import Collection
from fastapi import APIRouter, Depends

from backend.config import Settings, get_settings
from backend.dependencies import get_collection_dep

router = APIRouter()


@router.get("/health")
async def health(
    settings: Settings = Depends(get_settings),
    collection: Collection = Depends(get_collection_dep),
) -> dict:
    return {
        "status": "ok",
        "model": settings.anthropic.model,
        "embeddings_provider": settings.embeddings.provider,
        "chroma_docs": collection.count(),
        "workflow_tags": settings.workflow.tags,
    }
