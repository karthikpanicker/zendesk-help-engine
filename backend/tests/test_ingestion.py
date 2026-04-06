"""
Unit tests for ingestion modules: chunker, embedder, and individual source ingestors.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ingestion.chunker import chunk_text
from backend.ingestion.guide import _is_workflow_relevant, _strip_html


# ---------------------------------------------------------------------------
# chunker
# ---------------------------------------------------------------------------


def test_chunk_text_short_text_returns_single_chunk():
    text = "This is a short sentence."
    chunks = chunk_text(text, chunk_size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_empty_returns_empty():
    assert chunk_text("", 512, 64) == []
    assert chunk_text("   ", 512, 64) == []


def test_chunk_text_long_text_splits():
    # ~1500 chars — should produce multiple chunks at chunk_size=512
    text = ("The quick brown fox jumps over the lazy dog. " * 35).strip()
    chunks = chunk_text(text, chunk_size=512, overlap=64)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 512 + 100  # allow slight overage at word boundary


def test_chunk_text_preserves_content():
    text = "Para one.\n\nPara two.\n\nPara three."
    chunks = chunk_text(text, chunk_size=20, overlap=0)
    combined = " ".join(chunks)
    assert "Para one" in combined
    assert "Para two" in combined
    assert "Para three" in combined


# ---------------------------------------------------------------------------
# guide — HTML stripping and relevance filter
# ---------------------------------------------------------------------------


def test_strip_html_removes_tags():
    html = "<h2>Title</h2><p>Body text with <strong>bold</strong>.</p>"
    result = _strip_html(html)
    assert "<" not in result
    assert "Title" in result
    assert "Body text with" in result
    assert "bold" in result


def test_strip_html_empty():
    assert _strip_html("") == ""


def test_is_workflow_relevant_by_label():
    article = {"label_names": ["workflow-question"], "title": "Unrelated title"}
    assert _is_workflow_relevant(article, ["workflow-question"], {"workflow question"})


def test_is_workflow_relevant_by_title_keyword():
    article = {"label_names": [], "title": "How to submit a workflow request"}
    assert _is_workflow_relevant(article, ["workflow-question"], {"workflow question", "how do i"})


def test_is_workflow_not_relevant():
    article = {"label_names": ["billing"], "title": "Invoice FAQ"}
    assert not _is_workflow_relevant(article, ["workflow-question"], {"workflow question"})


# ---------------------------------------------------------------------------
# embedder — provider switching (no real model loaded)
# ---------------------------------------------------------------------------


def test_embed_local_called_when_provider_is_local():
    from backend.config import EmbeddingsConfig
    from backend.ingestion.embedder import embed_documents

    cfg = EmbeddingsConfig(provider="local", local_model="BAAI/bge-base-en-v1.5")
    fake_vec = [[0.1] * 768]

    with patch("backend.ingestion.embedder._embed_local", return_value=fake_vec) as mock_fn:
        result = embed_documents(["test text"], cfg)

    mock_fn.assert_called_once()
    assert result == fake_vec


def test_embed_voyage_called_when_provider_is_voyage():
    from backend.config import EmbeddingsConfig
    from backend.ingestion.embedder import embed_documents

    cfg = EmbeddingsConfig(
        provider="voyage",
        voyage_model="voyage-3",
        voyage_api_key="fake-key",
    )
    fake_vec = [[0.2] * 1024]

    with patch("backend.ingestion.embedder._embed_voyage", return_value=fake_vec) as mock_fn:
        result = embed_documents(["test text"], cfg)

    mock_fn.assert_called_once()
    assert result == fake_vec


def test_embed_documents_empty_input():
    from backend.config import EmbeddingsConfig
    from backend.ingestion.embedder import embed_documents

    cfg = EmbeddingsConfig(provider="local")
    assert embed_documents([], cfg) == []
