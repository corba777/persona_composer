"""XML skeleton renderer."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom

from persona_composer.models import (
    ConflictResolution,
    Module,
    ModuleType,
    SkeletonConfig,
    SpeechMode,
)


def _elem(tag: str, text: str = "", **attrs: str) -> ET.Element:
    el = ET.Element(tag, {k: v for k, v in attrs.items() if v is not None})
    if text:
        el.text = text
    return el


def _append_block(parent: ET.Element, tag: str, body: str, **attrs: str) -> None:
    el = _elem(tag, **attrs)
    # Store body as text; we'll serialize with minimal escaping for readability.
    el.text = body
    parent.append(el)


def render_prompt(
    modules: list[Module],
    resolutions: list[ConflictResolution],
    *,
    skeleton: SkeletonConfig | None = None,
) -> str:
    """Render the fixed-order XML system prompt."""
    skeleton = skeleton or SkeletonConfig()

    identity = next(m for m in modules if m.type == ModuleType.IDENTITY)
    speeches = [
        m
        for m in modules
        if m.type == ModuleType.SPEECH and m.mode == SpeechMode.PROMPT
    ]
    roles = [m for m in modules if m.type == ModuleType.ROLE]
    traits = [m for m in modules if m.type == ModuleType.TRAIT]
    relationships = [m for m in modules if m.type == ModuleType.RELATIONSHIP]
    output_modules = [m for m in modules if m.type == ModuleType.OUTPUT_RULES]

    # Deterministic trait order: by name (priority does not sort)
    traits = sorted(traits, key=lambda m: m.name)
    speeches = sorted(speeches, key=lambda m: m.name)
    relationships = sorted(relationships, key=lambda m: (m.agent or "", m.name))

    root = ET.Element("agent_prompt")

    _append_block(root, "identity", identity.render_body, name=identity.name)

    if speeches:
        speech_wrap = ET.SubElement(root, "speech")
        for s in speeches:
            _append_block(speech_wrap, "style", s.render_body, name=s.name)

    precedence = ET.SubElement(root, "precedence")
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
    precedence.text = "\n".join(lines)

    if roles:
        role = roles[0]
        _append_block(root, "role", role.render_body, name=role.name)

    if traits:
        traits_wrap = ET.SubElement(root, "traits")
        for t in traits:
            assert t.priority is not None
            _append_block(
                traits_wrap,
                "trait",
                t.render_body,
                name=t.name,
                priority=t.priority.value,
            )

    if resolutions:
        cr = ET.SubElement(root, "conflict_rule")
        cr.text = "\n".join(r.to_line() for r in resolutions)

    if relationships:
        rel_wrap = ET.SubElement(root, "relationships")
        for r in relationships:
            assert r.agent is not None and r.status is not None
            _append_block(
                rel_wrap,
                "relation",
                r.render_body,
                agent=r.agent,
                status=r.status,
                name=r.name,
            )

    # Module body wins; else skeleton fallback; else omit (optional slot).
    if output_modules:
        out = output_modules[0]
        _append_block(root, "output_rules", out.render_body, name=out.name)
    elif skeleton.output_rules.strip():
        _append_block(root, "output_rules", skeleton.output_rules.strip())

    return _serialize(root)


def _serialize(root: ET.Element) -> str:
    """Pretty-print XML with text content escaped."""
    rough = ET.tostring(root, encoding="unicode")
    parsed = minidom.parseString(rough)
    # minidom adds XML declaration; strip for prompt cleanliness
    pretty = parsed.toprettyxml(indent="  ")
    lines = pretty.splitlines()
    # Drop declaration line if present
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    # Drop empty lines introduced by toprettyxml
    cleaned = "\n".join(line for line in lines if line.strip())
    return cleaned + "\n"
