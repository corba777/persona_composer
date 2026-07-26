"""Persona Composer — modular Markdown → XML system prompt compiler."""

from persona_composer.compose import CompositionResult, compose, compose_from_manifest
from persona_composer.decompose import DecompositionResult, decompose
from persona_composer.errors import CompositionError, ValidationError
from persona_composer.factorial import (
    FactorialCell,
    FactorialResult,
    factorial_compose,
    write_factorial,
)
from persona_composer.rewriter import (
    RewriteResult,
    apply_rewriters,
    apply_rewriters_from_manifest,
    apply_rewriters_from_paths,
)
from persona_composer.skill_export import (
    SkillExportResult,
    compose_skill,
    write_skill_targets,
)
from persona_composer.skill_settings import (
    SkillMeta,
    SkillSettings,
    SkillTarget,
    load_skill_settings,
    skill_settings_adhoc,
)

__all__ = [
    "CompositionError",
    "CompositionResult",
    "DecompositionResult",
    "FactorialCell",
    "FactorialResult",
    "RewriteResult",
    "SkillExportResult",
    "SkillMeta",
    "SkillSettings",
    "SkillTarget",
    "ValidationError",
    "apply_rewriters",
    "apply_rewriters_from_manifest",
    "apply_rewriters_from_paths",
    "compose",
    "compose_from_manifest",
    "compose_skill",
    "decompose",
    "factorial_compose",
    "load_skill_settings",
    "skill_settings_adhoc",
    "write_factorial",
    "write_skill_targets",
]

__version__ = "0.1.0"
