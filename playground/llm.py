"""Vertex AI model callers for the Streamlit playground."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Provider = Literal["gemini", "claude"]


@dataclass(frozen=True)
class ModelChoice:
    label: str
    provider: Provider
    model_id: str
    default_location: str


# Curated presets — override IDs in the UI if your project has different versions.
MODEL_PRESETS: list[ModelChoice] = [
    ModelChoice(
        "Gemini 2.5 Flash",
        "gemini",
        "gemini-2.5-flash",
        "us-central1",
    ),
    ModelChoice(
        "Gemini 2.5 Pro",
        "gemini",
        "gemini-2.5-pro",
        "us-central1",
    ),
    ModelChoice(
        "Claude Sonnet 4 (Model Garden)",
        "claude",
        "claude-sonnet-4@20250514",
        "us-east5",
    ),
    ModelChoice(
        "Claude 3.5 Sonnet v2 (Model Garden)",
        "claude",
        "claude-3-5-sonnet-v2@20241022",
        "us-east5",
    ),
    ModelChoice(
        "Claude 3.5 Haiku (Model Garden)",
        "claude",
        "claude-3-5-haiku@20241022",
        "us-east5",
    ),
]


def generate(
    *,
    provider: Provider,
    project: str,
    location: str,
    model_id: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    if not project.strip():
        raise ValueError("GCP project id is required")
    if not user_message.strip():
        raise ValueError("User message is empty")

    if provider == "gemini":
        return _generate_gemini(
            project=project,
            location=location,
            model_id=model_id,
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "claude":
        return _generate_claude(
            project=project,
            location=location,
            model_id=model_id,
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unknown provider: {provider}")


def _generate_gemini(
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
    # Fallback: concatenate parts
    parts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None):
                parts.append(part.text)
    if not parts:
        raise RuntimeError("Gemini returned an empty response")
    return "\n".join(parts)


def _generate_claude(
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
    chunks: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
        elif hasattr(block, "text"):
            chunks.append(block.text)
    if not chunks:
        raise RuntimeError("Claude returned an empty response")
    return "\n".join(chunks)
