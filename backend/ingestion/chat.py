"""
Ingest Zendesk Chat (Sunshine Conversations) transcripts tagged with workflow tags.
Tries the Sunshine Conversations API first; falls back to the legacy Zopim Chat API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from backend.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ChatDocument:
    doc_id: str         # "chat_{id}"
    text: str
    title: str
    tags: list[str]
    url: str
    source_type: str = "chat"


async def fetch_workflow_chats(settings: Settings) -> list[ChatDocument]:
    cfg = settings.zendesk
    workflow_tags = settings.workflow.tags
    auth = (f"{cfg.email}/token", cfg.api_token)
    base = cfg.base_url

    async with httpx.AsyncClient(auth=auth, timeout=30) as client:
        # Try Sunshine Conversations first
        docs = await _fetch_sunshine(client, base, workflow_tags)
        if docs is not None:
            return docs
        # Fallback: legacy Zopim Chat API
        return await _fetch_legacy_chat(client, base, workflow_tags)


async def _fetch_sunshine(
    client: httpx.AsyncClient, base: str, workflow_tags: list[str]
) -> list[ChatDocument] | None:
    """Returns None if Sunshine Conversations is not available on this account."""
    documents: list[ChatDocument] = []

    for tag in workflow_tags:
        url = f"{base}/api/v2/conversations"
        params: dict = {"filter[tags]": tag, "page[size]": 100}
        try:
            while url:
                resp = await client.get(url, params=params)
                if resp.status_code == 404:
                    logger.info("Sunshine Conversations API not available, falling back")
                    return None
                resp.raise_for_status()
                data = resp.json()
                for conv in data.get("conversations", []):
                    doc = _sunshine_conv_to_doc(conv, base)
                    if doc:
                        documents.append(doc)
                url = (data.get("links") or {}).get("next")
                params = {}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.warning("Sunshine API error: %s", e)
            return None

    logger.info("Sunshine Conversations: fetched %d chats", len(documents))
    return documents


def _sunshine_conv_to_doc(conv: dict, base: str) -> ChatDocument | None:
    conv_id = conv.get("id", "")
    tags = conv.get("metadata", {}).get("tags", [])
    messages = conv.get("messages", [])

    parts: list[str] = []
    for msg in messages:
        role = "Agent" if msg.get("role") == "appUser" else "Customer"
        text = (msg.get("content") or {}).get("text", "").strip()
        if text:
            parts.append(f"[{role}]: {text}")

    if not parts:
        return None

    return ChatDocument(
        doc_id=f"chat_{conv_id}",
        text="\n".join(parts),
        title=f"Chat conversation {conv_id}",
        tags=tags,
        url=f"{base}/agent/conversations/{conv_id}",
    )


async def _fetch_legacy_chat(
    client: httpx.AsyncClient, base: str, workflow_tags: list[str]
) -> list[ChatDocument]:
    """Zopim / legacy Chat API."""
    documents: list[ChatDocument] = []
    tag_str = " ".join(workflow_tags)

    try:
        url = f"{base}/api/v2/chats/search"
        params: dict = {"q": f"tags:{tag_str}", "count": 200}
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        for chat in data.get("chats", []):
            doc = _legacy_chat_to_doc(chat, base)
            if doc:
                documents.append(doc)
    except httpx.HTTPStatusError as e:
        logger.warning("Legacy Chat API error: %s", e)

    logger.info("Legacy Chat: fetched %d chats", len(documents))
    return documents


def _legacy_chat_to_doc(chat: dict, base: str) -> ChatDocument | None:
    chat_id = chat.get("id", "")
    tags = chat.get("tags", [])
    transcript = chat.get("transcript", [])

    parts: list[str] = []
    for entry in transcript:
        role = "Agent" if entry.get("type") == "agent" else "Customer"
        msg = (entry.get("message") or "").strip()
        if msg:
            parts.append(f"[{role}]: {msg}")

    if not parts:
        return None

    return ChatDocument(
        doc_id=f"chat_{chat_id}",
        text="\n".join(parts),
        title=f"Chat {chat_id}",
        tags=tags,
        url=f"{base}/agent/chats/{chat_id}",
    )
