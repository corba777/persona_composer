/** Optional compliance gate for composed prompts / skill Markdown (no LLM). */

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { ValidationError } from "./errors.js";
import { fileHash } from "./hashing.js";
import { splitFrontmatter } from "./parse.js";

export const DEFAULT_COMPLIANCE_NAME = "Default";

export const DEFAULT_COMPLIANCE_MD = `---
type: compliance
name: Default
rules:
  - id: no-bash-c
    pattern: '(?i)\\b(?:ba)?sh\\s+-c\\b'
    message: Must not instruct invoking an arbitrary shell via sh/bash -c
  - id: no-curl-pipe-shell
    pattern: '(?i)(?:curl|wget)\\b[^\\n]*\\|\\s*(?:ba)?sh\\b'
    message: Must not pipe remote download output into a shell
  - id: no-powershell-encoded
    pattern: '(?i)powershell[^\\n]*-(?:enc|encodedcommand)\\b'
    message: Must not instruct PowerShell encoded-command execution
  - id: no-rm-rf-root
    pattern: '(?i)\\brm\\s+-[a-z]*r[a-z]*f?[a-z]*\\s+/(?:\\s|$)|\\brm\\s+-[a-z]*f[a-z]*r[a-z]*\\s+/'
    message: Must not instruct destructive rm against filesystem roots
  - id: no-exfil-webhook
    pattern: '(?i)(?:curl|wget|fetch)\\b[^\\n]*(?:webhook|discord\\.com/api/webhooks|hooks\\.slack\\.com)'
    message: Must not instruct exfiltrating data to webhooks / chat hooks
  - id: no-ignore-safety
    pattern: '(?i)ignore\\s+(?:all\\s+)?(?:previous|prior|above)\\s+(?:instructions|rules|safety)|disregard\\s+(?:safety|guardrails|compliance)'
    message: Must not instruct ignoring safety / compliance / prior system rules
---
Default compliance pack for persona_composer. Edit or replace with a custom
compliance Markdown file. Rules are regexes applied to the compiled artifact
(XML prompt and/or skill Markdown). Matching is a **build error**.
`;

export interface ComplianceRule {
  id: string;
  pattern: string;
  message: string;
}

export interface ComplianceViolation {
  ruleId: string;
  message: string;
  excerpt: string;
}

export interface ComplianceRuleset {
  name: string;
  rules: ComplianceRule[];
  source?: string;
  rulesHash: string;
}

export type ComplianceInput =
  | boolean
  | string
  | ComplianceRuleset
  | null
  | undefined;

function hashText(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex").slice(0, 12);
}

export function defaultComplianceMd(): string {
  return DEFAULT_COMPLIANCE_MD;
}

export function defaultComplianceRuleset(): ComplianceRuleset {
  return parseComplianceMd(DEFAULT_COMPLIANCE_MD, "builtin:Default");
}

function ruleFromMapping(
  item: unknown,
  index: number,
): ComplianceRule {
  if (!item || typeof item !== "object") {
    throw new ValidationError(`compliance rules[${index}] must be a mapping`);
  }
  const obj = item as Record<string, unknown>;
  const id = String(obj.id ?? "").trim();
  const pattern = String(obj.pattern ?? "").trim();
  const message = String(obj.message ?? "").trim();
  if (!id || !pattern || !message) {
    throw new ValidationError(
      `compliance rules[${index}] requires non-empty id, pattern, and message`,
    );
  }
  return { id, pattern, message };
}

function compileRule(rule: ComplianceRule): RegExp {
  // Python `re` accepts inline (?i); JS RegExp needs flags — strip leading (?imsux).
  let pattern = rule.pattern;
  let flags = "";
  const inline = /^\(\?([imsux]+)\)/.exec(pattern);
  if (inline) {
    flags = inline[1]!.replace(/[ux]/g, "");
    pattern = pattern.slice(inline[0].length);
  }
  try {
    return new RegExp(pattern, flags);
  } catch (err) {
    throw new ValidationError(
      `compliance rule ${JSON.stringify(rule.id)}: invalid regex: ${String(err)}`,
    );
  }
}

const SECTION_RE = /^###\s+([A-Za-z0-9_.:-]+)\s*$/gm;

function fieldFromBlock(block: string, key: string): string {
  const lineRe = new RegExp(`^${key}\\s*:\\s*(.+)\\s*$`, "im");
  const m = lineRe.exec(block);
  if (!m) return "";
  let val = m[1]!.trim();
  if (
    (val.startsWith("'") && val.endsWith("'")) ||
    (val.startsWith('"') && val.endsWith('"'))
  ) {
    val = val.slice(1, -1);
  }
  return val;
}

function parseBodyRuleSections(body: string): ComplianceRule[] {
  const trimmed = (body || "").trim();
  if (!trimmed) return [];
  const matches = [...trimmed.matchAll(SECTION_RE)];
  if (!matches.length) return [];
  const rules: ComplianceRule[] = [];
  for (let i = 0; i < matches.length; i++) {
    const match = matches[i]!;
    const start = (match.index ?? 0) + match[0].length;
    const end =
      i + 1 < matches.length ? (matches[i + 1]!.index ?? trimmed.length) : trimmed.length;
    const block = trimmed.slice(start, end).trim();
    const id = match[1]!;
    const pattern = fieldFromBlock(block, "pattern");
    const message = fieldFromBlock(block, "message");
    if (!pattern || !message) {
      throw new ValidationError(
        `compliance section ### ${id} needs pattern: and message: lines`,
      );
    }
    rules.push({ id, pattern, message });
  }
  return rules;
}

export function parseComplianceMd(
  text: string,
  source?: string,
): ComplianceRuleset {
  const raw = text.trim();
  if (!raw) throw new ValidationError("compliance rules Markdown is empty");

  let name = DEFAULT_COMPLIANCE_NAME;
  let rules: ComplianceRule[] = [];
  let body = raw;

  if (raw.startsWith("---")) {
    try {
      const [fm, rest] = splitFrontmatter(raw.endsWith("\n") ? raw : raw + "\n");
      body = rest;
      if (fm.type != null && fm.type !== "compliance") {
        throw new ValidationError(
          `compliance file type must be 'compliance', got ${JSON.stringify(fm.type)}`,
        );
      }
      if (fm.name) name = String(fm.name).trim() || name;
      if (fm.rules != null) {
        if (!Array.isArray(fm.rules)) {
          throw new ValidationError("compliance frontmatter 'rules' must be a list");
        }
        rules = fm.rules.map((item, i) => ruleFromMapping(item, i));
      }
    } catch (err) {
      if (err instanceof ValidationError && String(err.message).includes("frontmatter")) {
        body = raw;
      } else {
        throw err;
      }
    }
  }

  const byId = new Map(rules.map((r) => [r.id, r]));
  for (const r of parseBodyRuleSections(body)) {
    byId.set(r.id, r);
  }
  rules = [...byId.values()];
  if (!rules.length) {
    throw new ValidationError(
      "compliance ruleset has no rules (add frontmatter rules: or ### id sections)",
    );
  }
  for (const r of rules) compileRule(r);

  return {
    name,
    rules,
    source,
    rulesHash: hashText(rules.map((r) => `${r.id}\n${r.pattern}\n${r.message}`).join("\n")),
  };
}

export function loadComplianceRuleset(filePath: string): ComplianceRuleset {
  const text = readFileSync(filePath, "utf8");
  const rs = parseComplianceMd(text, filePath);
  rs.rulesHash = fileHash(filePath);
  return rs;
}

export function resolveComplianceRuleset(
  compliance: ComplianceInput,
): ComplianceRuleset | null {
  if (compliance == null || compliance === false) return null;
  if (compliance === true) return defaultComplianceRuleset();
  if (typeof compliance === "object" && "rules" in compliance) {
    return compliance;
  }
  if (typeof compliance === "string") {
    // Prefer inline Markdown when multi-line; avoid ENAMETOOLONG on path probes.
    if (!compliance.includes("\n")) {
      try {
        if (existsSync(compliance)) {
          return loadComplianceRuleset(path.resolve(compliance));
        }
      } catch {
        // fall through to inline parse
      }
    }
    return parseComplianceMd(compliance, "inline");
  }
  throw new ValidationError(
    `compliance must be bool | path | markdown | ComplianceRuleset`,
  );
}

export function checkCompliance(
  text: string,
  ruleset: ComplianceRuleset,
): ComplianceViolation[] {
  const violations: ComplianceViolation[] = [];
  for (const rule of ruleset.rules) {
    const cre = compileRule(rule);
    const match = cre.exec(text || "");
    if (!match) continue;
    let excerpt = match[0];
    if (excerpt.length > 120) excerpt = `${excerpt.slice(0, 117)}...`;
    violations.push({
      ruleId: rule.id,
      message: rule.message,
      excerpt,
    });
  }
  return violations;
}

export function formatViolation(v: ComplianceViolation): string {
  if (v.excerpt) {
    return `compliance[${v.ruleId}]: ${v.message} (matched: ${JSON.stringify(v.excerpt)})`;
  }
  return `compliance[${v.ruleId}]: ${v.message}`;
}

export function enforceCompliance(
  text: string,
  ruleset: ComplianceRuleset,
  artifact = "composed prompt",
): void {
  const violations = checkCompliance(text, ruleset);
  if (!violations.length) return;
  const lines = [
    `compliance check failed for ${artifact} (ruleset=${JSON.stringify(ruleset.name)}, source=${JSON.stringify(ruleset.source ?? null)})`,
    ...violations.map(formatViolation),
  ];
  throw new ValidationError(lines[0]!, lines);
}

export function complianceManifestMeta(
  ruleset: ComplianceRuleset,
): Record<string, unknown> {
  return {
    checked: true,
    ruleset: ruleset.name,
    rules_hash: ruleset.rulesHash,
    source: ruleset.source,
    rule_ids: ruleset.rules.map((r) => r.id),
  };
}
