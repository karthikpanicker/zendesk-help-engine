"""
Core RAG loop: retrieve relevant chunks → build prompt → call Claude → return suggestion.
"""

from __future__ import annotations

import anthropic
from chromadb import Collection

from backend.config import Settings
from backend.rag.prompt_builder import build_prompt
from backend.rag.retriever import retrieve


async def generate_suggestion(
    current_message: str,
    collection: Collection,
    settings: Settings,
) -> dict:
    """
    Run the full RAG pipeline for a single customer message.

    Returns:
    {
        "suggestion": str | None,
        "sources": list[dict],
        "retrieved_count": int,
    }
    """
    # Retrieve relevant chunks
    chunks = retrieve(
        query=current_message,
        collection=collection,
        rag_cfg=settings.rag,
        emb_cfg=settings.embeddings,
    )

    if not chunks:
        return {
            "suggestion": None,
            "sources": [],
            "retrieved_count": 0,
        }

    # Build prompt
    prompt = build_prompt(current_message, chunks)

    # Call Claude
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic.api_key)
    response = await client.messages.create(
        model=settings.anthropic.model,
        max_tokens=settings.rag.suggestion_max_tokens,
        system=prompt.system,
        messages=[{"role": "user", "content": prompt.user}],
    )

    suggestion_text = response.content[0].text if response.content else None

    sources = [
        {
            "source_type": c["metadata"].get("source_type"),
            "title": c["metadata"].get("title"),
            "url": c["metadata"].get("url"),
            "source_id": c["metadata"].get("source_id"),
            "score": round(c["score"], 3),
        }
        for c in chunks
    ]

    return {
        "suggestion": suggestion_text,
        "sources": sources,
        "retrieved_count": len(chunks),
    }
