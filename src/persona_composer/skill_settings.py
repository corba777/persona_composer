"""Settings for compiling Agent Skills / host instruction files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from persona_composer.errors import ValidationError

TargetKind = Literal["skill_md", "agents_md", "copilot_instructions"]


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str


@dataclass(frozen=True)
class SkillTarget:
    kind: TargetKind
    path: Path


@dataclass
class SkillSettings:
    """Consumer-owned recipe for skill export."""

    identity: Path
    modules: list[Path] = field(default_factory=list)
    module_root: Path | None = None
    skill: SkillMeta = field(
        default_factory=lambda: SkillMeta(
            name="persona",
            description="Composed coding persona.",
        )
    )
    targets: list[SkillTarget] = field(default_factory=list)
    # Directory used to resolve relative paths (settings file parent or CWD).
    base_dir: Path = field(default_factory=Path.cwd)


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def load_skill_settings(path: Path | str) -> SkillSettings:
    """Load ``persona.settings.json`` (or any JSON with the skill schema)."""
    settings_path = Path(path).resolve()
    if not settings_path.is_file():
        raise ValidationError(f"settings file not found: {settings_path}")
    base = settings_path.parent
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid settings JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("settings root must be a JSON object")
    return skill_settings_from_dict(data, base_dir=base)


def skill_settings_from_dict(
    data: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> SkillSettings:
    base = (base_dir or Path.cwd()).resolve()
    identity_raw = data.get("identity")
    if not identity_raw:
        raise ValidationError("settings require 'identity'")

    module_root_raw = data.get("module_root")
    module_root = (
        _resolve(base, module_root_raw) if module_root_raw else None
    )

    identity = _resolve(module_root or base, str(identity_raw))
    modules_raw = data.get("modules") or []
    if not isinstance(modules_raw, list):
        raise ValidationError("'modules' must be a list of paths")
    modules = [_resolve(module_root or base, str(p)) for p in modules_raw]

    skill_raw = data.get("skill") or {}
    if not isinstance(skill_raw, dict):
        raise ValidationError("'skill' must be an object")
    name = str(skill_raw.get("name") or "persona")
    description = str(
        skill_raw.get("description") or "Composed coding persona."
    )

    targets: list[SkillTarget] = []
    targets_raw = data.get("targets") or []
    if not isinstance(targets_raw, list):
        raise ValidationError("'targets' must be a list")
    for i, item in enumerate(targets_raw):
        if not isinstance(item, dict):
            raise ValidationError(f"targets[{i}] must be an object")
        kind = item.get("kind")
        tpath = item.get("path")
        if kind not in ("skill_md", "agents_md", "copilot_instructions"):
            raise ValidationError(
                f"targets[{i}].kind must be skill_md, agents_md, or "
                f"copilot_instructions, got {kind!r}"
            )
        if not tpath:
            raise ValidationError(f"targets[{i}] requires 'path'")
        targets.append(
            SkillTarget(kind=kind, path=_resolve(base, str(tpath)))
        )

    return SkillSettings(
        identity=identity,
        modules=modules,
        module_root=module_root,
        skill=SkillMeta(name=name, description=description),
        targets=targets,
        base_dir=base,
    )


def skill_settings_adhoc(
    *,
    identity: Path,
    modules: list[Path] | None = None,
    module_root: Path | None = None,
    name: str = "persona",
    description: str = "Composed coding persona.",
    out: Path | None = None,
    base_dir: Path | None = None,
) -> SkillSettings:
    """Build settings from CLI flags (no settings file)."""
    base = (base_dir or Path.cwd()).resolve()
    targets: list[SkillTarget] = []
    if out is not None:
        targets.append(SkillTarget(kind="skill_md", path=Path(out).resolve()))
    return SkillSettings(
        identity=Path(identity).resolve(),
        modules=[Path(m).resolve() for m in (modules or [])],
        module_root=Path(module_root).resolve() if module_root else None,
        skill=SkillMeta(name=name, description=description),
        targets=targets,
        base_dir=base,
    )
