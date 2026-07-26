"""Realtime extract/adapt for any persona module + speech rewriter compile."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from persona_composer.parse import parse_module, split_frontmatter

SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")

ModuleKind = Literal["identity", "role", "trait", "speech", "output_rules", "relationship"]
LlmCall = Callable[[str, str], str]

EXTRACT_SYSTEM = (
    "You distill agent persona modules into clean overlays for persona_composer. "
    "Return ONLY a JSON object. No markdown fences, no commentary."
)


def _safe(name: str) -> str:
    cleaned = SAFE_NAME.sub("_", name.strip()) or "Module"
    return cleaned[:64]


def _strip_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text)
    if fence:
        return fence.group(1).strip()
    return text


def load_module_meta(path: Path, module_root: Path | None) -> tuple[str, dict[str, Any]]:
    mod = parse_module(path, module_root=module_root)
    meta: dict[str, Any] = {
        "name": mod.name,
        "type": mod.type.value,
        "source": mod.source,
        "adaptation": mod.adaptation.value if mod.adaptation else None,
        "origin": mod.origin,
        "mode": mod.mode.value if hasattr(mod, "mode") and mod.mode else "prompt",
        "hash": mod.hash,
        "priority": mod.priority.value if mod.priority else None,
        "conflicts": list(mod.conflicts or []),
        "tools": list(mod.tools or []),
        "agent": mod.agent,
        "status": mod.status,
    }
    return mod.render_body, meta


def fingerprint_module(path: Path, module_root: Path | None) -> str:
    body, meta = load_module_meta(path, module_root)
    return f"{path.resolve()}|{meta.get('type')}|{meta.get('hash')}|{len(body)}"


def write_module_file(
    work_dir: Path,
    *,
    module_type: str,
    name: str,
    body: str,
    extra_frontmatter: dict[str, Any] | None = None,
    source: str | None = None,
    adaptation: str | None = None,
    origin: str | None = None,
    filename_suffix: str = "",
) -> Path:
    stem = f"{module_type}_{_safe(name)}{filename_suffix}"
    path = work_dir / f"{stem}.md"
    lines = ["---", f"type: {module_type}", f"name: {_safe(name)}"]
    for key, value in (extra_frontmatter or {}).items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, list):
            inner = ", ".join(str(v) for v in value)
            lines.append(f"{key}: [{inner}]")
        else:
            lines.append(f"{key}: {value}")
    if source:
        lines.append(f"source: {source}")
    if adaptation:
        lines.append(f"adaptation: {adaptation}")
    if origin:
        lines.append(f"origin: {origin}")
    lines.append("---")
    lines.append((body or "").strip())
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _extract_user_prompt(module_type: str, source_text: str, meta: dict[str, Any]) -> str:
    type_rules = {
        "identity": (
            "Distill a standalone identity body: who the agent is and what it does. "
            "Strip MCP/tool wiring, host config paths, and IDE-only machinery; keep workflow "
            "substance that still makes sense as system-prompt identity."
        ),
        "speech": (
            "Distill speech/style only. Preserve language and register. "
            "Strip slash-commands, 'read references', statusline, host activation. "
            "Body must apply to every user-facing reply, including formal reports."
        ),
        "trait": (
            "Distill a single behavioral trait as short imperatives. "
            "Keep conflict semantics in mind; you may return priority/conflicts."
        ),
        "role": (
            "Distill role directives (duties/authority). Strip tooling lists that are host-only "
            "unless essential to the role description."
        ),
        "output_rules": (
            "Distill output/format rules only (length, structure, metadata). No character speech."
        ),
        "relationship": (
            "Distill relationship stance toward the target agent as short imperatives."
        ),
    }.get(module_type, "Distill short imperative module body; strip host tooling.")

    schema = {
        "name": "PascalCaseName",
        "body": "short imperative directives",
        "rationale": "one sentence",
    }
    if module_type == "trait":
        schema["priority"] = meta.get("priority") or "medium"
        schema["conflicts"] = meta.get("conflicts") or []
    if module_type == "speech":
        schema["mode"] = "prompt"
    if module_type == "role" and meta.get("tools"):
        schema["tools"] = meta.get("tools")
    if module_type == "relationship":
        schema["agent"] = meta.get("agent") or "target"
        schema["status"] = meta.get("status") or "neutral"

    return (
        f"Module type to produce: {module_type}\n"
        f"{type_rules}\n\n"
        f"Return ONLY JSON with this shape:\n{json.dumps(schema, indent=2)}\n\n"
        "Rules:\n"
        "- Prefer short imperative bodies (no essays).\n"
        "- Preserve source language when it defines register (e.g. Russian informal speech).\n"
        "- Do not change the module type.\n\n"
        f"--- SOURCE START ---\n{source_text.strip()}\n--- SOURCE END ---\n"
    )


def distill_module(
    *,
    module_type: str,
    source_text: str,
    meta: dict[str, Any],
    llm_call: LlmCall,
    fallback_name: str,
) -> dict[str, Any]:
    raw = llm_call(EXTRACT_SYSTEM, _extract_user_prompt(module_type, source_text, meta))
    data = json.loads(_strip_fences(raw))
    if not isinstance(data, dict):
        raise ValueError(f"extract {module_type}: LLM JSON must be an object")
    name = str(data.get("name") or fallback_name).strip() or fallback_name
    body = str(data.get("body") or "").strip()
    if not body:
        raise ValueError(f"extract {module_type}: empty body from LLM")
    out: dict[str, Any] = {"name": name, "body": body}
    if module_type == "trait":
        pr = data.get("priority") or meta.get("priority") or "medium"
        if pr not in ("high", "medium", "low"):
            pr = "medium"
        out["priority"] = pr
        conflicts = data.get("conflicts")
        if not isinstance(conflicts, list):
            conflicts = meta.get("conflicts") or []
        out["conflicts"] = [str(c) for c in conflicts]
    if module_type == "speech":
        mode = data.get("mode") or "prompt"
        out["mode"] = mode if mode in ("prompt", "rewriter") else "prompt"
    if module_type == "role":
        tools = data.get("tools")
        if isinstance(tools, list):
            out["tools"] = [str(t) for t in tools]
        elif meta.get("tools"):
            out["tools"] = list(meta["tools"])
    if module_type == "relationship":
        out["agent"] = str(data.get("agent") or meta.get("agent") or "target")
        out["status"] = str(data.get("status") or meta.get("status") or "neutral")
    return out


@dataclass
class CompiledModule:
    source_path: Path
    module_type: str
    prompt_path: Path  # path to use in compose (extracted or original)
    extracted_path: Path | None = None
    rewriter_path: Path | None = None  # speech only
    notes: list[str] = field(default_factory=list)


@dataclass
class PersonaCompileResult:
    identity_path: Path
    module_paths: list[Path]  # non-identity modules for compose (prompt + rewriter speech)
    rewriter_paths: list[Path]
    notes: list[str] = field(default_factory=list)
    by_source: dict[str, CompiledModule] = field(default_factory=dict)


def _extra_fm_from_distill(module_type: str, distilled: dict[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if module_type == "trait":
        extra["priority"] = distilled.get("priority") or "medium"
        if distilled.get("conflicts"):
            extra["conflicts"] = distilled["conflicts"]
    if module_type == "speech":
        mode = distilled.get("mode") or "prompt"
        if mode != "prompt":
            extra["mode"] = mode
    if module_type == "role" and distilled.get("tools"):
        extra["tools"] = distilled["tools"]
    if module_type == "relationship":
        extra["agent"] = distilled.get("agent")
        extra["status"] = distilled.get("status")
    return extra


def _extra_fm_from_meta(module_type: str, meta: dict[str, Any]) -> dict[str, Any]:
    return _extra_fm_from_distill(
        module_type,
        {
            "priority": meta.get("priority"),
            "conflicts": meta.get("conflicts"),
            "mode": meta.get("mode"),
            "tools": meta.get("tools"),
            "agent": meta.get("agent"),
            "status": meta.get("status"),
        },
    )


def _provenance_for_overlay(
    source_path: Path,
    meta: dict[str, Any],
    module_root: Path | None,
) -> tuple[str | None, str | None, str | None]:
    """
    Return (source, adaptation, origin) for a compiled extracted overlay.

    ``parse_module`` always resolves ``source:`` under ``module_root`` (or the
    overlay's parent). Basename-only paths from temp uploads 404 — prefer a path
    that exists: library-relative, else absolute. If nothing resolves, omit
    provenance (body-only module).
    """
    origin = str(meta["origin"]) if meta.get("origin") else None
    existing = meta.get("source")
    if existing and module_root is not None:
        cand = (module_root / str(existing)).resolve()
        if cand.is_file():
            return str(existing), "extracted", origin

    resolved = source_path.resolve()
    if resolved.is_file():
        if module_root is not None:
            try:
                rel = resolved.relative_to(module_root.resolve())
                return str(rel), "extracted", origin
            except ValueError:
                pass
        # Absolute path: Path(module_root) / abs stays abs on POSIX.
        return str(resolved), "extracted", origin

    return None, None, origin


def compile_one_module(
    source_path: Path,
    *,
    work_dir: Path,
    module_root: Path | None,
    extract: bool,
    make_speech_rewriter: bool,
    include_speech_in_prompt: bool,
    llm_call: LlmCall | None,
    cache_bucket: dict[str, Any],
) -> CompiledModule:
    body, meta = load_module_meta(source_path, module_root)
    module_type = str(meta["type"])
    fp = fingerprint_module(source_path, module_root)
    base_name = str(meta.get("name") or source_path.stem)
    src_for_fm, adaptation, origin = _provenance_for_overlay(
        source_path, meta, module_root
    )
    notes: list[str] = []

    extracted_path: Path | None = None
    prompt_path = source_path
    distilled_body = body
    distilled_name = base_name
    distilled_extra = _extra_fm_from_meta(module_type, meta)

    if extract:
        cached = cache_bucket.get(fp) or {}
        cached_path = cached.get("extracted_path")
        if cached_path and Path(cached_path).is_file():
            extracted_path = Path(cached_path)
            # Drop stale overlays whose source: no longer resolves under module_root.
            try:
                parse_module(extracted_path, module_root=module_root)
                text = extracted_path.read_text(encoding="utf-8")
                fm, b = split_frontmatter(text)
                distilled_body = b
                distilled_name = str(fm.get("name") or base_name)
                distilled_extra = _extra_fm_from_meta(module_type, {**meta, **fm})
                notes.append(f"Reused extracted {module_type}: {extracted_path.name}")
            except Exception:
                extracted_path = None
                cache_bucket.pop(fp, None)
        if extracted_path is None:
            if llm_call is None:
                raise ValueError("Extract / adapt needs an LLM call")
            distilled = distill_module(
                module_type=module_type,
                source_text=body,
                meta=meta,
                llm_call=llm_call,
                fallback_name=f"{base_name}Extracted",
            )
            distilled_name = distilled["name"]
            distilled_body = distilled["body"]
            distilled_extra = _extra_fm_from_distill(module_type, distilled)
            extracted_path = write_module_file(
                work_dir,
                module_type=module_type,
                name=distilled_name,
                body=distilled_body,
                extra_frontmatter=distilled_extra,
                source=src_for_fm,
                adaptation=adaptation,
                origin=origin,
                filename_suffix=f"_extracted_{meta.get('hash') or 'x'}",
            )
            notes.append(f"Compiled extracted {module_type}: {extracted_path.name}")
            cache_bucket[fp] = {
                "extracted_path": str(extracted_path),
                "name": distilled_name,
            }
        prompt_path = extracted_path

    rewriter_path: Path | None = None
    if module_type == "speech" and make_speech_rewriter:
        rw_key = f"{fp}|rewriter|{extract}"
        cached_rw = (cache_bucket.get(rw_key) or {}).get("rewriter_path")
        if cached_rw and Path(cached_rw).is_file():
            rewriter_path = Path(cached_rw)
            notes.append(f"Reused rewriter speech: {rewriter_path.name}")
        else:
            rw_name = f"{distilled_name}Rewriter"
            rewriter_path = write_module_file(
                work_dir,
                module_type="speech",
                name=rw_name,
                body=distilled_body,
                extra_frontmatter={"mode": "rewriter"},
                source=src_for_fm,
                adaptation=adaptation if src_for_fm else None,
                origin=origin,
                filename_suffix=f"_rewriter_{meta.get('hash') or 'x'}",
            )
            notes.append(f"Compiled rewriter speech: {rewriter_path.name}")
            cache_bucket[rw_key] = {"rewriter_path": str(rewriter_path)}

    return CompiledModule(
        source_path=source_path,
        module_type=module_type,
        prompt_path=prompt_path,
        extracted_path=extracted_path,
        rewriter_path=rewriter_path,
        notes=notes,
    )


def compile_persona_modules(
    *,
    identity_path: Path,
    extra_paths: list[Path],
    work_dir: Path,
    module_root: Path | None,
    extract: bool,
    post_rewrite: bool,
    speech_in_prompt: bool,
    llm_call: LlmCall | None,
    cache: dict[str, Any] | None = None,
) -> tuple[PersonaCompileResult, dict[str, Any]]:
    """
    Optionally extract/adapt every attached module; optionally compile speech rewriter.

    Returns compose-ready identity + module paths (rewriter speech included for manifest stack).
    """
    cache = dict(cache or {})
    buckets: dict[str, Any] = cache.setdefault("modules", {})
    notes: list[str] = []
    by_source: dict[str, CompiledModule] = {}

    id_compiled = compile_one_module(
        identity_path,
        work_dir=work_dir,
        module_root=module_root,
        extract=extract,
        make_speech_rewriter=False,
        include_speech_in_prompt=True,
        llm_call=llm_call,
        cache_bucket=buckets,
    )
    notes.extend(id_compiled.notes)
    by_source[str(identity_path)] = id_compiled

    compose_modules: list[Path] = []
    rewriter_paths: list[Path] = []

    for path in extra_paths:
        body, meta = load_module_meta(path, module_root)
        _ = body
        is_speech = meta["type"] == "speech"
        compiled = compile_one_module(
            path,
            work_dir=work_dir,
            module_root=module_root,
            extract=extract,
            make_speech_rewriter=post_rewrite and is_speech,
            include_speech_in_prompt=speech_in_prompt if is_speech else True,
            llm_call=llm_call,
            cache_bucket=buckets,
        )
        notes.extend(compiled.notes)
        by_source[str(path)] = compiled
        if is_speech:
            if speech_in_prompt:
                compose_modules.append(compiled.prompt_path)
            if compiled.rewriter_path is not None:
                compose_modules.append(compiled.rewriter_path)
                rewriter_paths.append(compiled.rewriter_path)
        else:
            compose_modules.append(compiled.prompt_path)

    result = PersonaCompileResult(
        identity_path=id_compiled.prompt_path,
        module_paths=compose_modules,
        rewriter_paths=rewriter_paths,
        notes=notes,
        by_source=by_source,
    )
    cache["last_notes"] = notes
    cache["last_identity"] = str(result.identity_path)
    cache["last_modules"] = [str(p) for p in result.module_paths]
    cache["last_rewriters"] = [str(p) for p in result.rewriter_paths]
    return result, cache


# Back-compat aliases used by older imports
def write_speech_module(
    work_dir: Path,
    *,
    name: str,
    body: str,
    mode: str = "prompt",
    source: str | None = None,
    adaptation: str | None = None,
    origin: str | None = None,
    filename_suffix: str = "",
) -> Path:
    extra = {"mode": mode} if mode and mode != "prompt" else {}
    return write_module_file(
        work_dir,
        module_type="speech",
        name=name,
        body=body,
        extra_frontmatter=extra,
        source=source,
        adaptation=adaptation,
        origin=origin,
        filename_suffix=filename_suffix,
    )
