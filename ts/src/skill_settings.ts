/** Settings for compiling Agent Skills / host instruction files. */

import { readFileSync } from "node:fs";
import path from "node:path";

import { ValidationError } from "./errors.js";

export type TargetKind = "skill_md" | "agents_md" | "copilot_instructions";

export interface SkillMeta {
  name: string;
  description: string;
}

export interface SkillTarget {
  kind: TargetKind;
  path: string;
}

export interface SkillSettings {
  identity: string;
  modules: string[];
  moduleRoot?: string;
  skill: SkillMeta;
  targets: SkillTarget[];
  baseDir: string;
}

function resolvePath(base: string, value: string): string {
  if (path.isAbsolute(value)) return path.normalize(value);
  return path.resolve(base, value);
}

export function skillSettingsFromDict(
  data: Record<string, unknown>,
  baseDir: string = process.cwd(),
): SkillSettings {
  const base = path.resolve(baseDir);
  const identityRaw = data.identity;
  if (!identityRaw) {
    throw new ValidationError("settings require 'identity'");
  }

  const moduleRootRaw = data.module_root;
  const moduleRoot =
    moduleRootRaw != null
      ? resolvePath(base, String(moduleRootRaw))
      : undefined;

  const identity = resolvePath(moduleRoot ?? base, String(identityRaw));
  const modulesRaw = data.modules ?? [];
  if (!Array.isArray(modulesRaw)) {
    throw new ValidationError("'modules' must be a list of paths");
  }
  const modules = modulesRaw.map((p) =>
    resolvePath(moduleRoot ?? base, String(p)),
  );

  const skillRaw = (data.skill ?? {}) as Record<string, unknown>;
  if (typeof skillRaw !== "object" || skillRaw == null || Array.isArray(skillRaw)) {
    throw new ValidationError("'skill' must be an object");
  }
  const name = String(skillRaw.name ?? "persona");
  const description = String(
    skillRaw.description ?? "Composed coding persona.",
  );

  const targetsRaw = data.targets ?? [];
  if (!Array.isArray(targetsRaw)) {
    throw new ValidationError("'targets' must be a list");
  }
  const targets: SkillTarget[] = [];
  targetsRaw.forEach((item, i) => {
    if (typeof item !== "object" || item == null || Array.isArray(item)) {
      throw new ValidationError(`targets[${i}] must be an object`);
    }
    const row = item as Record<string, unknown>;
    const kind = row.kind;
    const tpath = row.path;
    if (
      kind !== "skill_md" &&
      kind !== "agents_md" &&
      kind !== "copilot_instructions"
    ) {
      throw new ValidationError(
        `targets[${i}].kind must be skill_md, agents_md, or ` +
          `copilot_instructions, got ${JSON.stringify(kind)}`,
      );
    }
    if (!tpath) {
      throw new ValidationError(`targets[${i}] requires 'path'`);
    }
    targets.push({
      kind,
      path: resolvePath(base, String(tpath)),
    });
  });

  return {
    identity,
    modules,
    moduleRoot,
    skill: { name, description },
    targets,
    baseDir: base,
  };
}

export function loadSkillSettings(filePath: string): SkillSettings {
  const settingsPath = path.resolve(filePath);
  let data: unknown;
  try {
    data = JSON.parse(readFileSync(settingsPath, "utf-8"));
  } catch (exc) {
    throw new ValidationError(
      `invalid or missing settings JSON: ${(exc as Error).message}`,
    );
  }
  if (typeof data !== "object" || data == null || Array.isArray(data)) {
    throw new ValidationError("settings root must be a JSON object");
  }
  return skillSettingsFromDict(
    data as Record<string, unknown>,
    path.dirname(settingsPath),
  );
}

export function skillSettingsAdhoc(opts: {
  identity: string;
  modules?: string[];
  moduleRoot?: string;
  name?: string;
  description?: string;
  out?: string;
  baseDir?: string;
}): SkillSettings {
  const base = path.resolve(opts.baseDir ?? process.cwd());
  const targets: SkillTarget[] = [];
  if (opts.out) {
    targets.push({ kind: "skill_md", path: path.resolve(opts.out) });
  }
  return {
    identity: path.resolve(opts.identity),
    modules: (opts.modules ?? []).map((m) => path.resolve(m)),
    moduleRoot: opts.moduleRoot ? path.resolve(opts.moduleRoot) : undefined,
    skill: {
      name: opts.name ?? "persona",
      description: opts.description ?? "Composed coding persona.",
    },
    targets,
    baseDir: base,
  };
}
