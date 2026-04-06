"""
Central settings loaded from config/config.yaml + environment variables.
Environment variables override YAML values; ${VAR} placeholders in YAML are expanded.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings

ROOT = Path(__file__).parent.parent


def _expand_env(value: str) -> str:
    """Replace ${VAR} placeholders with environment variable values."""
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def _expand_dict(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _expand_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_dict(v) for v in obj]
    if isinstance(obj, str):
        return _expand_env(obj)
    return obj


def _load_yaml() -> dict:
    config_path = ROOT / "config" / "config.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return _expand_dict(raw)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ZendeskConfig(BaseModel):
    subdomain: str
    email: str
    api_token: str

    @property
    def base_url(self) -> str:
        # Allow override via env var (useful for pointing at mock server)
        return os.environ.get(
            "ZENDESK_BASE_URL", f"https://{self.subdomain}.zendesk.com"
        )


class AnthropicConfig(BaseModel):
    api_key: str
    model: str = "claude-sonnet-4-6"


class EmbeddingsConfig(BaseModel):
    provider: str = "local"          # "local" | "voyage"
    local_model: str = "BAAI/bge-base-en-v1.5"
    voyage_model: str = "voyage-3"
    voyage_api_key: str = ""


class WorkflowConfig(BaseModel):
    tags: list[str]


class IngestionConfig(BaseModel):
    batch_size: int = 50
    chunk_size: int = 512
    chunk_overlap: int = 64
    max_tickets: int = 2000
    max_articles: int = 500


class RAGConfig(BaseModel):
    top_k: int = 5
    min_score: float = 0.35
    suggestion_max_tokens: int = 300


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]


class ChromaConfig(BaseModel):
    persist_directory: str = "./data/chroma"
    collection_name: str = "workflow_kb"


# ---------------------------------------------------------------------------
# Root settings object
# ---------------------------------------------------------------------------


class Settings(BaseModel):
    zendesk: ZendeskConfig
    anthropic: AnthropicConfig
    embeddings: EmbeddingsConfig
    workflow: WorkflowConfig
    ingestion: IngestionConfig
    rag: RAGConfig
    server: ServerConfig
    chroma: ChromaConfig


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data = _load_yaml()
    return Settings(**data)
