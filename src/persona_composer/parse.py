"""Parse Markdown modules with YAML frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from persona_composer.errors import ValidationError
from persona_composer.hashing import file_hash
from persona_composer.models import Adaptation, Module, ModuleType
from persona_composer.registry import DEFAULT_REGISTRY, TypeRegistry, apply_frontmatter

FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<fm>.*?)\n---\s*\n?(?P<body>.*)\Z",
    re.DOTALL,
)


def split_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValidationError("module must start with YAML frontmatter (--- ... ---)")
    raw = match.group("fm")
    body = match.group("body")
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("frontmatter must be a YAML mapping")
    return data, body


def parse_module(
    path: Path,
    *,
    module_root: Path | None = None,
    registry: TypeRegistry | None = None,
) -> Module:
    """Read and parse a single module file."""
    registry = registry or DEFAULT_REGISTRY
    path = path.resolve()
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)

    type_name = fm.get("type")
    if not type_name:
        raise ValidationError(f"{path}: missing required field: type")
    if not isinstance(type_name, str):
        raise ValidationError(f"{path}: type must be a string")

    try:
        spec = registry.require(type_name)
    except ValidationError as exc:
        raise ValidationError(f"{path}: {exc}") from exc

    errors = spec.validate_frontmatter(fm, body)
    if errors:
        raise ValidationError(f"{path}: " + "; ".join(errors), errors=errors)

    module = Module(
        path=path,
        type=ModuleType(type_name),
        name=str(fm["name"]),
        body=body.strip("\n"),
        hash=file_hash(path),
    )
    apply_frontmatter(module, fm)

    if module.source:
        root = (module_root or path.parent).resolve()
        source_path = (root / module.source).resolve()
        if not source_path.is_file():
            raise ValidationError(
                f"{path}: source not found: {module.source} (resolved {source_path})"
            )
        module.source_path = source_path
        module.source_hash = file_hash(source_path)
        source_text = source_path.read_text(encoding="utf-8")
        # Vendored files may themselves have frontmatter; for as-is we insert the
        # full file text so upstream stays pristine and diffable.
        if module.adaptation == Adaptation.AS_IS:
            module.source_body = source_text.strip("\n")
        else:
            # Provenance only; body comes from overlay.
            module.source_body = None

    return module


def parse_modules(
    paths: list[Path],
    *,
    module_root: Path | None = None,
    registry: TypeRegistry | None = None,
) -> list[Module]:
    return [
        parse_module(p, module_root=module_root, registry=registry) for p in paths
    ]
