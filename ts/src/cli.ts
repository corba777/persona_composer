#!/usr/bin/env node
/** CLI for persona-compose (TypeScript). */

import { writeFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { compose, composeFromManifest } from "./compose.js";
import { CompositionError } from "./errors.js";
import { factorialCompose, writeFactorial } from "./factorial.js";
import type { SkeletonConfig } from "./models.js";
import { composeSkill, writeSkillTargets } from "./skill_export.js";
import {
  loadSkillSettings,
  skillSettingsAdhoc,
} from "./skill_settings.js";

function usage(): never {
  console.error(`Usage:
  persona-compose compose --identity <path> [--module-root <dir>] [--out <file>] [--manifest <file>] [--output-rules <text>] [--compliance] [--compliance-file <md>] [modules...]
  persona-compose recompose <manifest.json> [--module-root <dir>] [--out <file>] [--manifest <file>] [--no-verify-hashes] [--output-rules <text>] [--compliance] [--compliance-file <md>]
  persona-compose skill --settings <persona.settings.json> [--manifest <file>] [--stdout] [--compliance] [--compliance-file <md>]
  persona-compose skill --identity <path> [--module-root <dir>] [--name <n>] [--description <d>] --out <SKILL.md> [--manifest <file>] [--compliance] [--compliance-file <md>] [modules...]
  persona-compose factorial --identity <path> --traits <t.md...> [--baseline <m.md...>] --out-dir <dir> [--module-root <dir>] [--no-prompts] [--max-traits <n>]`);
  process.exit(2);
}

function takeFlag(args: string[], name: string): string | undefined {
  const ix = args.indexOf(name);
  if (ix === -1) return undefined;
  const val = args[ix + 1];
  if (!val || val.startsWith("-")) usage();
  args.splice(ix, 2);
  return val;
}

function hasFlag(args: string[], name: string): boolean {
  const ix = args.indexOf(name);
  if (ix === -1) return false;
  args.splice(ix, 1);
  return true;
}

/** `--compliance-file` wins; else `--compliance` → builtin Default; else off. */
function takeCompliance(args: string[]): boolean | string | undefined {
  const file = takeFlag(args, "--compliance-file");
  if (file) return file;
  if (hasFlag(args, "--compliance")) return true;
  return undefined;
}

/** Collect remaining values after a multi-value flag until next --flag. */
function takeMultiFlag(args: string[], name: string): string[] | undefined {
  const ix = args.indexOf(name);
  if (ix === -1) return undefined;
  args.splice(ix, 1);
  const values: string[] = [];
  while (args.length && !args[0]!.startsWith("-")) {
    values.push(args.shift()!);
  }
  return values;
}

export function main(argv: string[] = process.argv.slice(2)): number {
  if (!argv.length) usage();
  const args = [...argv];
  const command = args.shift();

  try {
    if (command === "skill") {
      return runSkill(args);
    }
    if (command === "factorial") {
      return runFactorial(args);
    }

    const outPath = takeFlag(args, "--out");
    const manifestOut = takeFlag(args, "--manifest");
    const moduleRoot = takeFlag(args, "--module-root");
    const outputRules = takeFlag(args, "--output-rules");
    const compliance = takeCompliance(args);
    const skeleton: SkeletonConfig | undefined = outputRules
      ? { output_rules: outputRules }
      : undefined;

    let result;
    if (command === "compose") {
      const identity = takeFlag(args, "--identity");
      if (!identity) {
        console.error("error: --identity is required");
        return 1;
      }
      result = compose(identity, args, {
        skeleton,
        moduleRoot,
        libraryRoot: moduleRoot,
        compliance,
      });
    } else if (command === "recompose") {
      const noVerify = hasFlag(args, "--no-verify-hashes");
      const manifestIn = args.shift();
      if (!manifestIn) usage();
      result = composeFromManifest(path.resolve(manifestIn), {
        skeleton,
        moduleRoot,
        libraryRoot: moduleRoot,
        verifyHashes: !noVerify,
        compliance,
      });
    } else {
      usage();
    }

    if (outPath) writeFileSync(outPath, result.promptXml, "utf-8");
    else process.stdout.write(result.promptXml);

    if (manifestOut) {
      writeFileSync(manifestOut, result.manifestJson(), "utf-8");
    }
    for (const w of result.manifest.warnings) {
      console.error(`warning: ${w}`);
    }
    return 0;
  } catch (exc) {
    if (exc instanceof CompositionError) {
      console.error(`error: ${exc.message}`);
      return 1;
    }
    throw exc;
  }
}

function runSkill(args: string[]): number {
  const settingsPath = takeFlag(args, "--settings");
  const outPath = takeFlag(args, "--out");
  const manifestOut = takeFlag(args, "--manifest");
  const moduleRoot = takeFlag(args, "--module-root");
  const name = takeFlag(args, "--name") ?? "persona";
  const description =
    takeFlag(args, "--description") ?? "Composed coding persona.";
  const outputRules = takeFlag(args, "--output-rules");
  const toStdout = hasFlag(args, "--stdout");
  const compliance = takeCompliance(args);
  const skeleton: SkeletonConfig | undefined = outputRules
    ? { output_rules: outputRules }
    : undefined;

  const identity = takeFlag(args, "--identity");
  const modules = args.filter((a) => !a.startsWith("-"));

  const settings = settingsPath
    ? loadSkillSettings(settingsPath)
    : (() => {
        if (!identity) {
          console.error("error: skill requires --settings or --identity");
          process.exit(1);
        }
        return skillSettingsAdhoc({
          identity,
          modules,
          moduleRoot,
          name,
          description,
          out: outPath,
        });
      })();

  const result = composeSkill(settings, { skeleton, compliance });
  const written = writeSkillTargets(result, settings, {
    manifestPath: manifestOut,
  });

  if (toStdout || !settings.targets.length) {
    process.stdout.write(result.skillMd);
    if (!result.skillMd.endsWith("\n")) process.stdout.write("\n");
  }

  for (const p of written) {
    console.error(`wrote ${p}`);
  }
  for (const w of result.manifest.warnings) {
    console.error(`warning: ${w}`);
  }
  return 0;
}

function runFactorial(args: string[]): number {
  const identity = takeFlag(args, "--identity");
  const traits = takeMultiFlag(args, "--traits");
  const baseline = takeMultiFlag(args, "--baseline") ?? [];
  const moduleRoot = takeFlag(args, "--module-root");
  const outDir = takeFlag(args, "--out-dir");
  const noPrompts = hasFlag(args, "--no-prompts");
  const outputRules = takeFlag(args, "--output-rules");
  const maxTraitsRaw = takeFlag(args, "--max-traits");
  const skeleton: SkeletonConfig | undefined = outputRules
    ? { output_rules: outputRules }
    : undefined;

  if (!identity || !traits?.length || !outDir) {
    console.error(
      "error: factorial requires --identity, --traits, and --out-dir",
    );
    return 1;
  }

  const opts: Parameters<typeof factorialCompose>[2] = {
    baseline,
    moduleRoot,
    libraryRoot: moduleRoot,
    skeleton,
  };
  if (maxTraitsRaw != null) {
    opts.maxTraits = Number(maxTraitsRaw);
  }

  const result = factorialCompose(identity, traits, opts);
  const indexPath = writeFactorial(result, outDir, {
    writePrompts: !noPrompts,
  });
  console.error(`wrote ${indexPath}`);
  console.error(`cells: ${result.cells.length}`);
  for (const cell of result.cells) {
    if (cell.error) {
      console.error(`error: [${cell.label}] ${cell.error}`);
    }
  }
  return 0;
}

const isDirectRun =
  process.argv[1] != null &&
  fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);

if (isDirectRun) {
  process.exit(main());
}
