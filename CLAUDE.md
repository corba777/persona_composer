# CLAUDE.md — Persona Composer

## What this project is

A small, framework-agnostic **prompt compiler**: it assembles an agent's system prompt (XML skeleton) from modular Markdown files (identity, roles, traits, speech styles, relationships). Markdown modules are the *source*, the composed XML prompt is the *build artifact*, and the composer is the *compiler* in between.

The tool exists to make agent character **composable and intervenable**: traits toggle as files, so `do(trait=∅)` is a config-line change, conflict resolution is generated explicitly, and every composition is logged as an experiment manifest. A first-class goal is **reuse of the existing md ecosystem**: community skill files (Claude Code skills etc.) drop in as vendored modules — used verbatim under an identity-supremacy clause, or distilled into clean modules.

Primary consumers (all internal projects of the author):
- **Amber Blade** — Zelda-like multi-agent game (social dynamics testbed)
- **DS-process simulator** — LLM agents as team members (stakeholder, DE, DS, MLOps...)
- **wololo** and future MAS experiments

Not a goal: becoming a general-purpose framework, a public plugin marketplace, or adoption metrics. This is a personal instrument extracted from real experiments. Thin in-process plugins (new module types via a registry) are welcome when they stay simple.

## Core design decisions (do not silently change these)

1. **`identity` is MANDATORY; everything else is optional.**
   The identity module *is* the system prompt in the degenerate case — it may contain everything (role, character, speech) as one monolithic text. All other module types (`role`, `trait`, `speech`, `relationship`, `output_rules`) are optional refinements. This gives a **decomposition path**: a project starts with one big `identity.md`, then gradually extracts sub-modules out of it without breaking anything. Composing `identity` alone must always produce a valid prompt.

2. **Type lives in frontmatter, not in the filename.**
   Filenames (`traits/territorial.md`) are a human convention only. The composer trusts `type:` in YAML frontmatter. Files must be movable/renamable without semantic change.

3. **The composer is a renderer with a schema, not a concatenator.**
   It knows a fixed skeleton (section order), places modules into slots, and **generates derived instructions that exist in no single file** — most importantly `<conflict_rule>` from the `priority`/`conflicts` metadata of active trait modules. Naive tag-wrapping + concatenation is explicitly what this tool replaces.

4. **XML is the render target; Markdown is the authoring format.**
   XML skeleton for the assembled prompt (explicit boundaries, attributes, referenceable tags — models are trained to respect them). Markdown + YAML frontmatter for module files (human-friendly authoring). Neither format does the other's job.

5. **Every composition emits a manifest; a manifest can recompose.**
   The manifest (JSON) records: active modules (paths + hashes), resolved conflict rules, skeleton version, timestamp. It is both a *receipt* (what this run used) and a *recipe* (feed it back to rebuild the same prompt). Ablating a trait = removing one line from the manifest and recomposing. No manifest, no composition.

6. **Module types are a plugin surface.**
   The core ships the built-in types (`identity`, `role`, `trait`, `speech`, `relationship`, `output_rules`), but the type system is open: a plugin registers a type name + frontmatter validator + skeleton slot (+ optional derived-instruction generator, like conflict_rule for traits). Core logic never hard-codes the type list outside the registry. Discovery of plugins/modules may be dynamic; composition never is (see Anti-goals).

7. **Foreign modules are first-class citizens (vendor + overlay, never edit upstream).**
   A core use case is reusing *existing* md files from the ecosystem (Claude Code skills, agent instruction files — e.g. JuliusBrussee/caveman). The upstream file is vendored **pristine** into `modules/vendor/<name>/`; it is never edited, so it stays diffable/updatable against upstream. A thin **overlay module** in the normal library supplies our frontmatter and chooses one of two adaptation modes:
   - `adaptation: as-is` — overlay has no body of its own; `source:` points at the vendored file, whose body is inserted verbatim. The precedence clause (see skeleton) makes it subordinate to identity and tells the model to silently ignore instructions inapplicable in context (e.g. caveman's Claude-Code commands/statusline machinery inside a game NPC).
   - `adaptation: extracted` — the overlay body contains only the distilled part we want (e.g. just the caveman speech rules), authored via the decomposition workflow; `source:` still records provenance.
   The manifest hashes **both** the overlay and the vendored source, so upstream drift is detectable.

## Module file format

```markdown
---
type: trait            # identity | role | trait | speech | relationship | output_rules
name: Territorial      # unique within its type
priority: high         # high | medium | low  (traits only)
conflicts: [Cautious]  # names of conflicting traits (traits only)
---
Free Markdown body: behavioral directives, written as short imperative
instructions in a consistent register. This body is inserted verbatim
into the corresponding XML slot.
```

Type-specific fields:
- `identity`: no extra required fields. Body may be arbitrarily large (monolith allowed).
- `role`: optional `tools:` list (informational).
- `trait`: `priority` required (used **only** to resolve conflicts, not to order `<traits>`); `conflicts` optional (empty = conflicts with nothing). A conflict is recognized **only when mutual**: A lists B **and** B lists A. One-sided declarations do not generate `<conflict_rule>`; they **always** emit a manifest warning (`incomplete conflict pair … — no <conflict_rule> generated`).
- `speech`: optional `mode: prompt | rewriter` (default `prompt`). `rewriter` marks the module as intended for an output-rewriting pipeline stage instead of prompt insertion — the composer then *excludes* it from the prompt and lists it in the manifest under `rewriter_stack`.
- `relationship`: `agent:` (target agent id) and `status:` required. Usually generated from game/sim state, not hand-authored.
- `output_rules`: no extra required fields. At most one. Body fills `<output_rules>` after an injected date line (`Today is {YYYY-MM-DD}; use it in any generated metadata.`). If no module is active, the composer may fall back to `SkeletonConfig.output_rules` for the rest of the body; the date line is **always** present (slot is never omitted).

Import/provenance fields (any type, present on overlay modules for vendored files):
- `source:` relative path to the vendored upstream file (e.g. `vendor/caveman/SKILL.md`).
- `adaptation: as-is | extracted` — `as-is` inserts the vendored body verbatim (overlay body must be empty); `extracted` uses the overlay body (distilled) and keeps `source` as provenance.
- `origin:` upstream URL (informational, goes into the manifest).

Example — caveman as a speech style, used as-is:
```markdown
---
type: speech
name: Caveman
source: vendor/caveman/SKILL.md
adaptation: as-is
origin: https://github.com/JuliusBrussee/caveman
---
```
The composer inserts the vendored body into the `<speech>`-slot and adds to `<precedence>`: *"The Caveman module is an imported skill: apply its speech style insofar as consistent with `<identity>`; ignore its instructions that do not apply here (commands, tooling, statistics)."*

## Skeleton (fixed section order)

```xml
<identity>        <!-- mandatory, exactly one -->
<speech>          <!-- 0..N; prompt-mode speech modules only (rewriter-mode excluded) -->
<precedence>      <!-- GENERATED, always present: identity governs; all other modules
                       (including speech) apply only insofar as consistent with <identity>;
                       instructions inapplicable in the current context are ignored silently.
                       Imported (vendored) modules get an explicit per-module line here.
                       Placed after <speech> so precedence covers those modules. -->
<role>            <!-- 0..1 -->
<traits>          <!-- 0..N <trait name= priority=> blocks; order is stable/deterministic, not by priority -->
<conflict_rule>   <!-- GENERATED by composer from mutual trait conflicts among active modules; absent if none -->
<relationships>   <!-- 0..N <relation agent= status=> blocks -->
<output_rules>    <!-- always present; date line + body from type=output_rules module,
                       else SkeletonConfig.output_rules (may be empty beyond the date) -->
```

Order is fixed so positional bias is *constant across experiments* rather than an artifact of concatenation order. Changing the skeleton = bumping `skeleton_version` in the manifest.

## Composition algorithm

```
compose(identity, modules=[], skeleton=default) →
compose_from_manifest(manifest, skeleton=default) →   # recipe path: resolve paths/hashes, then same pipeline
  1. read + parse frontmatter of all inputs
  2. VALIDATE (see below); fail loudly, never render a known-bad prompt
  3. place bodies into skeleton slots (fixed order)
  4. generate <conflict_rule> lines:
       for each mutual conflicting pair among active traits:
         higher priority governs; equal priority = validation error
  5. render XML
  6. write manifest JSON
  7. return (prompt_xml, manifest)
```

## Validation rules (build-time errors, not runtime surprises)

- No `identity` module → **error** (it is the mandatory base).
- More than one `identity` → error.
- Unknown `type` → error.
- Duplicate `name` within a type among active modules → error.
- Two **active** traits with a **mutual** conflict **and equal priority** → error ("каша"/mush prevention: the model must never be left to average a conflict).
- `conflicts` referencing a trait name that doesn't exist anywhere in the **module library** (discoverable modules on disk / in the consumer's module root) → warning (typo catcher). A name that exists in the library but is simply not in the *active* set is fine — no warning (ablation / factorial runs would be unusable otherwise). One-sided `conflicts` (A lists B, B does not list A) → no `<conflict_rule>`; **warning** in the manifest (`incomplete conflict pair … — no <conflict_rule> generated`).
- `relationship` without `agent`/`status` → error.

## Conventions

- Module bodies: short imperative behavioral directives, one consistent register across the library. No essays. The style guide exists because mixed registers measurably dilute instruction-following.
- Language: modules in English (game/sim agents operate in English; Russian-speaking agents get speech modules, not translated trait modules).
- Directory layout is conventional, not semantic. Consumers may drop modules under a project tree (e.g. `agent/general/`, `agent/<agent_id>/`) or supply them via UI upload; the composer takes an explicit module list (or a manifest), not a hard-coded path scheme:
  ```
  modules/
    identity/  roles/  traits/  speech/  relationships/  output_rules/  vendor/
  ```
  Vendor `source:` paths are relative to the consumer's module root (the directory that contains `vendor/` and the overlay library).
- Hash every module file (sha256, first 12 chars) into the manifest — experiments must be reproducible after edits.

## Implementation surface (v1)

- Languages: **Python** (`src/persona_composer`) and **TypeScript** (`ts/`) — same behavior; golden fixtures shared under `tests/fixtures/`.
- Ship both a **library API** (`compose`, `compose_from_manifest`) and a **CLI** that wraps it.

## Testing

- Golden tests: fixed module set → byte-identical XML (skeleton stability).
- Validation tests: each rule above has a failing fixture.
- Property test: composing identity alone always yields valid XML.
- **No LLM calls in unit tests.** Behavioral experiments (does the trait *hold*?) live in the consuming projects, not here — this repo tests the compiler, not the model.

## Roadmap notes (context for future sessions)

- **Decomposition workflow** ✅ (library + CLI): `decompose()` — LLM-assisted via injected `llm_call` / offline `llm_response` JSON; writes draft overlay modules for human review. Core never calls a model.
- **Rewriter pipeline runner** ✅ (library + CLI stub): `apply_rewriters*` — post-generation style pass for `speech.mode: rewriter`; empty `rewriter_stack` is a no-op (backward compatible).
- Factorial experiment helper: given a trait list, emit the 2^k manifest set for ablation studies.
- Persistence measurement harness lives in Amber Blade, not here — but manifests must carry enough info (hashes, versions) for its logs to join against.

## Anti-goals

- **Plugins yes, dynamism at composition time no.** Plugin-based extension is welcome: new module *types* (memory, goals, ...) register themselves with a validator + a skeleton slot; discovery may scan directories or entry points. But the composed prompt must remain a **pure function of the manifest**: whatever discovery finds, composition consumes an explicit, hashed module list. Reproducibility lives in the manifest, not in restricting extensibility.
- No numeric behavior knobs (`swearing: +0.6`) — untestable pseudo-precision. Traits are discrete (on/off) with ordinal priority; that's what makes interventions executable and measurable.
- No agent self-modification of the active module set in v1 (endogenous trait switching destroys intervention cleanliness; it becomes a *studied object* later, not a background mechanic).
- The composer never calls an LLM.
