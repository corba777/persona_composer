"""LLM backends for the Streamlit playground: Vertex, OpenAI, Anthropic."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Provider = Literal["vertex_gemini", "vertex_claude", "openai", "anthropic"]


@dataclass(frozen=True)
class ModelChoice:
    label: str
    provider: Provider
    model_id: str
    default_location: str = ""


@dataclass(frozen=True)
class ApiAvailability:
    openai: bool
    anthropic: bool
    openai_key_set: bool
    anthropic_key_set: bool


def load_env(repo_root: Path | None = None) -> None:
    """Load `.env` from repo root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = repo_root or Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env", override=False)


def api_availability() -> ApiAvailability:
    openai_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    return ApiAvailability(
        openai=openai_key,
        anthropic=anthropic_key,
        openai_key_set=openai_key,
        anthropic_key_set=anthropic_key,
    )


VERTEX_PRESETS: list[ModelChoice] = [
    ModelChoice(
        "Gemini 2.5 Flash (Vertex)",
        "vertex_gemini",
        "gemini-2.5-flash",
        "us-central1",
    ),
    ModelChoice(
        "Gemini 2.5 Pro (Vertex)",
        "vertex_gemini",
        "gemini-2.5-pro",
        "us-central1",
    ),
    ModelChoice(
        "Claude Sonnet 4 (Vertex Model Garden)",
        "vertex_claude",
        "claude-sonnet-4@20250514",
        "us-east5",
    ),
    ModelChoice(
        "Claude 3.5 Sonnet v2 (Vertex Model Garden)",
        "vertex_claude",
        "claude-3-5-sonnet-v2@20241022",
        "us-east5",
    ),
    ModelChoice(
        "Claude 3.5 Haiku (Vertex Model Garden)",
        "vertex_claude",
        "claude-3-5-haiku@20241022",
        "us-east5",
    ),
]

OPENAI_PRESETS: list[ModelChoice] = [
    ModelChoice("GPT-4.1 (OpenAI)", "openai", "gpt-4.1"),
    ModelChoice("GPT-4.1 mini (OpenAI)", "openai", "gpt-4.1-mini"),
    ModelChoice("GPT-4o (OpenAI)", "openai", "gpt-4o"),
    ModelChoice("o4-mini (OpenAI)", "openai", "o4-mini"),
]

ANTHROPIC_PRESETS: list[ModelChoice] = [
    ModelChoice("Claude Sonnet 4 (Anthropic API)", "anthropic", "claude-sonnet-4-20250514"),
    ModelChoice(
        "Claude 3.5 Sonnet (Anthropic API)",
        "anthropic",
        "claude-3-5-sonnet-20241022",
    ),
    ModelChoice(
        "Claude 3.5 Haiku (Anthropic API)",
        "anthropic",
        "claude-3-5-haiku-20241022",
    ),
]


def available_presets(avail: ApiAvailability | None = None) -> list[ModelChoice]:
    """Vertex always; OpenAI / Anthropic API only when keys are in the environment."""
    avail = avail or api_availability()
    presets = list(VERTEX_PRESETS)
    if avail.openai:
        presets.extend(OPENAI_PRESETS)
    if avail.anthropic:
        presets.extend(ANTHROPIC_PRESETS)
    return presets


# Back-compat alias used by older imports
MODEL_PRESETS = VERTEX_PRESETS


def is_vertex(provider: Provider) -> bool:
    return provider in ("vertex_gemini", "vertex_claude")


def generate(
    *,
    provider: Provider,
    model_id: str,
    system_prompt: str,
    user_message: str,
    project: str = "",
    location: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    if not user_message.strip():
        raise ValueError("User message is empty")

    if provider == "vertex_gemini":
        if not project.strip():
            raise ValueError("GCP project id is required for Vertex Gemini")
        return _generate_vertex_gemini(
            project=project,
            location=location or "us-central1",
            model_id=model_id,
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "vertex_claude":
        if not project.strip():
            raise ValueError("GCP project id is required for Vertex Claude")
        return _generate_vertex_claude(
            project=project,
            location=location or "us-east5",
            model_id=model_id,
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "openai":
        return _generate_openai(
            model_id=model_id,
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "anthropic":
        return _generate_anthropic_api(
            model_id=model_id,
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unknown provider: {provider}")


def _generate_vertex_gemini(
    *,
    project: str,
    location: str,
    model_id: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, project=project, location=location)
    response = client.models.generate_content(
        model=model_id,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    text = getattr(response, "text", None)
    if text:
        return text
    parts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None):
                parts.append(part.text)
    if not parts:
        raise RuntimeError("Gemini returned an empty response")
    return "\n".join(parts)


def _generate_vertex_claude(
    *,
    project: str,
    location: str,
    model_id: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    from anthropic import AnthropicVertex

    client = AnthropicVertex(project_id=project, region=location)
    message = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return _anthropic_text(message)


def _generate_openai(
    *,
    model_id: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENAI_API_KEY is not set (add it to .env)")

    from openai import OpenAI

    client = OpenAI(api_key=key)
    # Newer models (o-series) may reject temperature; fall back without it.
    kwargs: dict = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_completion_tokens": max_tokens,
    }
    try:
        response = client.chat.completions.create(
            **kwargs,
            temperature=temperature,
        )
    except Exception:
        response = client.chat.completions.create(**kwargs)

    choice = response.choices[0].message.content if response.choices else None
    if not choice:
        raise RuntimeError("OpenAI returned an empty response")
    return choice


def _generate_anthropic_api(
    *,
    model_id: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise ValueError("ANTHROPIC_API_KEY is not set (add it to .env)")

    from anthropic import Anthropic

    client = Anthropic(api_key=key)
    message = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return _anthropic_text(message)


def _anthropic_text(message: object) -> str:
    chunks: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
        elif hasattr(block, "text"):
            chunks.append(block.text)
    if not chunks:
        raise RuntimeError("Claude returned an empty response")
    return "\n".join(chunks)
