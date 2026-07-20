"""Validation rule fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from persona_composer import compose
from persona_composer.errors import ValidationError
from persona_composer.parse import parse_module


def test_identity_arg_must_be_identity_type(modules_root: Path) -> None:
    trait = parse_module(
        modules_root / "traits" / "territorial.md", module_root=modules_root
    )
    with pytest.raises(ValidationError, match="identity"):
        compose(trait, [], module_root=modules_root)


def test_no_identity_via_validate(modules_root: Path) -> None:
    from persona_composer.validate import validate_modules
    from persona_composer.parse import parse_module

    trait = parse_module(
        modules_root / "traits" / "territorial.md", module_root=modules_root
    )
    with pytest.raises(ValidationError, match="no identity"):
        validate_modules([trait], library_trait_names=None)


def test_two_identities(modules_root: Path) -> None:
    with pytest.raises(ValidationError, match="more than one identity"):
        compose(
            modules_root / "identity" / "twin_a.md",
            [modules_root / "identity" / "twin_b.md"],
            module_root=modules_root,
            library_root=modules_root,
        )


def test_unknown_type(modules_root: Path) -> None:
    with pytest.raises(ValidationError, match="unknown type"):
        parse_module(modules_root / "bad" / "unknown_type.md")


def test_duplicate_trait_name(modules_root: Path, tmp_path: Path) -> None:
    dup = tmp_path / "dup.md"
    dup.write_text(
        (modules_root / "traits" / "territorial.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="duplicate name"):
        compose(
            modules_root / "identity" / "guard.md",
            [modules_root / "traits" / "territorial.md", dup],
            module_root=modules_root,
            library_root=modules_root,
        )


def test_equal_priority_mutual_conflict(modules_root: Path) -> None:
    with pytest.raises(ValidationError, match="equal priority"):
        compose(
            modules_root / "identity" / "guard.md",
            [
                modules_root / "traits" / "stubborn.md",
                modules_root / "traits" / "flexible.md",
            ],
            module_root=modules_root,
            library_root=modules_root,
        )


def test_one_sided_conflict_warns_no_rule(modules_root: Path) -> None:
    result = compose(
        modules_root / "identity" / "guard.md",
        [
            modules_root / "traits" / "territorial.md",
            modules_root / "traits" / "one_sided.md",
        ],
        module_root=modules_root,
        library_root=modules_root,
    )
    assert result.manifest.conflict_rules == []
    assert any("incomplete conflict" in w for w in result.manifest.warnings)


def test_unknown_conflict_name_warns(modules_root: Path) -> None:
    result = compose(
        modules_root / "identity" / "guard.md",
        [modules_root / "traits" / "typo_conflict.md"],
        module_root=modules_root,
        library_root=modules_root,
    )
    assert any("DoesNotExist" in w for w in result.manifest.warnings)


def test_ablation_no_warning_for_inactive_partner(modules_root: Path) -> None:
    """Territorial lists Cautious; Cautious inactive — no typo warning."""
    result = compose(
        modules_root / "identity" / "guard.md",
        [modules_root / "traits" / "territorial.md"],
        module_root=modules_root,
        library_root=modules_root,
    )
    assert result.manifest.conflict_rules == []
    assert not any("Cautious" in w and "unknown" in w for w in result.manifest.warnings)


def test_relationship_missing_fields(modules_root: Path) -> None:
    with pytest.raises(ValidationError, match="agent|status"):
        parse_module(modules_root / "relationships" / "broken.md")
