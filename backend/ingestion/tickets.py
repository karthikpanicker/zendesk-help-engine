"""
Ingest Zendesk tickets and their comments that carry workflow-related tags.
Ticket comments are concatenated into a single document per ticket.
Talk call transcripts are captured here too — Talk auto-creates a ticket comment
with the transcript text, so no separate Talk API call is needed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from backend.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class TicketDocument:
    doc_id: str          # "ticket_{id}"
    text: str
    title: str
    tags: list[str]
    url: str
    source_type: str = "ticket"


async def _get_json(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


async def fetch_workflow_tickets(settings: Settings) -> list[TicketDocument]:
    """
    Search Zendesk for tickets tagged with any workflow tag and return them
    as TicketDocument objects (one per ticket, with all comments joined).
    """
    cfg = settings.zendesk
    workflow_tags = settings.workflow.tags
    max_tickets = settings.ingestion.max_tickets

    auth = (f"{cfg.email}/token", cfg.api_token)
    base = cfg.base_url

    # Build tag query — Zendesk search supports multiple tag: filters OR'd together
    tag_query = " ".join(f"tags:{t}" for t in workflow_tags)
    search_query = f"type:ticket {tag_query}"

    documents: list[TicketDocument] = []
    page_url = f"{base}/api/v2/search.json"
    params: dict = {"query": search_query, "sort_by": "created_at", "sort_order": "desc"}

    async with httpx.AsyncClient(auth=auth, timeout=30) as client:
        while page_url and len(documents) < max_tickets:
            data = await _get_json(client, page_url, params)
            tickets = data.get("results", [])
            params = {}  # next_page already includes params

            ticket_tasks = [
                _build_ticket_doc(client, base, ticket)
                for ticket in tickets
                if ticket.get("type") == "ticket"
            ]
            batch = await asyncio.gather(*ticket_tasks, return_exceptions=True)
            for item in batch:
                if isinstance(item, Exception):
                    logger.warning("Skipping ticket due to error: %s", item)
                    continue
                if item is not None:
                    documents.append(item)

            page_url = data.get("next_page")
            logger.info("Fetched %d tickets so far", len(documents))

    logger.info("Total workflow tickets fetched: %d", len(documents))
    return documents


async def _build_ticket_doc(
    client: httpx.AsyncClient, base: str, ticket: dict
) -> TicketDocument | None:
    ticket_id = ticket["id"]
    subject = ticket.get("subject") or f"Ticket #{ticket_id}"
    tags = ticket.get("tags") or []
    url = f"{base}/agent/tickets/{ticket_id}"

    try:
        comments_data = await _get_json(client, f"{base}/api/v2/tickets/{ticket_id}/comments.json")
    except httpx.HTTPStatusError as e:
        logger.warning("Could not fetch comments for ticket %s: %s", ticket_id, e)
        return None

    parts = [f"[TICKET #{ticket_id}] {subject}"]
    for comment in comments_data.get("comments", []):
        if not comment.get("public", True):
            continue
        body = (comment.get("body") or "").strip()
        if body:
            author_type = "Agent" if comment.get("author_id") else "Customer"
            parts.append(f"[{author_type}]: {body}")

    text = "\n\n".join(parts)
    return TicketDocument(
        doc_id=f"ticket_{ticket_id}",
        text=text,
        title=subject,
        tags=tags,
        url=url,
    )
