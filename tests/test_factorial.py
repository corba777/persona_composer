"""Factorial ablation helper tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from persona_composer.errors import ValidationError
from persona_composer.factorial import (
    factorial_compose,
    sanitize_label,
    write_factorial,
)

FIXED_TS = "2026-07-20T15:00:00+00:00"
MODULES = Path(__file__).parent / "fixtures" / "modules"


def test_factorial_two_traits_four_cells() -> None:
    result = factorial_compose(
        MODULES / "identity" / "guard.md",
        [
            MODULES / "traits" / "territorial.md",
            MODULES / "traits" / "cautious.md",
        ],
        baseline=[MODULES / "speech" / "curt.md"],
        module_root=MODULES,
        library_root=MODULES,
        timestamp=FIXED_TS,
    )
    assert len(result.cells) == 4
    assert result.trait_names == ["Cautious", "Territorial"]
    labels = [c.label for c in result.cells]
    assert labels == [
        "none",
        "Cautious",
        "Territorial",
        "Cautious+Territorial",
    ]
    assert all(c.error is None for c in result.cells)
    assert all(c.result is not None for c in result.cells)
    # Shared timestamp
    assert all(c.result.manifest.timestamp == FIXED_TS for c in result.cells)  # type: ignore[union-attr]
    # Baseline speech in every successful manifest
    for cell in result.cells:
        assert cell.result is not None
        names = {m.name for m in cell.result.manifest.modules}
        assert "Curt" in names
        assert "Guard" in names
        for t in cell.traits_on:
            assert t in names


def test_factorial_equal_priority_conflict_cell_errors(tmp_path: Path) -> None:
    result = factorial_compose(
        MODULES / "identity" / "guard.md",
        [
            MODULES / "traits" / "stubborn.md",
            MODULES / "traits" / "flexible.md",
        ],
        module_root=MODULES,
        library_root=MODULES,
        timestamp=FIXED_TS,
    )
    assert len(result.cells) == 4
    by_label = {c.label: c for c in result.cells}
    assert by_label["none"].error is None
    assert by_label["Stubborn"].error is None
    assert by_label["Flexible"].error is None
    bad = by_label["Flexible+Stubborn"]
    assert bad.error is not None
    assert bad.result is None

    index = write_factorial(result, tmp_path, write_prompts=True)
    data = json.loads(index.read_text(encoding="utf-8"))
    assert data["trait_names"] == ["Flexible", "Stubborn"]
    assert len(data["cells"]) == 4
    failed = next(c for c in data["cells"] if c["label"] == "Flexible+Stubborn")
    assert failed["error"]
    assert failed["manifest"] is None
    ok = next(c for c in data["cells"] if c["label"] == "none")
    assert ok["manifest"] == "manifests/none.json"
    assert ok["prompt"] == "prompts/none.xml"
    assert (tmp_path / "manifests" / "none.json").is_file()
    assert (tmp_path / "prompts" / "none.xml").is_file()


def test_factorial_cap() -> None:
    traits = [MODULES / "traits" / "cautious.md"] * 13
    # duplicate names fail first — use max_traits with unique would need 13 files
    with pytest.raises(ValidationError, match="duplicate trait name"):
        factorial_compose(
            MODULES / "identity" / "guard.md",
            traits,
            module_root=MODULES,
            max_traits=20,
        )


def test_factorial_max_traits_limit(tmp_path: Path) -> None:
    # Create tiny unique traits
    paths = []
    for i in range(3):
        p = tmp_path / f"t{i}.md"
        p.write_text(
            f"---\ntype: trait\nname: T{i}\npriority: low\n---\nBody {i}.\n",
            encoding="utf-8",
        )
        paths.append(p)
    with pytest.raises(ValidationError, match="too many traits"):
        factorial_compose(
            MODULES / "identity" / "guard.md",
            paths,
            module_root=MODULES,
            max_traits=2,
        )


def test_sanitize_label() -> None:
    assert sanitize_label("none") == "none"
    assert sanitize_label("Cautious+Territorial") == "Cautious+Territorial"
