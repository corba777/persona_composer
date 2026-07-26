"""Back-compat re-exports — prefer ``playground.module_apply``."""

from __future__ import annotations

from playground.module_apply import (  # noqa: F401
    LlmCall,
    compile_persona_modules,
    write_speech_module,
)

# Legacy name used by older app imports
from playground.module_apply import write_speech_module as write_speech_module  # noqa: F401


def compile_speech_variants(*args, **kwargs):  # type: ignore[no-untyped-def]
    raise RuntimeError(
        "compile_speech_variants moved to compile_persona_modules "
        "(playground.module_apply)"
    )
