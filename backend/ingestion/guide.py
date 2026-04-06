"""
Ingest Zendesk Help Center (Guide) articles.
Articles are filtered by label_names overlapping with workflow tags,
or by section/category name containing a workflow keyword.
HTML is stripped to plain text before chunking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

from backend.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ArticleDocument:
    doc_id: str         # "article_{id}"
    text: str
    title: str
    tags: list[str]
    url: str
    source_type: str = "article"


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


async def fetch_workflow_articles(settings: Settings) -> list[ArticleDocument]:
    cfg = settings.zendesk
    workflow_tags = settings.workflow.tags
    max_articles = settings.ingestion.max_articles
    auth = (f"{cfg.email}/token", cfg.api_token)
    base = cfg.base_url

    # Build a set of lowercase keyword substrings for section-name matching
    tag_keywords = {t.replace("-", " ").replace("_", " ").lower() for t in workflow_tags}

    documents: list[ArticleDocument] = []
    page_url = f"{base}/api/v2/help_center/articles"
    params: dict = {"per_page": 100, "sort_by": "updated_at"}

    async with httpx.AsyncClient(auth=auth, timeout=30) as client:
        while page_url and len(documents) < max_articles:
            try:
                resp = await client.get(page_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning("Guide API error: %s", e)
                break

            for article in data.get("articles", []):
                if not _is_workflow_relevant(article, workflow_tags, tag_keywords):
                    continue
                doc = _article_to_doc(article, base)
                if doc:
                    documents.append(doc)
                if len(documents) >= max_articles:
                    break

            page_url = data.get("next_page")
            params = {}
            logger.info("Fetched %d articles so far", len(documents))

    logger.info("Total workflow articles fetched: %d", len(documents))
    return documents


def _is_workflow_relevant(
    article: dict, workflow_tags: list[str], tag_keywords: set[str]
) -> bool:
    # Check label_names (Zendesk Guide labels)
    label_names = {(ln or "").lower() for ln in article.get("label_names", [])}
    tag_set = {t.lower() for t in workflow_tags}
    if label_names & tag_set:
        return True

    # Check section name / title substring match
    title = (article.get("title") or "").lower()
    for kw in tag_keywords:
        if kw in title:
            return True

    return False


def _article_to_doc(article: dict, base: str) -> ArticleDocument | None:
    article_id = article["id"]
    title = article.get("title") or f"Article {article_id}"
    body_html = article.get("body") or ""
    body_text = _strip_html(body_html).strip()

    if not body_text:
        return None

    text = f"{title}\n\n{body_text}"
    url = article.get("html_url") or f"{base}/hc/articles/{article_id}"
    labels = article.get("label_names") or []

    return ArticleDocument(
        doc_id=f"article_{article_id}",
        text=text,
        title=title,
        tags=labels,
        url=url,
    )
