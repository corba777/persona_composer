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
        "Gemini 3.5 Flash (Vertex)",
        "vertex_gemini",
        "gemini-3.5-flash",
        "global",
    ),
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
        "Claude Opus 4.6 (Vertex Model Garden)",
        "vertex_claude",
        "claude-opus-4-6",
        "global",
    ),
    ModelChoice(
        "Claude Sonnet 4.6 (Vertex Model Garden)",
        "vertex_claude",
        "claude-sonnet-4-6",
        "global",
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

    # Claude model ids must use AnthropicVertex (publishers/anthropic), not the
    # Gemini client (publishers/google) — otherwise Vertex returns 404 NOT_FOUND.
    mid = model_id.strip().lower()
    if provider == "vertex_gemini" and mid.startswith("claude"):
        provider = "vertex_claude"
    if provider == "vertex_claude" and mid.startswith("gemini"):
        raise ValueError(
            f"Model {model_id!r} is Gemini — select a Gemini preset / "
            f"provider vertex_gemini, not vertex_claude"
        )

    if provider == "vertex_gemini":
        if not project.strip():
            raise ValueError("GCP project id is required for Vertex Gemini")
        default_loc = (
            "global"
            if "3." in model_id or model_id.startswith("gemini-3")
            else "us-central1"
        )
        return _generate_vertex_gemini(
            project=project,
            location=location or default_loc,
            model_id=model_id,
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "vertex_claude":
        if not project.strip():
            raise ValueError("GCP project id is required for Vertex Claude")
        # 4.6 aliases prefer global; older dated ids are often regional.
        default_claude_loc = (
            "global"
            if mid.endswith("-4-6") or mid.endswith("4.6") or "4-6" in mid
            else "us-east5"
        )
        return _generate_vertex_claude(
            project=project,
            location=location or default_claude_loc,
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

    # Gemini 2.5/3.x thinking shares the output budget; keep a floor for demos.
    out_tokens = (
        max(max_tokens, 4096)
        if "2.5" in model_id or "3." in model_id or model_id.startswith("gemini-3")
        else max_tokens
    )

    attempts: list[tuple[str, str, bool, float]] = [
        # (label, system_text, with_thinking, temperature)
        (
            "wrapped+think",
            _gemini_wrap_system(system_prompt),
            True,
            temperature,
        ),
        (
            "wrapped",
            _gemini_wrap_system(system_prompt),
            False,
            temperature,
        ),
        # XML angle brackets trigger spurious tool-call decoding on Gemini 3.x
        # (finish_reason=MALFORMED_FUNCTION_CALL). Flatten tags on last tries.
        (
            "flattened",
            _gemini_wrap_system(_gemini_flatten_xml_tags(system_prompt)),
            False,
            min(temperature, 0.4),
        ),
        (
            "flattened+inline",
            _gemini_inline_system(
                _gemini_flatten_xml_tags(system_prompt), user_message
            ),
            False,
            0.2,
        ),
    ]

    last_detail = ""
    for _label, sys_text, with_thinking, temp in attempts:
        # Last attempt puts instructions in the user turn (no system_instruction).
        use_system = not sys_text.startswith("__INLINE__:")
        if use_system:
            contents: object = user_message
            system_instruction = sys_text
        else:
            contents = sys_text.removeprefix("__INLINE__:")
            system_instruction = None

        config_kwargs: dict = {
            "temperature": temp,
            "max_output_tokens": out_tokens,
            "tool_config": types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.NONE,
                )
            ),
        }
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction
        if with_thinking:
            thinking = _gemini_thinking_config(types, model_id)
            if thinking is not None:
                config_kwargs["thinking_config"] = thinking

        response = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        text_out = _gemini_response_text(response)
        if text_out:
            return text_out
        last_detail = _gemini_empty_detail(response)
        # Only keep cascading on tool-malformed / empty; other finishes (safety) stop.
        if "MALFORMED_FUNCTION_CALL" not in last_detail and "no candidates" not in last_detail:
            break

    raise RuntimeError(last_detail or "Gemini returned an empty response")


def _gemini_wrap_system(system_prompt: str) -> str:
    """Frame composed XML as character instructions, not tools/APIs."""
    return (
        "You are roleplaying a character for a text demo.\n"
        "The block below is CHARACTER / PERSONA instructions only "
        "(structured markup for sections). It is NOT a tool schema, NOT an API, "
        "and NOT a request to call functions.\n"
        "Do not emit function calls, tool calls, or JSON tool payloads. "
        "Reply with plain in-character text only.\n\n"
        "----- BEGIN PERSONA INSTRUCTIONS -----\n"
        f"{system_prompt.rstrip()}\n"
        "----- END PERSONA INSTRUCTIONS -----"
    )


def _gemini_flatten_xml_tags(system_prompt: str) -> str:
    """Replace <tag> with [tag] so Gemini 3.x does not treat markup as tools."""
    import re

    def _repl(match: re.Match[str]) -> str:
        slash = match.group(1) or ""
        name = match.group(2)
        return f"[{slash}{name}]"

    return re.sub(r"<(/)?([A-Za-z0-9_:-]+)(\s[^>]*)?>", _repl, system_prompt)


def _gemini_inline_system(system_prompt: str, user_message: str) -> str:
    """Put persona + user in one user message (marked for caller)."""
    return (
        "__INLINE__:"
        + _gemini_wrap_system(system_prompt)
        + "\n\n----- USER MESSAGE -----\n"
        + user_message.strip()
    )


def _gemini_thinking_config(types: object, model_id: str) -> object | None:
    """Bound thinking so playground replies are not empty (MAX_TOKENS)."""
    ThinkingConfig = getattr(types, "ThinkingConfig", None)
    if ThinkingConfig is None:
        return None
    mid = model_id.lower()

    # Gemini 3.x: thinking_level enum (do not mix with thinking_budget).
    if "gemini-3" in mid or mid.startswith("3."):
        ThinkingLevel = getattr(types, "ThinkingLevel", None)
        if ThinkingLevel is not None:
            for attr in ("MINIMAL", "LOW"):
                level = getattr(ThinkingLevel, attr, None)
                if level is None:
                    continue
                try:
                    return ThinkingConfig(thinking_level=level)
                except TypeError:
                    continue
        for level in ("MINIMAL", "minimal", "LOW", "low"):
            try:
                return ThinkingConfig(thinking_level=level)
            except Exception:
                continue
        return None

    # Gemini 2.5 Flash: numeric budget 0 ≈ off.
    if "2.5" in mid and "flash" in mid:
        try:
            return ThinkingConfig(thinking_budget=0)
        except TypeError:
            return None

    if "2.5" in mid:
        try:
            return ThinkingConfig(thinking_budget=1024)
        except TypeError:
            return None
    return None


def _gemini_response_text(response: object) -> str:
    text = getattr(response, "text", None)
    if text:
        return text
    parts: list[str] = []
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", None):
                continue
            if getattr(part, "text", None):
                parts.append(part.text)
    return "\n".join(parts).strip()


def _gemini_empty_detail(response: object) -> str:
    bits: list[str] = ["Gemini returned an empty response"]
    cands = getattr(response, "candidates", None) or []
    if not cands:
        bits.append("(no candidates)")
    finish = ""
    for i, cand in enumerate(cands):
        fr = getattr(cand, "finish_reason", None)
        if fr is not None:
            finish = str(fr)
            bits.append(f"candidate[{i}].finish_reason={fr}")
    pf = getattr(response, "prompt_feedback", None)
    if pf is not None:
        br = getattr(pf, "block_reason", None)
        if br is not None:
            bits.append(f"prompt_feedback.block_reason={br}")
    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        thoughts = getattr(usage, "thoughts_token_count", None)
        out = getattr(usage, "candidates_token_count", None)
        if thoughts is not None:
            bits.append(f"thoughts_token_count={thoughts}")
        if out is not None:
            bits.append(f"candidates_token_count={out}")
    if "MALFORMED_FUNCTION_CALL" in finish:
        bits.append(
            "Tip: Gemini 3.x often misreads XML persona tags as tool calls. "
            "Playground now wraps/flattens the system prompt and retries; "
            "restart Streamlit. If it persists, try Gemini 2.5 Flash preset."
        )
    else:
        bits.append(
            "Tip: for gemini-3.5-flash use Location=global, Max tokens≥4096; "
            "thinking can consume the output budget (finish_reason=MAX_TOKENS)."
        )
    return " — ".join(bits)


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

    # Pass composed XML as-is (same as consuming games). No language heuristics —
    # speech modules own their register; the playground is not a language compiler.
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
