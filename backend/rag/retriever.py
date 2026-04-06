"""
ChromaDB retriever: embeds a query and returns the top-k most similar chunks
above the configured cosine similarity threshold.
"""

from __future__ import annotations

from chromadb import Collection

from backend.config import RAGConfig, EmbeddingsConfig
from backend.ingestion.embedder import embed_query


def retrieve(
    query: str,
    collection: Collection,
    rag_cfg: RAGConfig,
    emb_cfg: EmbeddingsConfig,
) -> list[dict]:
    """
    Returns a list of dicts, each with:
      - text: str          (the chunk content)
      - score: float       (cosine similarity 0–1)
      - metadata: dict     (source_type, title, url, tags, ...)
    Sorted by score descending. Empty list if nothing passes min_score.
    """
    if not query.strip():
        return []

    query_embedding = embed_query(query, emb_cfg)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=rag_cfg.top_k,
        include=["documents", "metadatas", "distances"],
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    chunks: list[dict] = []
    for text, meta, dist in zip(docs, metas, distances):
        # ChromaDB cosine distance: 0 = identical, 1 = orthogonal, 2 = opposite
        # Convert to similarity: 1 - distance (only valid for normalised vectors)
        score = max(0.0, 1.0 - dist)
        if score >= rag_cfg.min_score:
            chunks.append({"text": text, "score": score, "metadata": meta})

    # Sort best-first (already sorted by Chroma, but be explicit)
    chunks.sort(key=lambda c: c["score"], reverse=True)
    return chunks
