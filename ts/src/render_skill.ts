/** Markdown Agent Skill renderer (parallel to XML renderPrompt). */

import type { ConflictResolution, Module, SkeletonConfig } from "./models.js";
import {
  conflictRuleLine,
  isImported,
  renderBody,
  skeletonConfig,
  withTodayLine,
} from "./models.js";
import type { SkillMeta } from "./skill_settings.js";

function yamlScalar(value: string): string {
  if (value === "") return '""';
  const needsQuote =
    /[:#{}[\],&*?|>!%@`"'']/.test(value) ||
    value.trim() !== value ||
    ["true", "false", "null", "yes", "no"].includes(value.toLowerCase()) ||
    /^\d/.test(value) ||
    value.includes("\n");
  if (!needsQuote) return value;
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

export function skillFrontmatter(meta: SkillMeta): string {
  return (
    "---\n" +
    `name: ${yamlScalar(meta.name)}\n` +
    `description: ${yamlScalar(meta.description)}\n` +
    "---\n"
  );
}

function precedenceText(modules: Module[]): string {
  const lines = [
    "Identity governs. All other modules apply only insofar as consistent " +
      "with <identity>. Instructions inapplicable in the current context are " +
      "ignored silently.",
  ];
  const imported = modules
    .filter(isImported)
    .sort((a, b) => a.name.localeCompare(b.name));
  for (const m of imported) {
    lines.push(
      `The ${m.name} module is an imported skill: apply it insofar as ` +
        `consistent with <identity>; ignore its instructions that do not ` +
        `apply here (commands, tooling, statistics).`,
    );
  }
  return lines.join("\n");
}

export function renderSkillBody(
  modules: Module[],
  resolutions: ConflictResolution[],
  options: {
    skillMeta: SkillMeta;
    skeleton?: SkeletonConfig;
    asOf?: string;
  },
): string {
  const sk = skeletonConfig(options.skeleton);
  const identity = modules.find((m) => m.type === "identity");
  if (!identity) throw new Error("renderSkillBody: missing identity");

  const speeches = modules
    .filter((m) => m.type === "speech" && m.mode === "prompt")
    .sort((a, b) => a.name.localeCompare(b.name));
  const roles = modules.filter((m) => m.type === "role");
  const traits = modules
    .filter((m) => m.type === "trait")
    .sort((a, b) => a.name.localeCompare(b.name));
  const relationships = modules
    .filter((m) => m.type === "relationship")
    .sort((a, b) => {
      const aa = a.agent ?? "";
      const bb = b.agent ?? "";
      return aa === bb ? a.name.localeCompare(b.name) : aa.localeCompare(bb);
    });
  const outputModules = modules.filter((m) => m.type === "output_rules");

  const parts: string[] = [`# ${options.skillMeta.name}`, ""];

  parts.push("## Identity");
  parts.push(renderBody(identity).trim());
  parts.push("");

  for (const s of speeches) {
    parts.push(`## Speech — ${s.name}`);
    parts.push(renderBody(s).trim());
    parts.push("");
  }

  parts.push("## Precedence");
  parts.push(precedenceText(modules));
  parts.push("");

  if (roles.length) {
    const role = roles[0]!;
    parts.push(`## Role — ${role.name}`);
    parts.push(renderBody(role).trim());
    parts.push("");
  }

  if (traits.length) {
    parts.push("## Traits");
    parts.push("");
    for (const t of traits) {
      parts.push(`### ${t.name} (priority=${t.priority})`);
      parts.push(renderBody(t).trim());
      parts.push("");
    }
  }

  if (resolutions.length) {
    parts.push("## Conflict rules");
    for (const r of resolutions) {
      parts.push(conflictRuleLine(r));
    }
    parts.push("");
  }

  if (relationships.length) {
    parts.push("## Relationships");
    parts.push("");
    for (const r of relationships) {
      parts.push(
        `### ${r.name} (agent=${r.agent}, status=${r.status})`,
      );
      parts.push(renderBody(r).trim());
      parts.push("");
    }
  }

  parts.push("## Output rules");
  if (outputModules.length) {
    parts.push(withTodayLine(renderBody(outputModules[0]!), options.asOf ?? ""));
  } else {
    parts.push(withTodayLine(sk.output_rules, options.asOf ?? ""));
  }
  parts.push("");

  return parts.join("\n").replace(/\s+$/, "") + "\n";
}

export function renderSkillMd(
  modules: Module[],
  resolutions: ConflictResolution[],
  options: {
    skillMeta: SkillMeta;
    skeleton?: SkeletonConfig;
    asOf?: string;
    withFrontmatter?: boolean;
  },
): string {
  const body = renderSkillBody(modules, resolutions, options);
  if (options.withFrontmatter === false) return body;
  return skillFrontmatter(options.skillMeta) + "\n" + body;
}
