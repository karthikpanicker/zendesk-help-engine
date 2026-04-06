"""
API-level tests for /suggest, /health, and /ingest endpoints.
All external calls (Anthropic, embedder) are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


WORKFLOW_TAGS = ["workflow-question", "process-clarification", "how-do-i", "procedure-help"]
FAKE_SUGGESTION = "To submit a PTO request, navigate to HR Portal > Time Off > New Request."


def _mock_suggest_result():
    return {
        "suggestion": FAKE_SUGGESTION,
        "sources": [
            {
                "source_type": "ticket",
                "title": "How do I submit a PTO request?",
                "url": "https://yourcompany.zendesk.com/agent/tickets/101",
                "source_id": "ticket_101",
                "score": 0.85,
            }
        ],
        "retrieved_count": 1,
    }


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "chroma_docs" in data
    assert "model" in data


# ---------------------------------------------------------------------------
# /suggest — workflow-tagged ticket
# ---------------------------------------------------------------------------


def test_suggest_workflow_question_returns_suggestion(client: TestClient):
    with patch(
        "backend.routers.suggest.generate_suggestion",
        new_callable=AsyncMock,
        return_value=_mock_suggest_result(),
    ):
        resp = client.post(
            "/suggest",
            json={
                "ticket_id": "101",
                "current_message": "How do I submit a half-day PTO?",
                "ticket_tags": ["workflow-question", "hr"],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_workflow_question"] is True
    assert data["suggestion"] == FAKE_SUGGESTION
    assert len(data["sources"]) == 1


# ---------------------------------------------------------------------------
# /suggest — non-workflow ticket (fast path)
# ---------------------------------------------------------------------------


def test_suggest_non_workflow_ticket_skips_rag(client: TestClient):
    with patch(
        "backend.routers.suggest.generate_suggestion",
        new_callable=AsyncMock,
    ) as mock_gen:
        resp = client.post(
            "/suggest",
            json={
                "ticket_id": "999",
                "current_message": "My billing statement looks wrong",
                "ticket_tags": ["billing", "refund"],
            },
        )
        # RAG should NOT have been called
        mock_gen.assert_not_called()

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_workflow_question"] is False
    assert data["suggestion"] is None
    assert data["sources"] == []


# ---------------------------------------------------------------------------
# /suggest — empty message
# ---------------------------------------------------------------------------


def test_suggest_empty_message_returns_no_suggestion(client: TestClient):
    resp = client.post(
        "/suggest",
        json={
            "ticket_id": "101",
            "current_message": "   ",
            "ticket_tags": ["workflow-question"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_workflow_question"] is True
    assert data["suggestion"] is None


# ---------------------------------------------------------------------------
# /suggest — no tags supplied
# ---------------------------------------------------------------------------


def test_suggest_no_tags_is_fast_path(client: TestClient):
    resp = client.post(
        "/suggest",
        json={
            "ticket_id": "101",
            "current_message": "How do I submit PTO?",
            "ticket_tags": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_workflow_question"] is False


# ---------------------------------------------------------------------------
# /ingest
# ---------------------------------------------------------------------------


def test_ingest_trigger_returns_task_id(client: TestClient):
    with patch(
        "backend.routers.ingest.run_ingestion",
        new_callable=AsyncMock,
    ):
        resp = client.post("/ingest")

    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "started"


def test_ingest_status_unknown_task_returns_404(client: TestClient):
    resp = client.get("/ingest/status/nonexistent-task-id")
    assert resp.status_code == 404
