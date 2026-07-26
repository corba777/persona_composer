"""Factorial (2^k) trait ablation helper."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from persona_composer.compose import CompositionResult, compose
from persona_composer.errors import CompositionError, ValidationError
from persona_composer.models import Module, ModuleType, SkeletonConfig
from persona_composer.parse import parse_module

DEFAULT_MAX_TRAITS = 12
_SAFE = re.compile(r"[^A-Za-z0-9._+-]+")


@dataclass
class FactorialCell:
    traits_on: list[str]
    trait_paths: list[Path]
    label: str
    result: CompositionResult | None
    error: str | None


@dataclass
class FactorialResult:
    cells: list[FactorialCell]
    timestamp: str
    trait_names: list[str]


def _as_module(
    item: Path | Module,
    *,
    module_root: Path | None,
) -> Module:
    if isinstance(item, Module):
        return item
    return parse_module(item, module_root=module_root)


def cell_label(trait_names: list[str]) -> str:
    if not trait_names:
        return "none"
    return "+".join(trait_names)


def sanitize_label(label: str) -> str:
    cleaned = _SAFE.sub("_", label).strip("._")
    return cleaned or "cell"


def _subsets_by_popcount(
    named: list[tuple[str, Path | Module]],
) -> list[list[tuple[str, Path | Module]]]:
    """Order: popcount ascending, then lex by sorted names within size."""
    ordered: list[list[tuple[str, Path | Module]]] = []
    n = len(named)
    for r in range(n + 1):
        combos = list(combinations(named, r))
        combos.sort(key=lambda c: tuple(name for name, _ in c))
        for combo in combos:
            ordered.append(list(combo))
    return ordered


def factorial_compose(
    identity: Path | Module,
    traits: list[Path | Module],
    *,
    baseline: list[Path | Module] | None = None,
    module_root: Path | None = None,
    library_root: Path | None = None,
    skeleton: SkeletonConfig | None = None,
    timestamp: str | None = None,
    max_traits: int = DEFAULT_MAX_TRAITS,
) -> FactorialResult:
    """Compose every subset of ``traits`` (2^k), with ``baseline`` always on."""
    if not traits:
        raise ValidationError("factorial requires at least one trait module")
    if len(traits) > max_traits:
        raise ValidationError(
            f"too many traits for factorial: {len(traits)} > max_traits={max_traits}"
        )

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    identity_mod = _as_module(identity, module_root=module_root)
    if identity_mod.type != ModuleType.IDENTITY:
        raise ValidationError(
            f"identity must be type=identity, got {identity_mod.type.value}"
        )

    named: list[tuple[str, Path | Module]] = []
    seen_names: set[str] = set()
    for item in traits:
        mod = _as_module(item, module_root=module_root)
        if mod.type != ModuleType.TRAIT:
            raise ValidationError(
                f"factorial traits must be type=trait, got {mod.type.value} ({mod.name})"
            )
        if mod.name in seen_names:
            raise ValidationError(f"duplicate trait name in factorial list: {mod.name}")
        seen_names.add(mod.name)
        # Keep Path for trait_paths when possible
        path_or_mod: Path | Module = item if isinstance(item, Path) else mod
        named.append((mod.name, path_or_mod))

    named.sort(key=lambda t: t[0])
    trait_names = [n for n, _ in named]
    baseline_list = list(baseline or [])

    cells: list[FactorialCell] = []
    for subset in _subsets_by_popcount(named):
        names = [n for n, _ in subset]
        paths = [
            (p if isinstance(p, Path) else Path(p.path)) for _, p in subset
        ]
        label = cell_label(names)
        extras = list(baseline_list) + [item for _, item in subset]
        try:
            result = compose(
                identity_mod if isinstance(identity, Module) else identity,
                extras,
                skeleton=skeleton,
                module_root=module_root,
                library_root=library_root if library_root is not None else module_root,
                timestamp=ts,
            )
            cells.append(
                FactorialCell(
                    traits_on=names,
                    trait_paths=paths,
                    label=label,
                    result=result,
                    error=None,
                )
            )
        except CompositionError as exc:
            cells.append(
                FactorialCell(
                    traits_on=names,
                    trait_paths=paths,
                    label=label,
                    result=None,
                    error=str(exc),
                )
            )

    return FactorialResult(cells=cells, timestamp=ts, trait_names=trait_names)


def write_factorial(
    result: FactorialResult,
    out_dir: Path,
    *,
    write_prompts: bool = True,
) -> Path:
    """Write manifests/, prompts/, and index.json under ``out_dir``."""
    out_dir = Path(out_dir)
    manifests_dir = out_dir / "manifests"
    prompts_dir = out_dir / "prompts"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    if write_prompts:
        prompts_dir.mkdir(parents=True, exist_ok=True)

    index_cells: list[dict] = []
    used_files: set[str] = set()

    for cell in result.cells:
        base = sanitize_label(cell.label)
        file_stem = base
        n = 2
        while file_stem in used_files:
            file_stem = f"{base}_{n}"
            n += 1
        used_files.add(file_stem)

        manifest_rel: str | None = None
        prompt_rel: str | None = None

        if cell.result is not None:
            manifest_path = manifests_dir / f"{file_stem}.json"
            manifest_path.write_text(cell.result.manifest_json(), encoding="utf-8")
            manifest_rel = f"manifests/{file_stem}.json"
            if write_prompts:
                prompt_path = prompts_dir / f"{file_stem}.xml"
                prompt_path.write_text(cell.result.prompt_xml, encoding="utf-8")
                prompt_rel = f"prompts/{file_stem}.xml"

        index_cells.append(
            {
                "label": cell.label,
                "traits_on": list(cell.traits_on),
                "manifest": manifest_rel,
                "prompt": prompt_rel,
                "error": cell.error,
            }
        )

    index = {
        "timestamp": result.timestamp,
        "trait_names": list(result.trait_names),
        "cells": index_cells,
    }
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index_path
