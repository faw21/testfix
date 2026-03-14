"""LLM provider abstraction for testfix."""

from __future__ import annotations

import os
from typing import Optional

# ── Provider interface ────────────────────────────────────────────────────────

def call_llm(
    system: str,
    user: str,
    provider: str = "claude",
    model: Optional[str] = None,
) -> str:
    """Call the configured LLM and return the response text."""
    if provider == "claude":
        return _call_claude(system, user, model or "claude-haiku-4-5")
    if provider == "openai":
        return _call_openai(system, user, model or "gpt-4o-mini")
    if provider == "ollama":
        return _call_ollama(system, user, model or "qwen2.5:1.5b")
    raise ValueError(f"Unknown provider: {provider!r}. Use 'claude', 'openai', or 'ollama'.")


def _call_claude(system: str, user: str, model: str) -> str:
    import anthropic  # type: ignore
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


def _call_openai(system: str, user: str, model: str) -> str:
    from openai import OpenAI  # type: ignore
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=model,
        max_completion_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def _call_ollama(system: str, user: str, model: str) -> str:
    from openai import OpenAI  # type: ignore
    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""
