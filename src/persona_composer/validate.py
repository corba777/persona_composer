"""Build-time validation."""

from __future__ import annotations

from pathlib import Path

from persona_composer.errors import ValidationError
from persona_composer.models import Module, ModuleType
from persona_composer.registry import DEFAULT_REGISTRY, TypeRegistry


def discover_library_trait_names(module_root: Path | None) -> set[str] | None:
    """Scan module_root for trait names (typo catcher). None if no root given."""
    if module_root is None or not module_root.is_dir():
        return None
    names: set[str] = set()
    for path in module_root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        # Lightweight scan: avoid full parse failures blocking library discovery
        try:
            from persona_composer.parse import split_frontmatter

            fm, _ = split_frontmatter(text)
        except ValidationError:
            continue
        if fm.get("type") == ModuleType.TRAIT.value and fm.get("name"):
            names.add(str(fm["name"]))
    return names


def find_mutual_conflicts(
    traits: list[Module],
) -> list[tuple[Module, Module]]:
    """Return unordered mutual conflict pairs among active traits."""
    by_name = {t.name: t for t in traits}
    pairs: list[tuple[Module, Module]] = []
    seen: set[tuple[str, str]] = set()
    for trait in traits:
        for other_name in trait.conflicts:
            other = by_name.get(other_name)
            if other is None:
                continue
            if trait.name not in other.conflicts:
                continue
            key = tuple(sorted((trait.name, other.name)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((trait, other))
    return pairs


def find_one_sided_conflicts(traits: list[Module]) -> list[str]:
    by_name = {t.name: t for t in traits}
    warnings: list[str] = []
    for trait in traits:
        for other_name in trait.conflicts:
            other = by_name.get(other_name)
            if other is None:
                continue
            if trait.name not in other.conflicts:
                warnings.append(
                    f"incomplete conflict pair: {trait.name} lists {other_name}, "
                    f"but {other_name} does not list {trait.name}"
                )
    return warnings


def validate_modules(
    modules: list[Module],
    *,
    library_trait_names: set[str] | None = None,
    registry: TypeRegistry | None = None,
) -> list[str]:
    """
    Validate active modules. Raises ValidationError on hard failures.
    Returns warning strings.
    """
    registry = registry or DEFAULT_REGISTRY
    errors: list[str] = []
    warnings: list[str] = []

    identities = [m for m in modules if m.type == ModuleType.IDENTITY]
    if not identities:
        errors.append("no identity module (identity is mandatory)")
    elif len(identities) > 1:
        errors.append(
            f"more than one identity module: "
            + ", ".join(repr(m.name) for m in identities)
        )

    # Unknown types already rejected at parse time via registry.require

    # Duplicate names within type
    by_type: dict[ModuleType, list[Module]] = {}
    for m in modules:
        by_type.setdefault(m.type, []).append(m)
    for mtype, group in by_type.items():
        seen: dict[str, Module] = {}
        for m in group:
            if m.name in seen:
                errors.append(
                    f"duplicate name {m.name!r} within type {mtype.value}"
                )
            seen[m.name] = m

    # max_count from registry
    for mtype, group in by_type.items():
        spec = registry.get(mtype.value)
        if spec and spec.max_count is not None and len(group) > spec.max_count:
            errors.append(
                f"at most {spec.max_count} module(s) of type {mtype.value}, "
                f"got {len(group)}"
            )

    traits = by_type.get(ModuleType.TRAIT, [])
    warnings.extend(find_one_sided_conflicts(traits))

    # Typo catcher against library
    if library_trait_names is not None:
        for trait in traits:
            for name in trait.conflicts:
                if name not in library_trait_names:
                    warnings.append(
                        f"conflicts references unknown trait {name!r} "
                        f"(not found in module library)"
                    )

    # Equal-priority mutual conflicts
    for a, b in find_mutual_conflicts(traits):
        assert a.priority is not None and b.priority is not None
        if a.priority == b.priority:
            errors.append(
                f"mutual conflict between {a.name!r} and {b.name!r} "
                f"with equal priority {a.priority.value!r} (каша prevention)"
            )

    if errors:
        raise ValidationError(errors[0], errors=errors)
    return warnings


def resolve_conflicts(traits: list[Module]) -> list:
    """Generate conflict resolutions for mutual pairs (higher priority wins)."""
    from persona_composer.models import ConflictResolution

    resolutions: list[ConflictResolution] = []
    for a, b in find_mutual_conflicts(traits):
        assert a.priority is not None and b.priority is not None
        if a.priority.rank > b.priority.rank:
            winner, loser = a, b
        else:
            winner, loser = b, a
        resolutions.append(
            ConflictResolution(
                winner=winner.name,
                loser=loser.name,
                winner_priority=winner.priority.value,
                loser_priority=loser.priority.value,
            )
        )
    # Stable order by winner then loser
    resolutions.sort(key=lambda r: (r.winner, r.loser))
    return resolutions
