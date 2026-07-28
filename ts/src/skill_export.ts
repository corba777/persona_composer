/** Compose + write Agent Skill / host instruction artifacts. */

import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { compose, type CompositionResult } from "./compose.js";
import {
  complianceManifestMeta,
  enforceCompliance,
  resolveComplianceRuleset,
  type ComplianceInput,
} from "./compliance.js";
import type { Manifest, SkeletonConfig } from "./models.js";
import { parseModule } from "./parse.js";
import { renderSkillBody, renderSkillMd } from "./render_skill.js";
import {
  loadSkillSettings,
  type SkillMeta,
  type SkillSettings,
  type SkillTarget,
} from "./skill_settings.js";
import { resolveConflicts } from "./validate.js";

export interface SkillExportResult {
  skillMd: string;
  skillBody: string;
  promptXml: string;
  composition: CompositionResult;
  manifest: Manifest;
  manifestJson(indent?: number): string;
}

function attachExportMeta(
  composition: CompositionResult,
  skill: SkillMeta,
  targets: SkillTarget[],
): void {
  composition.manifest.artifact_format = "skill_md";
  composition.manifest.exports = targets.map((t) => ({
    kind: t.kind,
    path: t.path,
    skill_name: skill.name,
  }));
}

export function composeSkill(
  settingsInput: SkillSettings | string,
  options: {
    skeleton?: SkeletonConfig;
    timestamp?: string;
    compliance?: ComplianceInput;
  } = {},
): SkillExportResult {
  const settings =
    typeof settingsInput === "string"
      ? loadSkillSettings(settingsInput)
      : settingsInput;

  const composition = compose(settings.identity, settings.modules, {
    skeleton: options.skeleton,
    moduleRoot: settings.moduleRoot,
    libraryRoot: settings.moduleRoot,
    timestamp: options.timestamp,
    compliance: options.compliance,
  });
  attachExportMeta(composition, settings.skill, settings.targets);

  const identity = parseModule(settings.identity, {
    moduleRoot: settings.moduleRoot,
  });
  const parsed = [
    identity,
    ...settings.modules.map((p) =>
      parseModule(p, { moduleRoot: settings.moduleRoot }),
    ),
  ];
  const traits = parsed.filter((m) => m.type === "trait");
  const resolutions = resolveConflicts(traits);
  const ts = composition.manifest.timestamp;

  const skillMd = renderSkillMd(parsed, resolutions, {
    skillMeta: settings.skill,
    skeleton: options.skeleton,
    asOf: ts,
    withFrontmatter: true,
  });
  const skillBody = renderSkillBody(parsed, resolutions, {
    skillMeta: settings.skill,
    skeleton: options.skeleton,
    asOf: ts,
  });

  const ruleset = resolveComplianceRuleset(options.compliance);
  if (ruleset) {
    enforceCompliance(skillMd, ruleset, "skill Markdown");
    if (!composition.manifest.compliance) {
      composition.manifest.compliance = complianceManifestMeta(ruleset);
    }
  }

  return {
    skillMd,
    skillBody,
    promptXml: composition.promptXml,
    composition,
    manifest: composition.manifest,
    manifestJson(indent = 2) {
      return composition.manifestJson(indent);
    },
  };
}

export function contentForTarget(
  result: SkillExportResult,
  kind: string,
): string {
  if (kind === "skill_md") return result.skillMd;
  if (kind === "agents_md" || kind === "copilot_instructions") {
    return result.skillBody;
  }
  throw new Error(`unknown target kind: ${kind}`);
}

export function writeSkillTargets(
  result: SkillExportResult,
  settings: SkillSettings,
  options: { manifestPath?: string } = {},
): string[] {
  const written: string[] = [];
  for (const target of settings.targets) {
    mkdirSync(path.dirname(target.path), { recursive: true });
    writeFileSync(target.path, contentForTarget(result, target.kind), "utf-8");
    written.push(target.path);
  }

  if (options.manifestPath) {
    const mp = path.resolve(options.manifestPath);
    mkdirSync(path.dirname(mp), { recursive: true });
    writeFileSync(mp, result.manifestJson(), "utf-8");
    written.push(mp);
  } else if (settings.targets.length) {
    const primary =
      settings.targets.find((t) => t.kind === "skill_md") ??
      settings.targets[0]!;
    const sibling = path.join(
      path.dirname(primary.path),
      "persona_manifest.json",
    );
    writeFileSync(sibling, result.manifestJson(), "utf-8");
    written.push(sibling);
  }

  return written;
}
