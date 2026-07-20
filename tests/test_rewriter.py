"""Tests for rewriter pipeline (stub LLM, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from persona_composer import (
    ValidationError,
    apply_rewriters,
    apply_rewriters_from_manifest,
    apply_rewriters_from_paths,
    compose,
)
from persona_composer.parse import parse_module


def _stub(system: str, user: str) -> str:
    body = user
    if "---\n" in user:
        parts = user.split("---\n")
        if len(parts) >= 2:
            body = parts[1].rsplit("\n---", 1)[0]
    return f"STYLED:{body.strip()}"


def test_apply_rewriter_module(modules_root: Path) -> None:
    mod = parse_module(
        modules_root / "speech" / "fancy_rewriter.md", module_root=modules_root
    )
    result = apply_rewriters("Hello gate.", [mod], llm_call=_stub)
    assert result.text.startswith("STYLED:")
    assert "Hello gate." in result.text
    assert len(result.steps) == 1
    assert result.steps[0].module_name == "FancyRewriter"


def test_skips_prompt_mode_speech(modules_root: Path) -> None:
    curt = parse_module(modules_root / "speech" / "curt.md", module_root=modules_root)
    fancy = parse_module(
        modules_root / "speech" / "fancy_rewriter.md", module_root=modules_root
    )
    result = apply_rewriters("Hi", [curt, fancy], llm_call=_stub)
    assert len(result.steps) == 1
    assert result.steps[0].module_name == "FancyRewriter"


def test_from_paths(modules_root: Path) -> None:
    result = apply_rewriters_from_paths(
        "Plain text.",
        [modules_root / "speech" / "fancy_rewriter.md"],
        llm_call=_stub,
        module_root=modules_root,
    )
    assert "STYLED:" in result.text


def test_from_paths_requires_rewriter(modules_root: Path) -> None:
    with pytest.raises(ValidationError, match="mode=rewriter"):
        apply_rewriters_from_paths(
            "x",
            [modules_root / "speech" / "curt.md"],
            llm_call=_stub,
            module_root=modules_root,
        )


def test_manifest_stack_roundtrip(modules_root: Path) -> None:
    composed = compose(
        modules_root / "identity" / "guard.md",
        [modules_root / "speech" / "fancy_rewriter.md"],
        module_root=modules_root,
        library_root=modules_root,
    )
    assert len(composed.manifest.rewriter_stack) == 1
    assert "Victorian" not in composed.prompt_xml

    rewritten = apply_rewriters_from_manifest(
        "The traveler waits.",
        composed.manifest,
        llm_call=_stub,
        module_root=modules_root,
    )
    assert "STYLED:" in rewritten.text
    assert "traveler" in rewritten.text


def test_empty_manifest_stack_noop(modules_root: Path) -> None:
    composed = compose(
        modules_root / "identity" / "guard.md",
        [],
        module_root=modules_root,
        library_root=modules_root,
    )
    out = apply_rewriters_from_manifest(
        "unchanged",
        composed.manifest,
        llm_call=_stub,
        module_root=modules_root,
    )
    assert out.text == "unchanged"
    assert out.steps == []
