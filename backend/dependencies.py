"""
FastAPI dependency injection helpers.
"""

from __future__ import annotations

from chromadb import Collection
from fastapi import Depends

from backend.config import Settings, get_settings
from backend.store.vector_store import get_collection


def get_collection_dep(settings: Settings = Depends(get_settings)) -> Collection:
    return get_collection(settings.chroma)
