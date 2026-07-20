"""Golden / composition tests."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from persona_composer import compose, compose_from_manifest
from persona_composer.errors import CompositionError
from persona_composer.models import DEFAULT_OUTPUT_RULES, SkeletonConfig

FIXED_TS = "2026-07-20T15:00:00+00:00"
GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"


def test_identity_alone_valid_xml(identity_path: Path, modules_root: Path) -> None:
    result = compose(
        identity_path,
        [],
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
    )
    # Property: well-formed XML; output_rules always carries today's date
    ET.fromstring(result.prompt_xml)
    assert "<identity" in result.prompt_xml
    assert "<precedence>" in result.prompt_xml
    assert "<output_rules>" in result.prompt_xml
    assert "Today is 2026-07-20;" in result.prompt_xml
    assert "<traits>" not in result.prompt_xml
    assert result.manifest.skeleton_version == "3"
    assert len(result.manifest.modules) == 1


def test_output_rules_module(identity_path: Path, modules_root: Path) -> None:
    result = compose(
        identity_path,
        [modules_root / "output_rules" / "concise.md"],
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
    )
    assert '<output_rules name="Concise">' in result.prompt_xml
    assert "Today is 2026-07-20;" in result.prompt_xml
    assert "fewest words" in result.prompt_xml


def test_output_rules_skeleton_fallback(
    identity_path: Path, modules_root: Path
) -> None:
    result = compose(
        identity_path,
        [],
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
        skeleton=SkeletonConfig(output_rules=DEFAULT_OUTPUT_RULES),
    )
    assert "<output_rules>" in result.prompt_xml
    assert "Today is 2026-07-20;" in result.prompt_xml
    assert DEFAULT_OUTPUT_RULES in result.prompt_xml


def test_golden_full_composition(identity_path: Path, modules_root: Path) -> None:
    extras = [
        modules_root / "speech" / "curt.md",
        modules_root / "roles" / "gatekeeper.md",
        modules_root / "traits" / "territorial.md",
        modules_root / "traits" / "cautious.md",
        modules_root / "relationships" / "ally_bob.md",
        modules_root / "output_rules" / "default.md",
    ]
    result = compose(
        identity_path,
        extras,
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
    )
    expected = (GOLDEN_DIR / "full_prompt.xml").read_text(encoding="utf-8")
    assert result.prompt_xml == expected
    assert len(result.manifest.conflict_rules) == 1
    assert result.manifest.conflict_rules[0]["winner"] == "Territorial"


def test_rewriter_excluded_from_prompt(
    identity_path: Path, modules_root: Path
) -> None:
    result = compose(
        identity_path,
        [modules_root / "speech" / "fancy_rewriter.md"],
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
    )
    assert "Victorian" not in result.prompt_xml
    assert len(result.manifest.rewriter_stack) == 1
    assert result.manifest.rewriter_stack[0].name == "FancyRewriter"


def test_vendor_as_is(identity_path: Path, modules_root: Path) -> None:
    result = compose(
        identity_path,
        [modules_root / "speech" / "caveman.md"],
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
    )
    assert "Speak like cave person" in result.prompt_xml
    assert "imported skill" in result.prompt_xml
    caveman = next(m for m in result.manifest.modules if m.name == "Caveman")
    assert caveman.source_hash is not None
    assert caveman.origin is not None


def test_compose_from_manifest_roundtrip(
    identity_path: Path, modules_root: Path, tmp_path: Path
) -> None:
    result = compose(
        identity_path,
        [modules_root / "traits" / "territorial.md", modules_root / "traits" / "cautious.md"],
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(result.manifest_json(), encoding="utf-8")

    again = compose_from_manifest(
        manifest_path,
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
    )
    assert again.prompt_xml == result.prompt_xml


def test_compose_from_manifest_hash_mismatch(
    identity_path: Path, modules_root: Path, tmp_path: Path
) -> None:
    result = compose(
        identity_path,
        [],
        module_root=modules_root,
        library_root=modules_root,
        timestamp=FIXED_TS,
    )
    data = result.manifest.to_dict()
    data["modules"][0]["hash"] = "deadbeef0000"
    manifest_path = tmp_path / "bad.json"
    import json

    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CompositionError, match="hash mismatch"):
        compose_from_manifest(manifest_path, module_root=modules_root)
