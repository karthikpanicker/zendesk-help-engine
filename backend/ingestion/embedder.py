"""
Embedding wrapper that supports two backends:
  - "local"  → BAAI/bge-base-en-v1.5 via sentence-transformers (default)
  - "voyage" → Voyage AI voyage-3 API

Switch by setting embeddings.provider in config/config.yaml.
The local model is downloaded on first use and cached by HuggingFace (~440MB).
"""

from __future__ import annotations

from functools import lru_cache

from backend.config import EmbeddingsConfig


# ---------------------------------------------------------------------------
# Local (sentence-transformers)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_local_model(model_name: str):
    from sentence_transformers import SentenceTransformer  # type: ignore

    return SentenceTransformer(model_name)


def _embed_local(texts: list[str], model_name: str) -> list[list[float]]:
    model = _get_local_model(model_name)
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return embeddings.tolist()


# ---------------------------------------------------------------------------
# Voyage AI
# ---------------------------------------------------------------------------


def _embed_voyage(
    texts: list[str],
    model_name: str,
    api_key: str,
    input_type: str = "document",
) -> list[list[float]]:
    import voyageai  # type: ignore

    client = voyageai.Client(api_key=api_key)
    result = client.embed(texts, model=model_name, input_type=input_type)
    return result.embeddings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def embed_documents(texts: list[str], cfg: EmbeddingsConfig) -> list[list[float]]:
    """Embed a list of document chunks for storage in ChromaDB."""
    if not texts:
        return []
    if cfg.provider == "voyage":
        return _embed_voyage(texts, cfg.voyage_model, cfg.voyage_api_key, "document")
    return _embed_local(texts, cfg.local_model)


def embed_query(text: str, cfg: EmbeddingsConfig) -> list[float]:
    """Embed a single query string for retrieval."""
    if cfg.provider == "voyage":
        return _embed_voyage([text], cfg.voyage_model, cfg.voyage_api_key, "query")[0]
    # BGE models benefit from a query prefix
    prefixed = f"Represent this sentence for searching relevant passages: {text}"
    return _embed_local([prefixed], cfg.local_model)[0]
