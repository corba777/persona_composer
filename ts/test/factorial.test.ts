/** Factorial ablation helper tests. */

import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { ValidationError } from "../src/errors.js";
import {
  factorialCompose,
  sanitizeLabel,
  writeFactorial,
} from "../src/factorial.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MODULES = path.resolve(HERE, "../../tests/fixtures/modules");
const FIXED_TS = "2026-07-20T15:00:00+00:00";

describe("factorial", () => {
  it("emits 4 cells for 2 traits in deterministic order", () => {
    const result = factorialCompose(
      path.join(MODULES, "identity/guard.md"),
      [
        path.join(MODULES, "traits/territorial.md"),
        path.join(MODULES, "traits/cautious.md"),
      ],
      {
        baseline: [path.join(MODULES, "speech/curt.md")],
        moduleRoot: MODULES,
        libraryRoot: MODULES,
        timestamp: FIXED_TS,
      },
    );
    expect(result.cells).toHaveLength(4);
    expect(result.traitNames).toEqual(["Cautious", "Territorial"]);
    expect(result.cells.map((c) => c.label)).toEqual([
      "none",
      "Cautious",
      "Territorial",
      "Cautious+Territorial",
    ]);
    expect(result.cells.every((c) => c.error == null)).toBe(true);
    for (const cell of result.cells) {
      expect(cell.result).not.toBeNull();
      expect(cell.result!.manifest.timestamp).toBe(FIXED_TS);
      const names = new Set(cell.result!.manifest.modules.map((m) => m.name));
      expect(names.has("Curt")).toBe(true);
      expect(names.has("Guard")).toBe(true);
      for (const t of cell.traitsOn) {
        expect(names.has(t)).toBe(true);
      }
    }
  });

  it("records per-cell error for equal-priority mutual conflict", () => {
    const dir = mkdtempSync(path.join(os.tmpdir(), "persona-fact-"));
    const result = factorialCompose(
      path.join(MODULES, "identity/guard.md"),
      [
        path.join(MODULES, "traits/stubborn.md"),
        path.join(MODULES, "traits/flexible.md"),
      ],
      {
        moduleRoot: MODULES,
        libraryRoot: MODULES,
        timestamp: FIXED_TS,
      },
    );
    expect(result.cells).toHaveLength(4);
    const byLabel = Object.fromEntries(result.cells.map((c) => [c.label, c]));
    expect(byLabel["none"]!.error).toBeNull();
    expect(byLabel["Stubborn"]!.error).toBeNull();
    expect(byLabel["Flexible"]!.error).toBeNull();
    expect(byLabel["Flexible+Stubborn"]!.error).toBeTruthy();
    expect(byLabel["Flexible+Stubborn"]!.result).toBeNull();

    const indexPath = writeFactorial(result, dir, { writePrompts: true });
    const data = JSON.parse(readFileSync(indexPath, "utf-8"));
    expect(data.trait_names).toEqual(["Flexible", "Stubborn"]);
    expect(data.cells).toHaveLength(4);
    const failed = data.cells.find(
      (c: { label: string }) => c.label === "Flexible+Stubborn",
    );
    expect(failed.error).toBeTruthy();
    expect(failed.manifest).toBeNull();
    const ok = data.cells.find((c: { label: string }) => c.label === "none");
    expect(ok.manifest).toBe("manifests/none.json");
    expect(ok.prompt).toBe("prompts/none.xml");
  });

  it("respects maxTraits", () => {
    const dir = mkdtempSync(path.join(os.tmpdir(), "persona-traits-"));
    const paths: string[] = [];
    for (let i = 0; i < 3; i++) {
      const p = path.join(dir, `t${i}.md`);
      writeFileSync(
        p,
        `---\ntype: trait\nname: T${i}\npriority: low\n---\nBody ${i}.\n`,
        "utf-8",
      );
      paths.push(p);
    }
    expect(() =>
      factorialCompose(path.join(MODULES, "identity/guard.md"), paths, {
        moduleRoot: MODULES,
        maxTraits: 2,
      }),
    ).toThrow(ValidationError);
  });

  it("sanitizes labels", () => {
    expect(sanitizeLabel("none")).toBe("none");
    expect(sanitizeLabel("Cautious+Territorial")).toBe("Cautious+Territorial");
  });
});
