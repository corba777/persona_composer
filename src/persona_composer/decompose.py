"""Decomposition workflow — suggest trait/speech extractions (LLM-assisted, offline).

The composer core never calls an LLM. Pass ``llm_call`` (or use
``decompose_from_suggestions`` with precomputed JSON) to drive suggestions.
Writes *draft* modules for human review — does not mutate the source file.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from persona_composer.errors import CompositionError, ValidationError
from persona_composer.parse import split_frontmatter

SuggestionType = Literal["trait", "speech", "role", "output_rules"]

# Injected by the consumer: full prompt text → model response text.
LlmCall = Callable[[str], str]

DECOMPOSE_SCHEMA_HINT = """
Return ONLY a JSON object (no markdown fences) with this shape:
{
  "summary": "one-sentence overview of what you extracted",
  "remaining_identity_body": "slim identity directives that should stay in identity",
  "suggestions": [
    {
      "type": "trait" | "speech" | "role" | "output_rules",
      "name": "PascalOrCamelCase unique name",
      "priority": "high" | "medium" | "low",   // traits only; omit otherwise
      "conflicts": ["OtherTraitName"],         // traits only; optional
      "mode": "prompt" | "rewriter",           // speech only; default prompt
      "body": "short imperative directives, one consistent register",
      "rationale": "why this should be its own module"
    }
  ]
}
Rules:
- Prefer short imperative bodies (no essays).
- Do not invent tools/commands machinery; distill behavioral/speech rules only.
- Traits that oppose each other should list each other in conflicts (mutual).
- remaining_identity_body must still be a valid standalone identity if used alone.
""".strip()


@dataclass
class ModuleSuggestion:
    type: SuggestionType
    name: str
    body: str
    rationale: str = ""
    priority: str | None = None
    conflicts: list[str] = field(default_factory=list)
    mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "name": self.name,
            "body": self.body,
            "rationale": self.rationale,
        }
        if self.priority is not None:
            data["priority"] = self.priority
        if self.conflicts:
            data["conflicts"] = list(self.conflicts)
        if self.mode is not None:
            data["mode"] = self.mode
        return data


@dataclass
class DecompositionResult:
    source_path: Path | None
    source_kind: Literal["identity", "skill", "raw"]
    summary: str
    remaining_identity_body: str
    suggestions: list[ModuleSuggestion]
    draft_paths: list[Path] = field(default_factory=list)
    raw_llm_response: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path) if self.source_path else None,
            "source_kind": self.source_kind,
            "summary": self.summary,
            "remaining_identity_body": self.remaining_identity_body,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "draft_paths": [str(p) for p in self.draft_paths],
        }


def build_decompose_prompt(
    *,
    source_text: str,
    source_kind: Literal["identity", "skill", "raw"] = "raw",
    source_name: str | None = None,
    provenance: str | None = None,
) -> str:
    """Prompt for an external LLM (consumer supplies the call)."""
    kind_note = {
        "identity": "This is a monolithic identity / system prompt. Suggest extractions.",
        "skill": (
            "This is a foreign/vendored skill. Distill reusable speech/trait rules; "
            "ignore host-specific commands, CLI flags, statusline, and tooling."
        ),
        "raw": "This is free-form agent instruction text. Suggest modular extractions.",
    }[source_kind]
    header = f"Source kind: {source_kind}"
    if source_name:
        header += f"\nSource name: {source_name}"
    if provenance:
        header += f"\nProvenance: {provenance}"
    return (
        f"{header}\n{kind_note}\n\n"
        f"{DECOMPOSE_SCHEMA_HINT}\n\n"
        f"--- SOURCE START ---\n{source_text.rstrip()}\n--- SOURCE END ---\n"
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text)
    if fence:
        return fence.group(1).strip()
    return text


def parse_decomposition_response(text: str) -> tuple[str, str, list[ModuleSuggestion]]:
    """Parse LLM JSON into suggestions. Raises ValidationError on bad shape."""
    cleaned = _strip_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"decompose: invalid JSON from LLM: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("decompose: LLM response must be a JSON object")

    summary = str(data.get("summary") or "").strip()
    remaining = str(data.get("remaining_identity_body") or "").strip()
    raw_suggestions = data.get("suggestions")
    if not isinstance(raw_suggestions, list):
        raise ValidationError("decompose: 'suggestions' must be a list")

    suggestions: list[ModuleSuggestion] = []
    for i, item in enumerate(raw_suggestions):
        if not isinstance(item, dict):
            raise ValidationError(f"decompose: suggestions[{i}] must be an object")
        stype = item.get("type")
        if stype not in ("trait", "speech", "role", "output_rules"):
            raise ValidationError(
                f"decompose: suggestions[{i}].type invalid: {stype!r}"
            )
        name = str(item.get("name") or "").strip()
        body = str(item.get("body") or "").strip()
        if not name or not body:
            raise ValidationError(
                f"decompose: suggestions[{i}] requires non-empty name and body"
            )
        priority = item.get("priority")
        if stype == "trait":
            if priority not in ("high", "medium", "low"):
                priority = "medium"
        else:
            priority = None
        conflicts = item.get("conflicts") or []
        if not isinstance(conflicts, list):
            conflicts = []
        mode = item.get("mode")
        if stype == "speech":
            if mode not in ("prompt", "rewriter"):
                mode = "prompt"
        else:
            mode = None
        suggestions.append(
            ModuleSuggestion(
                type=stype,  # type: ignore[arg-type]
                name=name,
                body=body,
                rationale=str(item.get("rationale") or "").strip(),
                priority=str(priority) if priority else None,
                conflicts=[str(c) for c in conflicts],
                mode=str(mode) if mode else None,
            )
        )
    return summary, remaining, suggestions


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()) or "Module"
    return cleaned[:64]


def render_suggestion_markdown(
    suggestion: ModuleSuggestion,
    *,
    source: str | None = None,
    origin: str | None = None,
) -> str:
    """Render a draft overlay module (adaptation: extracted when source given)."""
    lines = ["---", f"type: {suggestion.type}", f"name: {suggestion.name}"]
    if suggestion.type == "trait":
        lines.append(f"priority: {suggestion.priority or 'medium'}")
        if suggestion.conflicts:
            lines.append("conflicts: [" + ", ".join(suggestion.conflicts) + "]")
    if suggestion.type == "speech" and suggestion.mode:
        lines.append(f"mode: {suggestion.mode}")
    if source:
        lines.append(f"source: {source}")
        lines.append("adaptation: extracted")
    if origin:
        lines.append(f"origin: {origin}")
    lines.append("---")
    if suggestion.rationale:
        lines.append(f"<!-- draft rationale: {suggestion.rationale} -->")
    lines.append(suggestion.body.rstrip())
    lines.append("")
    return "\n".join(lines)


def write_draft_modules(
    suggestions: list[ModuleSuggestion],
    out_dir: Path,
    *,
    source: str | None = None,
    origin: str | None = None,
    remaining_identity_body: str | None = None,
    identity_name: str = "IdentitySlim",
) -> list[Path]:
    """Write draft .md modules under out_dir. Does not overwrite unless same name."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if remaining_identity_body is not None and remaining_identity_body.strip():
        ident_path = out_dir / f"identity_{_safe_filename(identity_name)}.md"
        ident_path.write_text(
            "---\n"
            f"type: identity\nname: {identity_name}\n"
            "---\n"
            f"{remaining_identity_body.strip()}\n",
            encoding="utf-8",
        )
        paths.append(ident_path)
    for sug in suggestions:
        sub = out_dir / sug.type
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / f"{_safe_filename(sug.name)}.md"
        path.write_text(
            render_suggestion_markdown(sug, source=source, origin=origin),
            encoding="utf-8",
        )
        paths.append(path)
    return paths


def load_decompose_source(
    path: Path,
) -> tuple[str, Literal["identity", "skill", "raw"], str | None]:
    """Load a file; detect identity frontmatter vs raw/skill body."""
    text = path.read_text(encoding="utf-8")
    try:
        fm, body = split_frontmatter(text)
        if fm.get("type") == "identity":
            return body.strip("\n"), "identity", str(fm.get("name") or path.stem)
        # Overlay / other typed module — use renderable body
        return body.strip("\n") or text, "skill", str(fm.get("name") or path.stem)
    except ValidationError:
        return text, "raw", path.stem


def decompose(
    source: str | Path,
    *,
    llm_call: LlmCall | None = None,
    llm_response: str | None = None,
    out_dir: Path | None = None,
    source_kind: Literal["identity", "skill", "raw"] | None = None,
    provenance: str | None = None,
    source_relpath: str | None = None,
    origin: str | None = None,
    write_drafts: bool = True,
) -> DecompositionResult:
    """
    Suggest module extractions from a monolith or vendored skill.

    Provide either ``llm_call`` (invoked with the decompose prompt) or
    ``llm_response`` (precomputed JSON) — the core never contacts a model itself.
    """
    source_path: Path | None
    if isinstance(source, Path):
        source_path = source
        text, detected_kind, name = load_decompose_source(source)
        kind = source_kind or detected_kind
    else:
        source_path = None
        text = source
        kind = source_kind or "raw"
        name = None

    if llm_response is None:
        if llm_call is None:
            raise CompositionError(
                "decompose requires llm_call=... or llm_response=... "
                "(composer never calls an LLM itself)"
            )
        prompt = build_decompose_prompt(
            source_text=text,
            source_kind=kind,
            source_name=name,
            provenance=provenance or (str(source_path) if source_path else None),
        )
        llm_response = llm_call(prompt)

    summary, remaining, suggestions = parse_decomposition_response(llm_response)
    draft_paths: list[Path] = []
    if write_drafts and out_dir is not None:
        draft_paths = write_draft_modules(
            suggestions,
            out_dir,
            source=source_relpath,
            origin=origin,
            remaining_identity_body=remaining or None,
            identity_name=(name or "IdentitySlim"),
        )
    return DecompositionResult(
        source_path=source_path,
        source_kind=kind,
        summary=summary,
        remaining_identity_body=remaining,
        suggestions=suggestions,
        draft_paths=draft_paths,
        raw_llm_response=llm_response,
    )
