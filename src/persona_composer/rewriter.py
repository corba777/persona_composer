"""Rewriter pipeline — apply speech.mode=rewriter modules to model output.

Additive to compose(): rewriter modules stay excluded from the system prompt
and listed on the manifest ``rewriter_stack``. This runner applies them
post-generation. The composer core never calls an LLM — inject ``llm_call``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from persona_composer.errors import CompositionError, ValidationError
from persona_composer.models import Manifest, Module, ModuleType, SpeechMode
from persona_composer.parse import parse_module

# (system_instruction, user_content) -> rewritten text
RewriteLlmCall = Callable[[str, str], str]

DEFAULT_REWRITE_USER_TEMPLATE = (
    "Rewrite the following text according to the style instructions. "
    "Preserve meaning and factual content. Output only the rewritten text.\n\n"
    "---\n{text}\n---"
)


@dataclass
class RewriteStep:
    module_name: str
    module_path: str
    output: str


@dataclass
class RewriteResult:
    text: str
    steps: list[RewriteStep] = field(default_factory=list)


def _module_style_body(module: Module) -> str:
    body = module.render_body.strip()
    if not body:
        raise ValidationError(
            f"rewriter module {module.name!r} has an empty body"
        )
    return body


def apply_rewriters(
    text: str,
    modules: Sequence[Module],
    *,
    llm_call: RewriteLlmCall,
    user_template: str = DEFAULT_REWRITE_USER_TEMPLATE,
) -> RewriteResult:
    """
    Apply rewriter modules in order (stable by name).

    Only ``type=speech`` with ``mode=rewriter`` are applied; others are skipped
    with no error (backward compatible if a mixed list is passed).
    """
    if not text.strip():
        raise ValidationError("rewrite: input text is empty")

    rewriters = [
        m
        for m in modules
        if m.type == ModuleType.SPEECH and m.mode == SpeechMode.REWRITER
    ]
    rewriters = sorted(rewriters, key=lambda m: m.name)

    current = text
    steps: list[RewriteStep] = []
    for mod in rewriters:
        system = _module_style_body(mod)
        user = user_template.format(text=current)
        current = llm_call(system, user)
        if not isinstance(current, str) or not current.strip():
            raise CompositionError(
                f"rewriter {mod.name!r} returned an empty response"
            )
        steps.append(
            RewriteStep(
                module_name=mod.name,
                module_path=str(mod.path),
                output=current,
            )
        )
    return RewriteResult(text=current, steps=steps)


def apply_rewriters_from_paths(
    text: str,
    paths: Sequence[Path],
    *,
    llm_call: RewriteLlmCall,
    module_root: Path | None = None,
    user_template: str = DEFAULT_REWRITE_USER_TEMPLATE,
) -> RewriteResult:
    modules = [parse_module(p, module_root=module_root) for p in paths]
    if not any(
        m.type == ModuleType.SPEECH and m.mode == SpeechMode.REWRITER
        for m in modules
    ):
        raise ValidationError(
            "rewrite: no speech modules with mode=rewriter in the given paths"
        )
    return apply_rewriters(
        text, modules, llm_call=llm_call, user_template=user_template
    )


def _load_manifest(manifest: Manifest | dict[str, Any] | Path) -> Manifest:
    if isinstance(manifest, Manifest):
        return manifest
    if isinstance(manifest, Path):
        return Manifest.from_dict(
            json.loads(manifest.read_text(encoding="utf-8"))
        )
    return Manifest.from_dict(manifest)


def apply_rewriters_from_manifest(
    text: str,
    manifest: Manifest | dict[str, Any] | Path,
    *,
    llm_call: RewriteLlmCall,
    module_root: Path | None = None,
    user_template: str = DEFAULT_REWRITE_USER_TEMPLATE,
) -> RewriteResult:
    """Load ``rewriter_stack`` from a compose manifest and apply them.

    Empty ``rewriter_stack`` → no-op (returns input text). Backward compatible.
    """
    manifest = _load_manifest(manifest)
    stack = list(manifest.rewriter_stack)
    if not stack:
        return RewriteResult(text=text, steps=[])

    paths: list[Path] = []
    for entry in stack:
        path = Path(entry.path)
        if not path.is_file() and module_root is not None:
            alt = module_root / entry.path
            if alt.is_file():
                path = alt
        if not path.is_file():
            raise CompositionError(
                f"rewrite: rewriter module not found: {entry.path}"
            )
        paths.append(path)

    return apply_rewriters_from_paths(
        text,
        paths,
        llm_call=llm_call,
        module_root=module_root,
        user_template=user_template,
    )
