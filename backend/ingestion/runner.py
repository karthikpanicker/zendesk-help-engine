"""
Ingestion runner: orchestrates all data sources → chunks → embeddings → ChromaDB.
Called by the CLI script (scripts/run_ingestion.py) and by the POST /ingest endpoint.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from typing import Union

from backend.config import Settings, get_settings
from backend.ingestion.chat import ChatDocument, fetch_workflow_chats
from backend.ingestion.chunker import chunk_text
from backend.ingestion.embedder import embed_documents
from backend.ingestion.guide import ArticleDocument, fetch_workflow_articles
from backend.ingestion.tickets import TicketDocument, fetch_workflow_tickets
from backend.store.vector_store import get_collection, upsert_chunks

logger = logging.getLogger(__name__)

AnyDocument = Union[TicketDocument, ChatDocument, ArticleDocument]


@dataclass
class IngestionProgress:
    tickets: int = 0
    chats: int = 0
    articles: int = 0
    chunks_stored: int = 0
    errors: int = 0


async def run_ingestion(settings: Settings | None = None) -> IngestionProgress:
    if settings is None:
        settings = get_settings()

    progress = IngestionProgress()
    collection = get_collection(settings.chroma)

    # Fetch from all sources concurrently
    logger.info("Starting ingestion from all sources...")
    tickets_task = fetch_workflow_tickets(settings)
    chats_task = fetch_workflow_chats(settings)
    articles_task = fetch_workflow_articles(settings)

    tickets, chats, articles = await asyncio.gather(
        tickets_task, chats_task, articles_task, return_exceptions=True
    )

    all_docs: list[AnyDocument] = []

    if isinstance(tickets, Exception):
        logger.error("Ticket ingestion failed: %s", tickets)
        progress.errors += 1
    else:
        progress.tickets = len(tickets)
        all_docs.extend(tickets)

    if isinstance(chats, Exception):
        logger.error("Chat ingestion failed: %s", chats)
        progress.errors += 1
    else:
        progress.chats = len(chats)
        all_docs.extend(chats)

    if isinstance(articles, Exception):
        logger.error("Article ingestion failed: %s", articles)
        progress.errors += 1
    else:
        progress.articles = len(articles)
        all_docs.extend(articles)

    logger.info(
        "Fetched: %d tickets, %d chats, %d articles",
        progress.tickets,
        progress.chats,
        progress.articles,
    )

    # Chunk → embed → upsert in batches
    cfg_ing = settings.ingestion
    cfg_emb = settings.embeddings

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for doc in all_docs:
        chunks = chunk_text(doc.text, cfg_ing.chunk_size, cfg_ing.chunk_overlap)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc.doc_id}_chunk{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append(
                {
                    "source_type": doc.source_type,
                    "source_id": doc.doc_id,
                    "title": doc.title,
                    "url": doc.url,
                    "tags": ",".join(doc.tags),
                    "chunk_index": i,
                }
            )

    logger.info("Total chunks to embed: %d", len(ids))

    # Embed and upsert in batches
    batch_size = cfg_ing.batch_size
    for start in range(0, len(ids), batch_size):
        batch_ids = ids[start : start + batch_size]
        batch_docs = documents[start : start + batch_size]
        batch_meta = metadatas[start : start + batch_size]

        try:
            embeddings = embed_documents(batch_docs, cfg_emb)
            upsert_chunks(collection, batch_ids, batch_docs, embeddings, batch_meta)
            progress.chunks_stored += len(batch_ids)
            logger.info("Stored %d / %d chunks", progress.chunks_stored, len(ids))
        except Exception as e:
            logger.error("Batch upsert failed: %s", e)
            progress.errors += 1

    logger.info("Ingestion complete. %d chunks stored.", progress.chunks_stored)
    return progress
