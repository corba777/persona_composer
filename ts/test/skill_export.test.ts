/** Skill export / settings tests. */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { ValidationError } from "../src/errors.js";
import {
  composeSkill,
  contentForTarget,
  writeSkillTargets,
} from "../src/skill_export.js";
import {
  loadSkillSettings,
  skillSettingsAdhoc,
  skillSettingsFromDict,
} from "../src/skill_settings.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MODULES = path.resolve(HERE, "../../tests/fixtures/modules");
const GOLDEN = path.resolve(HERE, "../../tests/fixtures/golden/full_skill.md");
const FIXED_TS = "2026-07-20T15:00:00+00:00";

function fullSettings() {
  return skillSettingsAdhoc({
    identity: path.join(MODULES, "identity/guard.md"),
    modules: [
      path.join(MODULES, "speech/curt.md"),
      path.join(MODULES, "roles/gatekeeper.md"),
      path.join(MODULES, "traits/territorial.md"),
      path.join(MODULES, "traits/cautious.md"),
      path.join(MODULES, "relationships/ally_bob.md"),
      path.join(MODULES, "output_rules/default.md"),
    ],
    moduleRoot: MODULES,
    name: "persona",
    description: "Composed gate-guard persona for skill export tests.",
  });
}

describe("skill export", () => {
  it("matches golden full skill", () => {
    const result = composeSkill(fullSettings(), { timestamp: FIXED_TS });
    const expected = readFileSync(GOLDEN, "utf-8");
    expect(result.skillMd).toBe(expected);
    expect(result.promptXml.startsWith("<agent_prompt>")).toBe(true);
    expect(result.manifest.artifact_format).toBe("skill_md");
  });

  it("loads settings with relative paths", () => {
    const dir = fsTemp();
    const settingsPath = path.join(dir, "persona.settings.json");
    writeFileSync(
      settingsPath,
      JSON.stringify({
        module_root: MODULES,
        identity: "identity/guard.md",
        modules: ["speech/curt.md"],
        skill: { name: "curt-guard", description: "Brief guard." },
        targets: [
          { kind: "skill_md", path: "out/SKILL.md" },
          { kind: "agents_md", path: "out/AGENTS.md" },
        ],
      }),
      "utf-8",
    );
    const settings = loadSkillSettings(settingsPath);
    expect(settings.identity).toBe(path.join(MODULES, "identity/guard.md"));
    expect(settings.modules[0]).toBe(path.join(MODULES, "speech/curt.md"));
    expect(settings.targets[0]!.path).toBe(path.join(dir, "out/SKILL.md"));
    expect(settings.skill.name).toBe("curt-guard");
  });

  it("requires identity", () => {
    expect(() => skillSettingsFromDict({ modules: [] })).toThrow(ValidationError);
  });

  it("writes skill_md with frontmatter and agents_md without", () => {
    const dir = fsTemp();
    const settings = skillSettingsAdhoc({
      identity: path.join(MODULES, "identity/guard.md"),
      modules: [],
      moduleRoot: MODULES,
      name: "solo",
      description: "Identity alone.",
    });
    settings.targets = [
      { kind: "skill_md", path: path.join(dir, "SKILL.md") },
      { kind: "agents_md", path: path.join(dir, "AGENTS.md") },
      {
        kind: "copilot_instructions",
        path: path.join(dir, ".github/copilot-instructions.md"),
      },
    ];
    const result = composeSkill(settings, { timestamp: FIXED_TS });
    writeSkillTargets(result, settings, {
      manifestPath: path.join(dir, "manifest.json"),
    });
    const skillText = readFileSync(path.join(dir, "SKILL.md"), "utf-8");
    const agentsText = readFileSync(path.join(dir, "AGENTS.md"), "utf-8");
    expect(skillText.startsWith("---\nname: solo\n")).toBe(true);
    expect(agentsText.startsWith("---")).toBe(false);
    expect(agentsText.startsWith("# solo\n")).toBe(true);
    expect(contentForTarget(result, "agents_md")).toBe(result.skillBody);
    const data = JSON.parse(
      readFileSync(path.join(dir, "manifest.json"), "utf-8"),
    );
    expect(data.artifact_format).toBe("skill_md");
    expect(data.exports).toHaveLength(3);
  });
});

function fsTemp(): string {
  const dir = path.join(
    os.tmpdir(),
    `persona-skill-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );
  mkdirSync(dir, { recursive: true });
  return dir;
}
