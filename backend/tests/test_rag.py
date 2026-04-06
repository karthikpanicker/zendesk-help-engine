"""
Unit tests for the RAG pipeline: retriever, prompt builder, suggester.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import chromadb
import pytest

from backend.rag.prompt_builder import SYSTEM_PROMPT, build_prompt, _format_chunks


# ---------------------------------------------------------------------------
# prompt_builder
# ---------------------------------------------------------------------------


def test_build_prompt_includes_customer_message():
    chunks = [
        {
            "text": "Submit PTO via HR Portal.",
            "score": 0.9,
            "metadata": {"source_type": "ticket", "title": "PTO Guide"},
        }
    ]
    prompt = build_prompt("How do I request time off?", chunks)
    assert "How do I request time off?" in prompt.user
    assert prompt.system == SYSTEM_PROMPT


def test_build_prompt_includes_chunk_text():
    chunks = [
        {
            "text": "Use the Finance portal for expenses.",
            "score": 0.8,
            "metadata": {"source_type": "article", "title": "Expenses FAQ"},
        }
    ]
    prompt = build_prompt("How do I claim expenses?", chunks)
    assert "Use the Finance portal" in prompt.user


def test_build_prompt_empty_chunks_shows_fallback():
    prompt = build_prompt("What is the process?", [])
    assert "No relevant knowledge found" in prompt.user


def test_format_chunks_numbers_sources():
    chunks = [
        {"text": "Step A", "score": 0.9, "metadata": {"source_type": "ticket", "title": "T1"}},
        {"text": "Step B", "score": 0.7, "metadata": {"source_type": "article", "title": "A1"}},
    ]
    formatted = _format_chunks(chunks)
    assert "[1]" in formatted
    assert "[2]" in formatted
    assert "Step A" in formatted
    assert "Step B" in formatted


# ---------------------------------------------------------------------------
# retriever — uses mock collection
# ---------------------------------------------------------------------------


def test_retriever_returns_results_above_min_score(mock_collection, mock_settings):
    from backend.rag.retriever import retrieve

    # Use min_score=0 so all pre-seeded test chunks are returned
    mock_settings.rag.min_score = 0.0
    mock_settings.rag.top_k = 4

    with patch("backend.rag.retriever.embed_query", return_value=[0.1] * 768):
        results = retrieve("How do I submit PTO?", mock_collection, mock_settings.rag, mock_settings.embeddings)

    assert isinstance(results, list)
    # All chunks should come back (min_score=0)
    assert len(results) > 0
    for r in results:
        assert "text" in r
        assert "score" in r
        assert "metadata" in r


def test_retriever_filters_below_min_score(mock_collection, mock_settings):
    from backend.rag.retriever import retrieve

    mock_settings.rag.min_score = 0.9999  # almost nothing will pass
    mock_settings.rag.top_k = 4

    with patch("backend.rag.retriever.embed_query", return_value=[0.1] * 768):
        results = retrieve("unrelated query", mock_collection, mock_settings.rag, mock_settings.embeddings)

    # With very high threshold and random test vectors, expect 0 or very few results
    assert isinstance(results, list)
    for r in results:
        assert r["score"] >= 0.9999


def test_retriever_empty_query_returns_empty(mock_collection, mock_settings):
    from backend.rag.retriever import retrieve

    results = retrieve("", mock_collection, mock_settings.rag, mock_settings.embeddings)
    assert results == []


# ---------------------------------------------------------------------------
# suggester — mocked Anthropic + embedder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_suggestion_returns_text(mock_collection, mock_settings):
    from backend.rag.suggester import generate_suggestion

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="Submit via HR Portal > Time Off.")]

    with (
        patch("backend.rag.retriever.embed_query", return_value=[0.1] * 768),
        patch("backend.rag.suggester.retrieve", return_value=[
            {
                "text": "Submit via HR Portal.",
                "score": 0.85,
                "metadata": {
                    "source_type": "ticket",
                    "title": "PTO Guide",
                    "url": "https://example.com",
                    "source_id": "ticket_101",
                },
            }
        ]),
        patch(
            "backend.rag.suggester.anthropic.AsyncAnthropic"
        ) as mock_anthropic_cls,
    ):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=fake_response)
        mock_anthropic_cls.return_value = mock_client

        result = await generate_suggestion("How do I request PTO?", mock_collection, mock_settings)

    assert result["suggestion"] == "Submit via HR Portal > Time Off."
    assert result["retrieved_count"] == 1
    assert len(result["sources"]) == 1


@pytest.mark.asyncio
async def test_generate_suggestion_no_chunks_returns_none(mock_collection, mock_settings):
    from backend.rag.suggester import generate_suggestion

    with patch("backend.rag.suggester.retrieve", return_value=[]):
        result = await generate_suggestion("Random unrelated question", mock_collection, mock_settings)

    assert result["suggestion"] is None
    assert result["retrieved_count"] == 0
