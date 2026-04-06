"""
ChromaDB wrapper. Provides a single persistent collection used by both
the ingestion pipeline (writes) and the RAG retriever (reads).
"""

from __future__ import annotations

from functools import lru_cache

import chromadb
from chromadb import Collection

from backend.config import ChromaConfig


@lru_cache(maxsize=1)
def get_chroma_client(persist_directory: str) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=persist_directory)


def get_collection(cfg: ChromaConfig) -> Collection:
    client = get_chroma_client(cfg.persist_directory)
    return client.get_or_create_collection(
        name=cfg.collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(
    collection: Collection,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    """Idempotent upsert — safe to call multiple times with the same IDs."""
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )
