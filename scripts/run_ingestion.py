"""
CLI script to trigger a full ingestion run.

Usage:
    # Against real Zendesk (requires .env configured):
    python scripts/run_ingestion.py

    # Against local mock server:
    ZENDESK_BASE_URL=http://localhost:9000 python scripts/run_ingestion.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Make sure the project root is on sys.path so backend imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

from backend.config import get_settings
from backend.ingestion.runner import run_ingestion


async def main() -> None:
    settings = get_settings()
    print(f"Starting ingestion against: {settings.zendesk.base_url}")
    print(f"Workflow tags: {settings.workflow.tags}")
    print(f"Embeddings: {settings.embeddings.provider} / {settings.embeddings.local_model}")
    print()

    progress = await run_ingestion(settings)

    print()
    print("=" * 50)
    print("Ingestion complete!")
    print(f"  Tickets   : {progress.tickets}")
    print(f"  Chats     : {progress.chats}")
    print(f"  Articles  : {progress.articles}")
    print(f"  Chunks    : {progress.chunks_stored}")
    print(f"  Errors    : {progress.errors}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
