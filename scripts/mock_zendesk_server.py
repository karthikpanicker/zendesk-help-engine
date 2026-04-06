"""
Mock Zendesk API server for local development and testing.
Serves fixture JSON so you can run the ingestion pipeline without a real Zendesk account.

Usage:
    uvicorn scripts.mock_zendesk_server:app --port 9000

Then run ingestion against it:
    ZENDESK_BASE_URL=http://localhost:9000 python scripts/run_ingestion.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Zendesk API")

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

COMMENTS_MAP = {
    "101": "comments_101.json",
    "102": "comments_102.json",
    "103": "comments_103.json",
}


def _load(filename: str) -> dict:
    with open(FIXTURES / filename) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Tickets search
# ---------------------------------------------------------------------------


@app.get("/api/v2/search.json")
async def search_tickets(request: Request):
    """Return all mock workflow tickets regardless of query params."""
    return JSONResponse(_load("tickets.json"))


# ---------------------------------------------------------------------------
# Ticket comments
# ---------------------------------------------------------------------------


@app.get("/api/v2/tickets/{ticket_id}/comments.json")
async def ticket_comments(ticket_id: str):
    fixture_file = COMMENTS_MAP.get(ticket_id)
    if fixture_file is None:
        return JSONResponse({"comments": []})
    return JSONResponse(_load(fixture_file))


# ---------------------------------------------------------------------------
# Help Center articles
# ---------------------------------------------------------------------------


@app.get("/api/v2/help_center/articles")
async def articles():
    return JSONResponse(_load("articles.json"))


# ---------------------------------------------------------------------------
# Legacy Chat search (Zopim)
# ---------------------------------------------------------------------------


@app.get("/api/v2/chats/search")
async def chats_search():
    return JSONResponse(_load("chats.json"))


# ---------------------------------------------------------------------------
# Sunshine Conversations — return 404 to trigger fallback to legacy chat
# ---------------------------------------------------------------------------


@app.get("/api/v2/conversations")
async def sunshine_conversations():
    return JSONResponse({"error": "not found"}, status_code=404)
