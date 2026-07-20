"""Tests for decompose workflow (no real LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from persona_composer import CompositionError, ValidationError, decompose
from persona_composer.decompose import (
    build_decompose_prompt,
    parse_decomposition_response,
    write_draft_modules,
    ModuleSuggestion,
)


SAMPLE_RESPONSE = {
    "summary": "Split guard into territorial trait and curt speech",
    "remaining_identity_body": "You are the gate guard of Amber Outpost.",
    "suggestions": [
        {
            "type": "trait",
            "name": "Territorial",
            "priority": "high",
            "conflicts": ["Cautious"],
            "body": "Treat strangers near the gate as intrusion until proven otherwise.",
            "rationale": "Behavioral stance",
        },
        {
            "type": "speech",
            "name": "Curt",
            "mode": "prompt",
            "body": "Use short sentences. No small talk.",
            "rationale": "Delivery style",
        },
    ],
}


def test_parse_decomposition_response() -> None:
    summary, remaining, suggestions = parse_decomposition_response(
        json.dumps(SAMPLE_RESPONSE)
    )
    assert "Split" in summary
    assert "gate guard" in remaining
    assert len(suggestions) == 2
    assert suggestions[0].type == "trait"
    assert suggestions[0].priority == "high"
    assert suggestions[1].mode == "prompt"


def test_parse_with_fences() -> None:
    raw = "```json\n" + json.dumps(SAMPLE_RESPONSE) + "\n```"
    _, _, suggestions = parse_decomposition_response(raw)
    assert len(suggestions) == 2


def test_decompose_with_llm_response(tmp_path: Path, modules_root: Path) -> None:
    out = tmp_path / "drafts"
    result = decompose(
        modules_root / "identity" / "guard.md",
        llm_response=json.dumps(SAMPLE_RESPONSE),
        out_dir=out,
        write_drafts=True,
    )
    assert result.source_kind == "identity"
    assert len(result.suggestions) == 2
    assert any(p.name.startswith("identity_") for p in result.draft_paths)
    trait = out / "trait" / "Territorial.md"
    assert trait.is_file()
    text = trait.read_text(encoding="utf-8")
    assert "type: trait" in text
    assert "priority: high" in text


def test_decompose_requires_llm(modules_root: Path) -> None:
    with pytest.raises(CompositionError, match="llm_call"):
        decompose(modules_root / "identity" / "guard.md")


def test_decompose_llm_call_injected(modules_root: Path, tmp_path: Path) -> None:
    def fake(prompt: str) -> str:
        assert "SOURCE START" in prompt
        return json.dumps(SAMPLE_RESPONSE)

    result = decompose(
        modules_root / "identity" / "guard.md",
        llm_call=fake,
        out_dir=tmp_path / "d",
    )
    assert len(result.suggestions) == 2


def test_build_prompt_skill_kind() -> None:
    prompt = build_decompose_prompt(
        source_text="Speak like cave person.",
        source_kind="skill",
        provenance="vendor/caveman/SKILL.md",
    )
    assert "foreign/vendored skill" in prompt
    assert "Speak like cave person" in prompt


def test_write_draft_extracted_provenance(tmp_path: Path) -> None:
    paths = write_draft_modules(
        [
            ModuleSuggestion(
                type="speech",
                name="CavemanLite",
                body="Short words only.",
                mode="prompt",
            )
        ],
        tmp_path,
        source="vendor/caveman/SKILL.md",
        origin="https://example.com",
    )
    text = paths[0].read_text(encoding="utf-8")
    assert "adaptation: extracted" in text
    assert "source: vendor/caveman/SKILL.md" in text


def test_invalid_json() -> None:
    with pytest.raises(ValidationError, match="invalid JSON"):
        parse_decomposition_response("not json")
