/** Factorial (2^k) trait ablation helper. */

import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { compose, type CompositionResult } from "./compose.js";
import { CompositionError, ValidationError } from "./errors.js";
import type { Module, SkeletonConfig } from "./models.js";
import { parseModule } from "./parse.js";

export const DEFAULT_MAX_TRAITS = 12;

export interface FactorialCell {
  traitsOn: string[];
  traitPaths: string[];
  label: string;
  result: CompositionResult | null;
  error: string | null;
}

export interface FactorialResult {
  cells: FactorialCell[];
  timestamp: string;
  traitNames: string[];
}

function asModule(
  item: string | Module,
  moduleRoot?: string,
): Module {
  if (typeof item !== "string") return item;
  return parseModule(item, { moduleRoot });
}

export function cellLabel(traitNames: string[]): string {
  if (!traitNames.length) return "none";
  return traitNames.join("+");
}

export function sanitizeLabel(label: string): string {
  const cleaned = label.replace(/[^A-Za-z0-9._+-]+/g, "_").replace(/^[._]+|[._]+$/g, "");
  return cleaned || "cell";
}

function combinations<T>(items: T[], r: number): T[][] {
  if (r === 0) return [[]];
  if (r > items.length) return [];
  const out: T[][] = [];
  const go = (start: number, acc: T[]) => {
    if (acc.length === r) {
      out.push([...acc]);
      return;
    }
    for (let i = start; i < items.length; i++) {
      acc.push(items[i]!);
      go(i + 1, acc);
      acc.pop();
    }
  };
  go(0, []);
  return out;
}

function subsetsByPopcount<T extends { name: string }>(
  named: T[],
): T[][] {
  const ordered: T[][] = [];
  for (let r = 0; r <= named.length; r++) {
    const combos = combinations(named, r);
    combos.sort((a, b) => {
      const aa = a.map((x) => x.name).join("\0");
      const bb = b.map((x) => x.name).join("\0");
      return aa < bb ? -1 : aa > bb ? 1 : 0;
    });
    ordered.push(...combos);
  }
  return ordered;
}

export interface FactorialComposeOptions {
  baseline?: Array<string | Module>;
  moduleRoot?: string;
  libraryRoot?: string;
  skeleton?: SkeletonConfig;
  timestamp?: string;
  maxTraits?: number;
}

export function factorialCompose(
  identity: string | Module,
  traits: Array<string | Module>,
  options: FactorialComposeOptions = {},
): FactorialResult {
  const maxTraits = options.maxTraits ?? DEFAULT_MAX_TRAITS;
  if (!traits.length) {
    throw new ValidationError("factorial requires at least one trait module");
  }
  if (traits.length > maxTraits) {
    throw new ValidationError(
      `too many traits for factorial: ${traits.length} > max_traits=${maxTraits}`,
    );
  }

  const ts = options.timestamp ?? new Date().toISOString();
  const identityMod = asModule(identity, options.moduleRoot);
  if (identityMod.type !== "identity") {
    throw new ValidationError(
      `identity must be type=identity, got ${identityMod.type}`,
    );
  }

  type Named = { name: string; item: string | Module; path: string };
  const named: Named[] = [];
  const seen = new Set<string>();
  for (const item of traits) {
    const mod = asModule(item, options.moduleRoot);
    if (mod.type !== "trait") {
      throw new ValidationError(
        `factorial traits must be type=trait, got ${mod.type} (${mod.name})`,
      );
    }
    if (seen.has(mod.name)) {
      throw new ValidationError(
        `duplicate trait name in factorial list: ${mod.name}`,
      );
    }
    seen.add(mod.name);
    named.push({
      name: mod.name,
      item,
      path: typeof item === "string" ? item : mod.path,
    });
  }
  named.sort((a, b) => a.name.localeCompare(b.name));
  const traitNames = named.map((n) => n.name);
  const baseline = options.baseline ?? [];

  const cells: FactorialCell[] = [];
  for (const subset of subsetsByPopcount(named)) {
    const names = subset.map((s) => s.name);
    const paths = subset.map((s) => s.path);
    const label = cellLabel(names);
    const extras = [...baseline, ...subset.map((s) => s.item)];
    try {
      const result = compose(identity, extras, {
        skeleton: options.skeleton,
        moduleRoot: options.moduleRoot,
        libraryRoot: options.libraryRoot ?? options.moduleRoot,
        timestamp: ts,
      });
      cells.push({
        traitsOn: names,
        traitPaths: paths,
        label,
        result,
        error: null,
      });
    } catch (exc) {
      if (exc instanceof CompositionError) {
        cells.push({
          traitsOn: names,
          traitPaths: paths,
          label,
          result: null,
          error: exc.message,
        });
      } else {
        throw exc;
      }
    }
  }

  return { cells, timestamp: ts, traitNames };
}

export function writeFactorial(
  result: FactorialResult,
  outDir: string,
  options: { writePrompts?: boolean } = {},
): string {
  const writePrompts = options.writePrompts !== false;
  const manifestsDir = path.join(outDir, "manifests");
  const promptsDir = path.join(outDir, "prompts");
  mkdirSync(manifestsDir, { recursive: true });
  if (writePrompts) mkdirSync(promptsDir, { recursive: true });

  const indexCells: Record<string, unknown>[] = [];
  const used = new Set<string>();

  for (const cell of result.cells) {
    const base = sanitizeLabel(cell.label);
    let fileStem = base;
    let n = 2;
    while (used.has(fileStem)) {
      fileStem = `${base}_${n}`;
      n += 1;
    }
    used.add(fileStem);

    let manifestRel: string | null = null;
    let promptRel: string | null = null;

    if (cell.result) {
      const manifestPath = path.join(manifestsDir, `${fileStem}.json`);
      writeFileSync(manifestPath, cell.result.manifestJson(), "utf-8");
      manifestRel = `manifests/${fileStem}.json`;
      if (writePrompts) {
        const promptPath = path.join(promptsDir, `${fileStem}.xml`);
        writeFileSync(promptPath, cell.result.promptXml, "utf-8");
        promptRel = `prompts/${fileStem}.xml`;
      }
    }

    indexCells.push({
      label: cell.label,
      traits_on: cell.traitsOn,
      manifest: manifestRel,
      prompt: promptRel,
      error: cell.error,
    });
  }

  const indexPath = path.join(outDir, "index.json");
  writeFileSync(
    indexPath,
    JSON.stringify(
      {
        timestamp: result.timestamp,
        trait_names: result.traitNames,
        cells: indexCells,
      },
      null,
      2,
    ) + "\n",
    "utf-8",
  );
  return indexPath;
}
