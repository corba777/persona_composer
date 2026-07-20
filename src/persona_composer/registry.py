"""Module-type registry (plugin surface)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from persona_composer.errors import ValidationError
from persona_composer.models import Adaptation, Module, ModuleType, Priority, SpeechMode

Frontmatter = dict

Validator = Callable[[Frontmatter, str], list[str]]


@dataclass(frozen=True)
class TypeSpec:
    type: ModuleType
    slot: str
    validate_frontmatter: Validator
    max_count: int | None = None  # None = unbounded; 1 = at most one


def _require_name(fm: Frontmatter) -> list[str]:
    if not fm.get("name"):
        return ["missing required field: name"]
    return []


def _validate_identity(fm: Frontmatter, _body: str) -> list[str]:
    return _require_name(fm)


def _validate_role(fm: Frontmatter, _body: str) -> list[str]:
    errors = _require_name(fm)
    tools = fm.get("tools")
    if tools is not None and not isinstance(tools, list):
        errors.append("role.tools must be a list")
    return errors


def _validate_trait(fm: Frontmatter, _body: str) -> list[str]:
    errors = _require_name(fm)
    priority = fm.get("priority")
    if priority is None:
        errors.append("trait requires priority (high|medium|low)")
    elif priority not in {p.value for p in Priority}:
        errors.append(f"invalid trait.priority: {priority!r}")
    conflicts = fm.get("conflicts", [])
    if conflicts is None:
        conflicts = []
    if not isinstance(conflicts, list):
        errors.append("trait.conflicts must be a list")
    return errors


def _validate_speech(fm: Frontmatter, body: str) -> list[str]:
    errors = _require_name(fm)
    mode = fm.get("mode", SpeechMode.PROMPT.value)
    if mode not in {m.value for m in SpeechMode}:
        errors.append(f"invalid speech.mode: {mode!r}")
    errors.extend(_validate_import_fields(fm, body))
    return errors


def _validate_relationship(fm: Frontmatter, _body: str) -> list[str]:
    errors = _require_name(fm)
    if not fm.get("agent"):
        errors.append("relationship requires agent")
    if not fm.get("status"):
        errors.append("relationship requires status")
    return errors


def _validate_output_rules(fm: Frontmatter, _body: str) -> list[str]:
    return _require_name(fm)


def _validate_import_fields(fm: Frontmatter, body: str) -> list[str]:
    errors: list[str] = []
    source = fm.get("source")
    adaptation = fm.get("adaptation")
    if adaptation is not None and adaptation not in {a.value for a in Adaptation}:
        errors.append(f"invalid adaptation: {adaptation!r}")
    if adaptation == Adaptation.AS_IS.value:
        if not source:
            errors.append("adaptation as-is requires source")
        if body.strip():
            errors.append("adaptation as-is requires an empty overlay body")
    if source and adaptation is None:
        errors.append("source requires adaptation (as-is|extracted)")
    return errors


def _validate_with_import(
    base: Validator,
) -> Validator:
    def _wrapped(fm: Frontmatter, body: str) -> list[str]:
        return base(fm, body) + _validate_import_fields(fm, body)

    return _wrapped


BUILTIN_TYPES: dict[str, TypeSpec] = {
    ModuleType.IDENTITY.value: TypeSpec(
        type=ModuleType.IDENTITY,
        slot="identity",
        validate_frontmatter=_validate_with_import(_validate_identity),
        max_count=1,
    ),
    ModuleType.ROLE.value: TypeSpec(
        type=ModuleType.ROLE,
        slot="role",
        validate_frontmatter=_validate_with_import(_validate_role),
        max_count=1,
    ),
    ModuleType.TRAIT.value: TypeSpec(
        type=ModuleType.TRAIT,
        slot="traits",
        validate_frontmatter=_validate_with_import(_validate_trait),
    ),
    ModuleType.SPEECH.value: TypeSpec(
        type=ModuleType.SPEECH,
        slot="speech",
        validate_frontmatter=_validate_speech,
    ),
    ModuleType.RELATIONSHIP.value: TypeSpec(
        type=ModuleType.RELATIONSHIP,
        slot="relationships",
        validate_frontmatter=_validate_with_import(_validate_relationship),
    ),
    ModuleType.OUTPUT_RULES.value: TypeSpec(
        type=ModuleType.OUTPUT_RULES,
        slot="output_rules",
        validate_frontmatter=_validate_with_import(_validate_output_rules),
        max_count=1,
    ),
}


class TypeRegistry:
    """Open registry of module types."""

    def __init__(self, specs: dict[str, TypeSpec] | None = None) -> None:
        self._specs = dict(specs or BUILTIN_TYPES)

    def register(self, spec: TypeSpec) -> None:
        self._specs[spec.type.value] = spec

    def get(self, type_name: str) -> TypeSpec | None:
        return self._specs.get(type_name)

    def require(self, type_name: str) -> TypeSpec:
        spec = self.get(type_name)
        if spec is None:
            raise ValidationError(f"unknown type: {type_name!r}")
        return spec

    def known_types(self) -> set[str]:
        return set(self._specs)


DEFAULT_REGISTRY = TypeRegistry()


def apply_frontmatter(module: Module, fm: Frontmatter) -> None:
    """Fill type-specific fields on a Module from frontmatter (post-parse)."""
    if module.type == ModuleType.TRAIT:
        module.priority = Priority(fm["priority"])
        conflicts = fm.get("conflicts") or []
        module.conflicts = list(conflicts)
    elif module.type == ModuleType.ROLE:
        module.tools = list(fm.get("tools") or [])
    elif module.type == ModuleType.SPEECH:
        module.mode = SpeechMode(fm.get("mode", SpeechMode.PROMPT.value))
    elif module.type == ModuleType.RELATIONSHIP:
        module.agent = str(fm["agent"])
        module.status = str(fm["status"])

    if fm.get("source"):
        module.source = str(fm["source"])
    if fm.get("adaptation"):
        module.adaptation = Adaptation(fm["adaptation"])
    if fm.get("origin"):
        module.origin = str(fm["origin"])
