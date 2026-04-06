"""
Zendesk Workflow Suggestion Engine — FastAPI application entrypoint.

Run locally:
    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.routers import health, ingest, suggest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

settings = get_settings()

app = FastAPI(
    title="Zendesk Workflow Suggestion Engine",
    description=(
        "Real-time AI suggestions for support agents handling workflow-related "
        "customer questions. Powered by ChromaDB + Claude."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(suggest.router)
app.include_router(ingest.router)
