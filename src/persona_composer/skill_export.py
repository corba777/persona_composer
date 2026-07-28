"""Compose + write Agent Skill / host instruction artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from persona_composer.compose import CompositionResult, compose
from persona_composer.compliance import (
    ComplianceRuleset,
    enforce_compliance,
    resolve_compliance_ruleset,
)
from persona_composer.models import Manifest, ModuleType, SkeletonConfig
from persona_composer.parse import parse_module
from persona_composer.render_skill import render_skill_body, render_skill_md
from persona_composer.skill_settings import (
    SkillMeta,
    SkillSettings,
    SkillTarget,
    load_skill_settings,
)
from persona_composer.validate import resolve_conflicts


@dataclass
class SkillExportResult:
    skill_md: str
    skill_body: str
    prompt_xml: str
    composition: CompositionResult

    @property
    def manifest(self) -> Manifest:
        return self.composition.manifest

    def manifest_json(self, *, indent: int = 2) -> str:
        return self.composition.manifest_json(indent=indent)


def _attach_export_meta(
    composition: CompositionResult,
    *,
    skill: SkillMeta,
    targets: list[SkillTarget],
) -> None:
    composition.manifest.artifact_format = "skill_md"
    composition.manifest.exports = [
        {
            "kind": t.kind,
            "path": str(t.path),
            "skill_name": skill.name,
        }
        for t in targets
    ]


def compose_skill(
    settings: SkillSettings | Path | str,
    *,
    skeleton: SkeletonConfig | None = None,
    timestamp: str | None = None,
    compliance: bool | Path | str | ComplianceRuleset | None = None,
) -> SkillExportResult:
    """Validate/compose modules, then render Markdown skill + XML prompt."""
    if not isinstance(settings, SkillSettings):
        settings = load_skill_settings(settings)

    composition = compose(
        settings.identity,
        settings.modules,
        skeleton=skeleton,
        module_root=settings.module_root,
        library_root=settings.module_root,
        timestamp=timestamp,
        compliance=compliance,
    )
    _attach_export_meta(
        composition, skill=settings.skill, targets=settings.targets
    )

    identity = parse_module(
        settings.identity, module_root=settings.module_root
    )
    parsed = [identity] + [
        parse_module(p, module_root=settings.module_root)
        for p in settings.modules
    ]
    traits = [m for m in parsed if m.type == ModuleType.TRAIT]
    resolutions = resolve_conflicts(traits)
    ts = composition.manifest.timestamp

    skill_md = render_skill_md(
        parsed,
        resolutions,
        skill_meta=settings.skill,
        skeleton=skeleton,
        as_of=ts,
        with_frontmatter=True,
    )
    skill_body = render_skill_body(
        parsed,
        resolutions,
        skill_meta=settings.skill,
        skeleton=skeleton,
        as_of=ts,
    )
    ruleset = resolve_compliance_ruleset(compliance)
    if ruleset is not None:
        enforce_compliance(skill_md, ruleset, artifact="skill Markdown")
        if composition.manifest.compliance is None:
            composition.manifest.compliance = ruleset.to_manifest_meta()
    return SkillExportResult(
        skill_md=skill_md,
        skill_body=skill_body,
        prompt_xml=composition.prompt_xml,
        composition=composition,
    )


def content_for_target(result: SkillExportResult, kind: str) -> str:
    if kind == "skill_md":
        return result.skill_md
    if kind in ("agents_md", "copilot_instructions"):
        return result.skill_body
    raise ValueError(f"unknown target kind: {kind}")


def write_skill_targets(
    result: SkillExportResult,
    settings: SkillSettings,
    *,
    manifest_path: Path | None = None,
) -> list[Path]:
    """Write each configured target; optionally write manifest JSON."""
    written: list[Path] = []
    for target in settings.targets:
        target.path.parent.mkdir(parents=True, exist_ok=True)
        text = content_for_target(result, target.kind)
        target.path.write_text(text, encoding="utf-8")
        written.append(target.path)

    if manifest_path is not None:
        manifest_path = Path(manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(result.manifest_json(), encoding="utf-8")
        written.append(manifest_path)
    elif settings.targets:
        # Sibling manifest next to the first skill_md target when present.
        primary = next(
            (t for t in settings.targets if t.kind == "skill_md"),
            settings.targets[0],
        )
        sibling = primary.path.parent / "persona_manifest.json"
        sibling.write_text(result.manifest_json(), encoding="utf-8")
        written.append(sibling)

    return written
