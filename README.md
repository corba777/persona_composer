# Persona Composer

A small, framework-agnostic **prompt compiler**: assemble an agent’s system prompt (XML) from modular Markdown files — identity, roles, traits, speech, relationships, output rules.

Markdown modules are the *source*. The composed XML prompt is the *build artifact*. The composer is the *compiler* in between.

**Why it exists:** character becomes composable and intervenable. Toggle a trait by adding/removing a file; conflict resolution is generated explicitly; every run emits a JSON **manifest** (receipt + recipe for recomposition). Community skill files can be vendored pristine and wired via thin overlays.

Implementations (same behavior, shared fixtures):

| Language | Path | Package |
|----------|------|---------|
| Python ≥ 3.10 | `src/persona_composer/` | `persona-composer` |
| TypeScript (Node ≥ 18) | `ts/` | `persona-composer` |

Design notes and invariants live in [`CLAUDE.md`](./CLAUDE.md).

---

## Quick start

### Python

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

persona-compose compose \
  --identity tests/fixtures/modules/identity/guard.md \
  --module-root tests/fixtures/modules \
  tests/fixtures/modules/traits/territorial.md \
  tests/fixtures/modules/traits/cautious.md \
  --manifest /tmp/manifest.json
```

### TypeScript

```bash
cd ts
npm install
npm run build

node dist/cli.js compose \
  --identity ../tests/fixtures/modules/identity/guard.md \
  --module-root ../tests/fixtures/modules \
  ../tests/fixtures/modules/traits/territorial.md \
  ../tests/fixtures/modules/traits/cautious.md \
  --manifest /tmp/manifest.json
```

---

## Module format

Each module is Markdown with YAML frontmatter. **Type is in frontmatter**, not the filename.

```markdown
---
type: trait            # identity | role | trait | speech | relationship | output_rules
name: Territorial      # unique within its type
priority: high         # high | medium | low  (traits only)
conflicts: [Cautious]  # mutual conflicts only generate <conflict_rule>
---
Treat unfamiliar presence near the gate as intrusion until proven otherwise.
```

| Type | Required | Notes |
|------|----------|--------|
| `identity` | **yes** (exactly one) | May be a full monolith; composing identity alone is valid |
| `role` | no (0..1) | Optional `tools:` list |
| `trait` | no (0..N) | `priority` required; conflicts must be **mutual** (one-sided → manifest warning, no rule) |
| `speech` | no (0..N) | `mode: prompt` (default) or `rewriter` (excluded from prompt, listed in manifest) |
| `relationship` | no (0..N) | Requires `agent` + `status` |
| `output_rules` | no (0..1) | Else optional `SkeletonConfig.output_rules` body; slot **always** includes `Today is {YYYY-MM-DD}; …` |

Built-in types above are registered in `TypeRegistry` (`registry.py` / `registry.ts`). v1 does not ship a public plugin loader yet — extending the registry is the intended hook for new module types.

**Vendor overlays** (reuse upstream skills without editing them):

```markdown
---
type: speech
name: Caveman
source: vendor/caveman/SKILL.md
adaptation: as-is          # or extracted
origin: https://github.com/JuliusBrussee/caveman
---
```

`module_root` must contain the `vendor/` tree so `source:` resolves.

---

## Composed skeleton

Fixed section order (positional bias stays constant across experiments). Changing order = bump `skeleton_version`.

```xml
<identity>         <!-- mandatory, exactly one -->
<speech>           <!-- 0..N; prompt-mode only -->
<precedence>       <!-- always generated -->
<role>             <!-- 0..1 -->
<traits>           <!-- 0..N -->
<conflict_rule>    <!-- generated; absent if no mutual conflicts -->
<relationships>    <!-- 0..N -->
<output_rules>     <!-- always present; starts with Today's ISO date -->
```

Every composition returns `(prompt_xml, manifest)`. The manifest records module paths, content hashes, conflict rules, skeleton version, and warnings (including incomplete / one-sided conflict pairs). Feed it back via `compose_from_manifest` / `composeFromManifest` to rebuild or ablate.

### `<identity>` — mandatory base

The identity *is* the system prompt in the degenerate case. Composing identity alone is valid.

```markdown
---
type: identity
name: Guard
---
You are the gate guard of Amber Outpost. Protect the gate. Speak briefly.
```

```xml
<identity name="Guard">You are the gate guard of Amber Outpost. Protect the gate. Speak briefly.</identity>
```

### `<speech>` — style in the prompt

Only `mode: prompt` (default) modules land here. `mode: rewriter` is excluded from the prompt and listed in the manifest under `rewriter_stack`.

```markdown
---
type: speech
name: Curt
---
Use short sentences. No small talk.
```

```xml
<speech>
  <style name="Curt">Use short sentences. No small talk.</style>
</speech>
```

Several speech modules → several `<style>` children, sorted by name.

### `<precedence>` — always generated

Placed **after** `<speech>` so the supremacy rule covers speech and every later slot. Body is composer-generated (not authored as a module):

1. A fixed clause: identity governs; other modules apply only insofar as consistent with `<identity>`; inapplicable instructions are ignored silently.
2. One extra line per **imported** (vendored) module, so foreign skills stay subordinate.

```xml
<precedence>Identity governs. All other modules apply only insofar as consistent with &lt;identity&gt;. Instructions inapplicable in the current context are ignored silently.</precedence>
```

With a vendored overlay (e.g. Caveman `adaptation: as-is`), an extra sentence is appended:

```xml
<precedence>Identity governs. …
The Caveman module is an imported skill: apply it insofar as consistent with &lt;identity&gt;; ignore its instructions that do not apply here (commands, tooling, statistics).</precedence>
```

### `<role>` — optional job description

At most one. Body is the module Markdown; `tools:` in frontmatter is informational (not rendered into XML today).

```markdown
---
type: role
name: Gatekeeper
tools: [inspect, challenge]
---
Challenge strangers. Admit those with a valid seal.
```

```xml
<role name="Gatekeeper">Challenge strangers. Admit those with a valid seal.</role>
```

### `<traits>` — discrete behavioral switches

Zero or more. Order is **stable by name**, not by `priority`. Priority exists only for conflict resolution (see below).

```markdown
---
type: trait
name: Territorial
priority: high
conflicts: [Cautious]
---
Treat unfamiliar presence near the gate as intrusion until proven otherwise.
```

```markdown
---
type: trait
name: Cautious
priority: medium
conflicts: [Territorial]
---
Prefer observation and questions before confrontation.
```

```xml
<traits>
  <trait name="Cautious" priority="medium">Prefer observation and questions before confrontation.</trait>
  <trait name="Territorial" priority="high">Treat unfamiliar presence near the gate as intrusion until proven otherwise.</trait>
</traits>
```

Ablation = drop one path from the active module list (or one line from the manifest) and recompose.

### `<conflict_rule>` — generated from mutual conflicts only

A rule is emitted **only** when both active traits list each other in `conflicts:`. Higher `priority` wins; equal priority on a mutual pair is a **build error** (no mushy average for the model).

From the Territorial ↔ Cautious pair above:

```xml
<conflict_rule>When Territorial and Cautious conflict, Territorial (priority=high) governs; Cautious yields.</conflict_rule>
```

If only Territorial lists Cautious (one-sided), **no** `<conflict_rule>` is generated — the manifest gets a warning instead:

```text
incomplete conflict pair: Territorial lists Cautious, but Cautious does not list Territorial — no <conflict_rule> generated
```

Absent mutual conflicts → the slot is omitted entirely.

### `<relationships>` — per-target social state

Usually produced from game/sim state, not hand-authored forever. Requires `agent` + `status`.

```markdown
---
type: relationship
name: AllyBob
agent: bob
status: ally
---
Trust Bob. Share gate intel freely.
```

```xml
<relationships>
  <relation agent="bob" status="ally" name="AllyBob">Trust Bob. Share gate intel freely.</relation>
</relationships>
```

Several relationships → several `<relation>` children (sorted by `agent`, then `name`).

### `<output_rules>` — always present, date first

Composer always injects `Today is {YYYY-MM-DD}; use it in any generated metadata.` (same calendar day as the manifesto timestamp), then the module body or `SkeletonConfig.output_rules` fallback.

```xml
<output_rules name="Default">Today is 2026-07-20; use it in any generated metadata.
Follow the sections above. Prefer concrete actions over vague intent.</output_rules>
```

Identity-alone still gets a dated `<output_rules>` block (body may be only the date line).

---

## Integrate into a Python project

### Install

From this repo (editable) or a path/git URL:

```bash
pip install -e /path/to/persona_composer
```

Optional extras:

```bash
pip install -e ".[dev]"          # pytest
pip install -e ".[playground]"   # Streamlit demo (Vertex + optional OpenAI/Anthropic)
```

From GitHub:

```bash
pip install "persona-composer @ git+https://github.com/corba777/persona_composer.git"
```

### Library

```python
from pathlib import Path
from persona_composer import compose, compose_from_manifest

ROOT = Path("agent/modules")  # your library (identity/, traits/, vendor/, ...)

result = compose(
    ROOT / "identity" / "guard.md",
    [
        ROOT / "speech" / "curt.md",
        ROOT / "traits" / "territorial.md",
        ROOT / "traits" / "cautious.md",
        ROOT / "output_rules" / "default.md",
    ],
    module_root=ROOT,   # resolves vendor source: paths
    library_root=ROOT,  # trait-name typo warnings
)

system_prompt = result.prompt_xml
manifest_json = result.manifest_json()

# later: recompose / ablate from the saved manifest
again = compose_from_manifest(
    Path("manifests/run-001.json"),
    module_root=ROOT,
    verify_hashes=True,
)
```

Pass the XML string as the model’s **system** instruction (Gemini `system_instruction`, Claude `system`, OpenAI `system` message, etc.).

### CLI

```bash
persona-compose compose --identity ... --module-root ... [modules...] --out prompt.xml --manifest run.json
persona-compose recompose run.json --module-root ... --out prompt.xml
```

### Decompose & rewrite (optional, additive)

Both keep **backward compatibility**: `compose` / manifests unchanged. The core **never** calls an LLM — you inject a callable or pass a precomputed response.

**Decompose** a monolith or vendored skill into draft modules:

```python
from persona_composer import decompose

result = decompose(
    Path("agent/identity.md"),
    llm_call=my_llm,          # or llm_response=json_text
    out_dir=Path("drafts"),
    source_relpath="vendor/foo/SKILL.md",  # optional extracted provenance
)
# Review drafts under drafts/, then compose as usual
```

```bash
# 1) optional: write the prompt for your LLM
persona-compose decompose identity.md --llm-response /dev/null --prompt-out /tmp/p.txt --no-write
# 2) after the model returns JSON:
persona-compose decompose identity.md --llm-response /tmp/answer.json --out-dir drafts/
```

**Rewrite** model output with `speech.mode: rewriter` modules (from paths or manifest `rewriter_stack`):

```python
from persona_composer import compose, apply_rewriters_from_manifest

composed = compose(identity, [rewriter_speech], module_root=ROOT)
draft = call_llm(system=composed.prompt_xml, user=user_msg)
final = apply_rewriters_from_manifest(
    draft, composed.manifest, llm_call=my_rewrite_llm, module_root=ROOT
).text
# Empty rewriter_stack → no-op (returns draft unchanged)
```

```bash
persona-compose rewrite --text "Hello" --modules speech/fancy_rewriter.md --stub
persona-compose rewrite --text-file out.txt --from-manifest run.json --stub
```

### Playground (optional)

Interactive Streamlit UI to compose a persona, call an LLM, and export Markdown/PDF.

| Backend | When available |
|---------|----------------|
| **Vertex AI** (Gemini / Claude Model Garden) | Always (ADC + GCP project) |
| **OpenAI API** | `OPENAI_API_KEY` set in `.env` |
| **Anthropic API** | `ANTHROPIC_API_KEY` set in `.env` |

```bash
pip install -e ".[playground]"
cp .env.example .env
# edit .env:
#   OPENAI_API_KEY=...          # optional
#   ANTHROPIC_API_KEY=...       # optional
#   GOOGLE_CLOUD_PROJECT=...    # optional default for Vertex UI

gcloud auth application-default login   # for Vertex
streamlit run playground/app.py
```

Without API keys, the sidebar shows **Vertex presets only**. See [`.env.example`](./.env.example).

MD/PDF exports include the full experiment **manifest** (module hashes) so a run is reproducible.

---

## Integrate into a TypeScript / Node project

### Install

From this repo:

```bash
cd /path/to/persona_composer/ts
npm install
npm run build
```

In your app, depend on the local package:

```json
{
  "dependencies": {
    "persona-composer": "file:../persona_composer/ts"
  }
}
```

Or from GitHub (after clone + build in `ts/`):

```bash
npm install git+https://github.com/corba777/persona_composer.git#main
```

Consumers need the built `dist/` (run `npm run build` in `ts/` after clone).

### Library

```ts
import { compose, composeFromManifest } from "persona-composer";
import path from "node:path";

const ROOT = path.resolve("agent/modules");

const result = compose(
  path.join(ROOT, "identity/guard.md"),
  [
    path.join(ROOT, "speech/curt.md"),
    path.join(ROOT, "traits/territorial.md"),
    path.join(ROOT, "traits/cautious.md"),
    path.join(ROOT, "output_rules/default.md"),
  ],
  { moduleRoot: ROOT, libraryRoot: ROOT },
);

const systemPrompt = result.promptXml;
const manifestJson = result.manifestJson();

const again = composeFromManifest("./manifests/run-001.json", {
  moduleRoot: ROOT,
  verifyHashes: true,
});
```

### CLI

```bash
npx persona-compose compose --identity ... --module-root ... [modules...]
# or after build:
node node_modules/persona-composer/dist/cli.js compose ...
```

---

## Suggested consumer layout

Directory names are conventional, not semantic — the composer only trusts frontmatter `type:`:

```
agent/
  modules/
    identity/
    roles/
    traits/
    speech/
    relationships/
    output_rules/
    vendor/           # pristine upstream skills
  manifests/          # experiment receipts
```

Drop modules under `agent/general/` or `agent/<agent_id>/` if you prefer; pass an explicit file list (or a manifest) into `compose`.

---

## Tests

```bash
# Python
pip install -e ".[dev]"
pytest

# TypeScript (uses the same tests/fixtures golden XML)
cd ts && npm test
```

CI (`.github/workflows/ci.yml`) runs both on every push/PR so golden XML stays the cross-language contract.

No LLM calls in unit tests — this repo tests the compiler, not model behavior.

---

## License / scope

MIT — see [`LICENSE`](./LICENSE). Personal instrument for multi-agent experiments (game NPCs, process sims, MAS). Not aiming at a plugin marketplace or framework lock-in. See [`CLAUDE.md`](./CLAUDE.md) for anti-goals and the full schema.
