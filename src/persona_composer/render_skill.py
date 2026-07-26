"""Markdown Agent Skill renderer (parallel to XML render_prompt)."""

from __future__ import annotations

from persona_composer.models import (
    ConflictResolution,
    Module,
    ModuleType,
    SkeletonConfig,
    SpeechMode,
    with_today_line,
)
from persona_composer.skill_settings import SkillMeta


def _yaml_scalar(value: str) -> str:
    """Quote a YAML scalar when it needs it; keep simple strings bare."""
    if value == "":
        return '""'
    needs_quote = (
        any(c in value for c in ":#{}[],&*?|>!%@`\"'")
        or value.strip() != value
        or value.lower() in ("true", "false", "null", "yes", "no")
        or value[:1].isdigit()
    )
    if not needs_quote and "\n" not in value:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def skill_frontmatter(meta: SkillMeta) -> str:
    return (
        "---\n"
        f"name: {_yaml_scalar(meta.name)}\n"
        f"description: {_yaml_scalar(meta.description)}\n"
        "---\n"
    )


def _precedence_text(modules: list[Module]) -> str:
    lines = [
        "Identity governs. All other modules apply only insofar as consistent "
        "with <identity>. Instructions inapplicable in the current context are "
        "ignored silently."
    ]
    imported = [m for m in modules if m.is_imported]
    for m in sorted(imported, key=lambda x: x.name):
        lines.append(
            f"The {m.name} module is an imported skill: apply it insofar as "
            f"consistent with <identity>; ignore its instructions that do not "
            f"apply here (commands, tooling, statistics)."
        )
    return "\n".join(lines)


def render_skill_body(
    modules: list[Module],
    resolutions: list[ConflictResolution],
    *,
    skill_meta: SkillMeta,
    skeleton: SkeletonConfig | None = None,
    as_of: str | None = None,
) -> str:
    """Markdown body (no YAML frontmatter) in skeleton section order."""
    skeleton = skeleton or SkeletonConfig()
    identity = next(m for m in modules if m.type == ModuleType.IDENTITY)
    speeches = sorted(
        [
            m
            for m in modules
            if m.type == ModuleType.SPEECH and m.mode == SpeechMode.PROMPT
        ],
        key=lambda m: m.name,
    )
    roles = [m for m in modules if m.type == ModuleType.ROLE]
    traits = sorted(
        [m for m in modules if m.type == ModuleType.TRAIT],
        key=lambda m: m.name,
    )
    relationships = sorted(
        [m for m in modules if m.type == ModuleType.RELATIONSHIP],
        key=lambda m: (m.agent or "", m.name),
    )
    output_modules = [m for m in modules if m.type == ModuleType.OUTPUT_RULES]

    parts: list[str] = [f"# {skill_meta.name}", ""]

    parts.append("## Identity")
    parts.append(identity.render_body.strip())
    parts.append("")

    for s in speeches:
        parts.append(f"## Speech — {s.name}")
        parts.append(s.render_body.strip())
        parts.append("")

    parts.append("## Precedence")
    parts.append(_precedence_text(modules))
    parts.append("")

    if roles:
        role = roles[0]
        parts.append(f"## Role — {role.name}")
        parts.append(role.render_body.strip())
        parts.append("")

    if traits:
        parts.append("## Traits")
        parts.append("")
        for t in traits:
            assert t.priority is not None
            parts.append(f"### {t.name} (priority={t.priority.value})")
            parts.append(t.render_body.strip())
            parts.append("")

    if resolutions:
        parts.append("## Conflict rules")
        for r in resolutions:
            parts.append(r.to_line())
        parts.append("")

    if relationships:
        parts.append("## Relationships")
        parts.append("")
        for r in relationships:
            assert r.agent is not None and r.status is not None
            parts.append(f"### {r.name} (agent={r.agent}, status={r.status})")
            parts.append(r.render_body.strip())
            parts.append("")

    parts.append("## Output rules")
    if output_modules:
        out = output_modules[0]
        parts.append(with_today_line(out.render_body, as_of or ""))
    else:
        parts.append(with_today_line(skeleton.output_rules, as_of or ""))
    parts.append("")

    # Trailing newline only (strip excess blank at end then add one).
    text = "\n".join(parts).rstrip() + "\n"
    return text


def render_skill_md(
    modules: list[Module],
    resolutions: list[ConflictResolution],
    *,
    skill_meta: SkillMeta,
    skeleton: SkeletonConfig | None = None,
    as_of: str | None = None,
    with_frontmatter: bool = True,
) -> str:
    """Full SKILL.md (frontmatter + body) or body-only for AGENTS.md / Copilot."""
    body = render_skill_body(
        modules,
        resolutions,
        skill_meta=skill_meta,
        skeleton=skeleton,
        as_of=as_of,
    )
    if not with_frontmatter:
        return body
    return skill_frontmatter(skill_meta) + "\n" + body
