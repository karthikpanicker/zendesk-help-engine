"""
Shared test fixtures.

- mock_collection: an in-memory ChromaDB collection pre-seeded with workflow knowledge
- mock_settings: Settings object pointing at mock Zendesk and using fake API keys
- No real embedding model is loaded — vectors are pre-seeded directly
"""

from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock, patch

import chromadb
import pytest
from fastapi.testclient import TestClient

from backend.config import (
    AnthropicConfig,
    ChromaConfig,
    EmbeddingsConfig,
    IngestionConfig,
    RAGConfig,
    ServerConfig,
    Settings,
    WorkflowConfig,
    ZendeskConfig,
)
from backend.main import app

WORKFLOW_TAGS = ["workflow-question", "process-clarification", "how-do-i", "procedure-help"]

# Fixed 768-dim vectors for test chunks (deterministic)
_rng = random.Random(42)


def _rand_vec(seed: int) -> list[float]:
    r = random.Random(seed)
    v = [r.gauss(0, 1) for _ in range(768)]
    norm = sum(x**2 for x in v) ** 0.5
    return [x / norm for x in v]


TEST_CHUNKS = [
    {
        "id": "ticket_101_chunk0",
        "text": "To submit a half-day PTO request, go to HR Portal > Time Off > New Request. Select 'Half Day' and specify AM or PM. Requires 48 hours advance notice.",
        "metadata": {
            "source_type": "ticket",
            "source_id": "ticket_101",
            "title": "How do I submit a PTO request?",
            "url": "https://yourcompany.zendesk.com/agent/tickets/101",
            "tags": "workflow-question,hr-process",
            "chunk_index": 0,
        },
    },
    {
        "id": "article_202_chunk0",
        "text": "Expense reports over $500 require manager approval then Finance team sign-off. Submit through the Expenses portal, attach all receipts.",
        "metadata": {
            "source_type": "article",
            "source_id": "article_202",
            "title": "Expense Report Approval Workflow",
            "url": "https://yourcompany.zendesk.com/hc/articles/202",
            "tags": "process-clarification,finance",
            "chunk_index": 0,
        },
    },
    {
        "id": "article_203_chunk0",
        "text": "All software access requests must go through the IT Portal. Select the application, choose permission level, add your manager as approver. Provisioning takes 2 business days.",
        "metadata": {
            "source_type": "article",
            "source_id": "article_203",
            "title": "Software and System Access Requests",
            "url": "https://yourcompany.zendesk.com/hc/articles/203",
            "tags": "how-do-i,it",
            "chunk_index": 0,
        },
    },
    {
        "id": "chat_301_chunk0",
        "text": "To reset your password, go to the IT Self-Service portal and click 'Forgot Password'. You'll receive a reset link via your personal email on file.",
        "metadata": {
            "source_type": "chat",
            "source_id": "chat_301",
            "title": "Chat chat_301",
            "url": "https://yourcompany.zendesk.com/agent/chats/chat_301",
            "tags": "workflow-question",
            "chunk_index": 0,
        },
    },
]


@pytest.fixture
def mock_collection():
    """In-memory ChromaDB collection pre-seeded with test chunks."""
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        name="test_workflow_kb",
        metadata={"hnsw:space": "cosine"},
    )
    collection.upsert(
        ids=[c["id"] for c in TEST_CHUNKS],
        documents=[c["text"] for c in TEST_CHUNKS],
        embeddings=[_rand_vec(i) for i, _ in enumerate(TEST_CHUNKS)],
        metadatas=[c["metadata"] for c in TEST_CHUNKS],
    )
    return collection


@pytest.fixture
def mock_settings():
    return Settings(
        zendesk=ZendeskConfig(
            subdomain="testcompany",
            email="test@testcompany.com",
            api_token="fake-token",
        ),
        anthropic=AnthropicConfig(api_key="fake-anthropic-key", model="claude-sonnet-4-6"),
        embeddings=EmbeddingsConfig(provider="local", local_model="BAAI/bge-base-en-v1.5"),
        workflow=WorkflowConfig(tags=WORKFLOW_TAGS),
        ingestion=IngestionConfig(batch_size=10, chunk_size=512, chunk_overlap=64),
        rag=RAGConfig(top_k=3, min_score=0.0),  # min_score=0 so test vecs always pass
        server=ServerConfig(cors_origins=["*"]),
        chroma=ChromaConfig(persist_directory="/tmp/test_chroma", collection_name="test_kb"),
    )


@pytest.fixture
def client(mock_settings, mock_collection):
    """FastAPI TestClient with mocked settings and collection."""
    with (
        patch("backend.main.get_settings", return_value=mock_settings),
        patch("backend.routers.suggest.get_settings", return_value=mock_settings),
        patch("backend.routers.health.get_settings", return_value=mock_settings),
        patch("backend.routers.ingest.get_settings", return_value=mock_settings),
        patch("backend.dependencies.get_settings", return_value=mock_settings),
        patch("backend.dependencies.get_collection", return_value=mock_collection),
    ):
        with TestClient(app) as c:
            yield c
