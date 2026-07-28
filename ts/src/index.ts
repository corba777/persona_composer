/** Persona Composer — modular Markdown → XML system prompt compiler (TypeScript). */

export { compose, composeFromManifest } from "./compose.js";
export type { CompositionResult, ComposeOptions } from "./compose.js";
export {
  buildDecomposePrompt,
  decompose,
  parseDecompositionResponse,
  writeDraftModules,
} from "./decompose.js";
export type { DecompositionResult, ModuleSuggestion } from "./decompose.js";
export { CompositionError, ValidationError } from "./errors.js";
export {
  checkCompliance,
  complianceManifestMeta,
  defaultComplianceMd,
  defaultComplianceRuleset,
  enforceCompliance,
  loadComplianceRuleset,
  parseComplianceMd,
  resolveComplianceRuleset,
} from "./compliance.js";
export type {
  ComplianceInput,
  ComplianceRule,
  ComplianceRuleset,
  ComplianceViolation,
} from "./compliance.js";
export {
  cellLabel,
  factorialCompose,
  sanitizeLabel,
  writeFactorial,
  DEFAULT_MAX_TRAITS,
} from "./factorial.js";
export type {
  FactorialCell,
  FactorialComposeOptions,
  FactorialResult,
} from "./factorial.js";
export {
  DEFAULT_OUTPUT_RULES,
  SKELETON_VERSION,
  skeletonConfig,
  todayLine,
  withTodayLine,
} from "./models.js";
export type {
  Manifest,
  Module,
  ModuleType,
  SkeletonConfig,
} from "./models.js";
export { parseModule, parseModules, splitFrontmatter } from "./parse.js";
export { DEFAULT_REGISTRY, TypeRegistry } from "./registry.js";
export { renderPrompt } from "./render.js";
export { renderSkillBody, renderSkillMd } from "./render_skill.js";
export {
  applyRewriters,
  applyRewritersFromManifest,
  applyRewritersFromPaths,
} from "./rewriter.js";
export type { RewriteResult } from "./rewriter.js";
export {
  composeSkill,
  contentForTarget,
  writeSkillTargets,
} from "./skill_export.js";
export type { SkillExportResult } from "./skill_export.js";
export {
  loadSkillSettings,
  skillSettingsAdhoc,
  skillSettingsFromDict,
} from "./skill_settings.js";
export type {
  SkillMeta,
  SkillSettings,
  SkillTarget,
  TargetKind,
} from "./skill_settings.js";
