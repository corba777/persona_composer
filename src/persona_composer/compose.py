"""Compose system prompts from modules + emit manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from persona_composer.errors import CompositionError, ValidationError
from persona_composer.hashing import file_hash
from persona_composer.models import (
    Manifest,
    ManifestModule,
    Module,
    ModuleType,
    SkeletonConfig,
    SpeechMode,
)
from persona_composer.parse import parse_module, parse_modules
from persona_composer.registry import DEFAULT_REGISTRY, TypeRegistry
from persona_composer.render import render_prompt
from persona_composer.validate import (
    discover_library_trait_names,
    resolve_conflicts,
    validate_modules,
)


@dataclass
class CompositionResult:
    prompt_xml: str
    manifest: Manifest

    def manifest_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.manifest.to_dict(), indent=indent) + "\n"


def _module_to_manifest_entry(m: Module) -> ManifestModule:
    return ManifestModule(
        path=str(m.path),
        type=m.type.value,
        name=m.name,
        hash=m.hash,
        source=m.source,
        source_hash=m.source_hash,
        origin=m.origin,
        adaptation=m.adaptation.value if m.adaptation else None,
        mode=m.mode.value if m.type == ModuleType.SPEECH else None,
    )


def _build_manifest(
    modules: list[Module],
    resolutions: list,
    warnings: list[str],
    skeleton: SkeletonConfig,
    *,
    timestamp: str | None = None,
) -> Manifest:
    prompt_modules = [
        m
        for m in modules
        if not (m.type == ModuleType.SPEECH and m.mode == SpeechMode.REWRITER)
    ]
    rewriters = [
        m
        for m in modules
        if m.type == ModuleType.SPEECH and m.mode == SpeechMode.REWRITER
    ]
    return Manifest(
        skeleton_version=skeleton.version,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        modules=[_module_to_manifest_entry(m) for m in prompt_modules],
        conflict_rules=[r.to_dict() for r in resolutions],
        rewriter_stack=[_module_to_manifest_entry(m) for m in rewriters],
        warnings=warnings,
    )


def compose(
    identity: Path | Module,
    modules: list[Path | Module] | None = None,
    *,
    skeleton: SkeletonConfig | None = None,
    module_root: Path | None = None,
    library_root: Path | None = None,
    registry: TypeRegistry | None = None,
    timestamp: str | None = None,
) -> CompositionResult:
    """
    Compose a system prompt from an identity module plus optional modules.

    ``module_root`` resolves vendor ``source:`` paths.
    ``library_root`` is scanned for trait-name typo warnings (defaults to module_root).
    """
    skeleton = skeleton or SkeletonConfig()
    registry = registry or DEFAULT_REGISTRY
    modules = list(modules or [])

    parsed: list[Module] = []

    def _ensure(item: Path | Module) -> Module:
        if isinstance(item, Module):
            return item
        return parse_module(item, module_root=module_root, registry=registry)

    identity_mod = _ensure(identity)
    if identity_mod.type != ModuleType.IDENTITY:
        raise ValidationError(
            f"identity argument must be type=identity, got {identity_mod.type.value}"
        )
    parsed.append(identity_mod)
    for item in modules:
        parsed.append(_ensure(item))

    lib_root = library_root if library_root is not None else module_root
    library_names = discover_library_trait_names(lib_root)
    warnings = validate_modules(
        parsed, library_trait_names=library_names, registry=registry
    )
    traits = [m for m in parsed if m.type == ModuleType.TRAIT]
    resolutions = resolve_conflicts(traits)
    prompt_xml = render_prompt(parsed, resolutions, skeleton=skeleton)
    manifest = _build_manifest(
        parsed, resolutions, warnings, skeleton, timestamp=timestamp
    )
    return CompositionResult(prompt_xml=prompt_xml, manifest=manifest)


def compose_from_manifest(
    manifest: Manifest | dict[str, Any] | Path,
    *,
    skeleton: SkeletonConfig | None = None,
    module_root: Path | None = None,
    library_root: Path | None = None,
    registry: TypeRegistry | None = None,
    verify_hashes: bool = True,
    timestamp: str | None = None,
) -> CompositionResult:
    """Recompose from a saved manifest (recipe path)."""
    if isinstance(manifest, Path):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        manifest = Manifest.from_dict(data)
    elif isinstance(manifest, dict):
        manifest = Manifest.from_dict(manifest)

    skeleton = skeleton or SkeletonConfig(version=manifest.skeleton_version)
    if skeleton.version != manifest.skeleton_version:
        # Allow override but default to manifest's version string on the SkeletonConfig
        skeleton = SkeletonConfig(
            version=manifest.skeleton_version,
            output_rules=skeleton.output_rules,
        )

    all_entries = list(manifest.modules) + list(manifest.rewriter_stack)
    if not all_entries:
        raise ValidationError("manifest has no modules")

    paths: list[Path] = []
    for entry in all_entries:
        path = Path(entry.path)
        if not path.is_file():
            # Try relative to module_root
            if module_root is not None:
                alt = module_root / entry.path
                if alt.is_file():
                    path = alt
                else:
                    raise CompositionError(f"manifest module not found: {entry.path}")
            else:
                raise CompositionError(f"manifest module not found: {entry.path}")
        if verify_hashes:
            actual = file_hash(path)
            if actual != entry.hash:
                raise CompositionError(
                    f"hash mismatch for {entry.path}: "
                    f"manifest={entry.hash} actual={actual}"
                )
            if entry.source and entry.source_hash:
                root = module_root or path.parent
                source_path = (root / entry.source).resolve()
                if source_path.is_file():
                    src_hash = file_hash(source_path)
                    if src_hash != entry.source_hash:
                        raise CompositionError(
                            f"source hash mismatch for {entry.source}: "
                            f"manifest={entry.source_hash} actual={src_hash}"
                        )
        paths.append(path)

    # Identify identity among parsed modules
    parsed = parse_modules(paths, module_root=module_root, registry=registry)
    identities = [m for m in parsed if m.type == ModuleType.IDENTITY]
    if not identities:
        raise ValidationError("manifest contains no identity module")
    identity = identities[0]
    others = [m for m in parsed if m is not identity]
    return compose(
        identity,
        others,
        skeleton=skeleton,
        module_root=module_root,
        library_root=library_root,
        registry=registry,
        timestamp=timestamp,
    )
