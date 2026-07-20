"""Persona Composer — modular Markdown → XML system prompt compiler."""

from persona_composer.compose import CompositionResult, compose, compose_from_manifest
from persona_composer.errors import CompositionError, ValidationError

__all__ = [
    "CompositionError",
    "CompositionResult",
    "ValidationError",
    "compose",
    "compose_from_manifest",
]

__version__ = "0.1.0"
