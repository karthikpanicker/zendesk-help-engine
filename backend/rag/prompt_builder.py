"""
Builds the system + user prompt for Claude from retrieved knowledge chunks.
"""

from __future__ import annotations

from dataclasses import dataclass


SYSTEM_PROMPT = """\
You are a workflow assistant helping a Zendesk support agent answer a customer's question in real time.

You will be given:
1. The customer's current message
2. Relevant knowledge retrieved from past support tickets and Help Center articles

Your job is to provide a concise, actionable suggestion the agent can use to respond.
Focus on workflow steps, process clarifications, and procedure guidance.

Rules:
- Do NOT fabricate steps or invent policy details not present in the retrieved knowledge.
- If the retrieved knowledge does not contain a clear answer, say so briefly and suggest escalation.
- Keep your response to 2–4 sentences OR a short numbered list if steps are involved.
- Write in a helpful, professional tone the agent can use directly or adapt.
- Do not address the customer directly — you are advising the agent.\
"""


@dataclass
class Prompt:
    system: str
    user: str


def build_prompt(current_message: str, chunks: list[dict]) -> Prompt:
    """
    Construct the Claude prompt from the customer's message and retrieved chunks.
    """
    knowledge_section = _format_chunks(chunks)

    user_content = (
        f'Customer message: "{current_message}"\n\n'
        f"Relevant knowledge:\n---\n{knowledge_section}\n---\n\n"
        "Suggested agent response:"
    )

    return Prompt(system=SYSTEM_PROMPT, user=user_content)


def _format_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "(No relevant knowledge found)"

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.get("metadata", {})
        source_type = meta.get("source_type", "unknown")
        title = meta.get("title", "Untitled")
        text = chunk.get("text", "")
        parts.append(f"[{i}] Source: {source_type} | {title}\n{text}")

    return "\n\n".join(parts)
