"""Skill export / settings tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from persona_composer.errors import ValidationError
from persona_composer.skill_export import (
    compose_skill,
    content_for_target,
    write_skill_targets,
)
from persona_composer.skill_settings import (
    load_skill_settings,
    skill_settings_adhoc,
    skill_settings_from_dict,
)

FIXED_TS = "2026-07-20T15:00:00+00:00"
GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "full_skill.md"
MODULES = Path(__file__).parent / "fixtures" / "modules"


def _full_settings():
    return skill_settings_adhoc(
        identity=MODULES / "identity" / "guard.md",
        modules=[
            MODULES / "speech" / "curt.md",
            MODULES / "roles" / "gatekeeper.md",
            MODULES / "traits" / "territorial.md",
            MODULES / "traits" / "cautious.md",
            MODULES / "relationships" / "ally_bob.md",
            MODULES / "output_rules" / "default.md",
        ],
        module_root=MODULES,
        name="persona",
        description="Composed gate-guard persona for skill export tests.",
    )


def test_golden_full_skill() -> None:
    result = compose_skill(_full_settings(), timestamp=FIXED_TS)
    expected = GOLDEN.read_text(encoding="utf-8")
    assert result.skill_md == expected
    assert result.prompt_xml.startswith("<agent_prompt>")
    assert result.manifest.artifact_format == "skill_md"


def test_settings_loader_resolves_relative(tmp_path: Path) -> None:
    # Copy-style: point module_root at fixtures via absolute path in JSON
    settings_path = tmp_path / "persona.settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "module_root": str(MODULES),
                "identity": "identity/guard.md",
                "modules": ["speech/curt.md"],
                "skill": {
                    "name": "curt-guard",
                    "description": "Brief guard.",
                },
                "targets": [
                    {"kind": "skill_md", "path": "out/SKILL.md"},
                    {"kind": "agents_md", "path": "out/AGENTS.md"},
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = load_skill_settings(settings_path)
    assert settings.identity == MODULES / "identity" / "guard.md"
    assert settings.modules[0] == MODULES / "speech" / "curt.md"
    assert settings.targets[0].path == (tmp_path / "out" / "SKILL.md").resolve()
    assert settings.skill.name == "curt-guard"


def test_settings_missing_identity() -> None:
    with pytest.raises(ValidationError, match="identity"):
        skill_settings_from_dict({"modules": []})


def test_multi_target_write_frontmatter(tmp_path: Path) -> None:
    settings = skill_settings_adhoc(
        identity=MODULES / "identity" / "guard.md",
        modules=[],
        module_root=MODULES,
        name="solo",
        description="Identity alone.",
        out=tmp_path / "skill" / "SKILL.md",
    )
    # Replace targets with both kinds
    from persona_composer.skill_settings import SkillTarget

    settings.targets = [
        SkillTarget(kind="skill_md", path=tmp_path / "SKILL.md"),
        SkillTarget(kind="agents_md", path=tmp_path / "AGENTS.md"),
        SkillTarget(
            kind="copilot_instructions",
            path=tmp_path / ".github" / "copilot-instructions.md",
        ),
    ]
    result = compose_skill(settings, timestamp=FIXED_TS)
    written = write_skill_targets(
        result, settings, manifest_path=tmp_path / "manifest.json"
    )
    skill_text = (tmp_path / "SKILL.md").read_text(encoding="utf-8")
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert skill_text.startswith("---\nname: solo\n")
    assert not agents_text.startswith("---")
    assert agents_text.startswith("# solo\n")
    assert content_for_target(result, "agents_md") == result.skill_body
    assert (tmp_path / "manifest.json").is_file()
    assert any(p.name == "manifest.json" for p in written)
    data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert data["artifact_format"] == "skill_md"
    assert len(data["exports"]) == 3
