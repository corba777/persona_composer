"""Persona Composer — modular Markdown → XML system prompt compiler."""

from persona_composer.compose import CompositionResult, compose, compose_from_manifest
from persona_composer.decompose import DecompositionResult, decompose
from persona_composer.errors import CompositionError, ValidationError
from persona_composer.rewriter import (
    RewriteResult,
    apply_rewriters,
    apply_rewriters_from_manifest,
    apply_rewriters_from_paths,
)

__all__ = [
    "CompositionError",
    "CompositionResult",
    "DecompositionResult",
    "RewriteResult",
    "ValidationError",
    "apply_rewriters",
    "apply_rewriters_from_manifest",
    "apply_rewriters_from_paths",
    "compose",
    "compose_from_manifest",
    "decompose",
]

__version__ = "0.1.0"
