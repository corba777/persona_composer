"""Build CLI / Python / TypeScript snippets that reproduce a playground run."""

from __future__ import annotations

from pathlib import Path


def _rel(path: Path, root: Path | None) -> str:
    try:
        if root is not None:
            return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        pass
    return str(path)


def build_repro_snippets(
    *,
    identity_path: Path,
    module_paths: list[Path],
    module_root: Path | None,
    repo_root: Path | None = None,
    extract: bool,
    post_rewrite: bool,
    speech_in_prompt: bool,
    manifest_path: str = "manifest.json",
    prompt_out: str = "prompt.xml",
    draft_out: str = "draft.txt",
    final_out: str = "final.txt",
) -> dict[str, str]:
    """Return ``{cli, python, typescript}`` code strings."""
    root = repo_root or Path.cwd()
    id_s = _rel(identity_path, root)
    root_s = _rel(module_root, root) if module_root else "."
    mods = [_rel(p, root) for p in module_paths]
    mods_cli = " \\\n  ".join(mods) if mods else ""

    extract_note = (
        "# Note: Extract/adapt already applied in the playground — paths below are "
        "the compiled overlays (adaptation: extracted) and/or rewriter modules.\n"
        if extract or post_rewrite
        else ""
    )

    cli_mods = f" \\\n  {mods_cli}" if mods_cli else ""
    cli = f"""{extract_note}# 1) Compose system prompt + manifest
persona-compose compose \\
  --identity {id_s} \\
  --module-root {root_s}{cli_mods} \\
  --manifest {manifest_path} \\
  --out {prompt_out}

# 2) Call your LLM with prompt.xml as the system prompt, user message as user;
#    write the model reply to {draft_out}

# 3) Optional post-rewrite (no-op if rewriter_stack is empty)
persona-compose rewrite \\
  --text-file {draft_out} \\
  --from-manifest {manifest_path} \\
  --module-root {root_s} \\
  --stub \\
  --out {final_out}
# Replace --stub with a real llm_call wrapper in library code for production.
"""
    if not post_rewrite:
        cli += (
            "\n# Post-rewrite was off in the UI — step 3 is optional / will no-op "
            "unless a mode:rewriter module is in the compose set.\n"
        )
    if not speech_in_prompt and post_rewrite:
        cli += (
            "\n# Speech was rewriter-only (not in prompt): style is applied in step 3.\n"
        )

    if mods:
        mods_py = ",\n    ".join(f'Path("{m}")' for m in mods)
        modules_py_block = f"modules = [\n    {mods_py},\n]"
        mods_ts = ",\n  ".join(f'"{m}"' for m in mods)
        modules_ts_block = f"const modules = [\n  {mods_ts},\n];"
    else:
        modules_py_block = "modules: list[Path] = []"
        modules_ts_block = "const modules: string[] = [];"

    python = f'''#!/usr/bin/env python3
"""Reproduce the playground compose (+ optional rewrite) without Streamlit."""
from __future__ import annotations

from pathlib import Path

from persona_composer import compose, apply_rewriters_from_manifest

ROOT = Path("{root_s}")
identity = Path("{id_s}")
{modules_py_block}

def llm_call(system: str, user: str) -> str:
    """Replace with Vertex / OpenAI / Anthropic — playground injects the sidebar model."""
    raise NotImplementedError("wire your LLM here")

composed = compose(identity, modules, module_root=ROOT, library_root=ROOT)
Path("{prompt_out}").write_text(composed.prompt_xml, encoding="utf-8")
Path("{manifest_path}").write_text(composed.manifest_json(), encoding="utf-8")

user_message = "…"  # same as playground Request
draft = llm_call(composed.prompt_xml, user_message)

final = apply_rewriters_from_manifest(
    draft,
    composed.manifest,
    llm_call=llm_call,
    module_root=ROOT,
).text
# Empty rewriter_stack → final == draft
Path("{final_out}").write_text(final, encoding="utf-8")
print(final)
'''

    typescript = f'''/** Reproduce the playground compose (+ optional rewrite) without Streamlit. */
import {{ compose, applyRewritersFromManifest }} from "persona-composer";
import {{ writeFileSync }} from "node:fs";

const ROOT = "{root_s}";
const identity = "{id_s}";
{modules_ts_block}

async function llmCall(system: string, user: string): Promise<string> {{
  // Replace with Vertex / OpenAI / Anthropic — playground injects the sidebar model.
  throw new Error("wire your LLM here");
}}

const composed = compose(identity, modules, {{
  moduleRoot: ROOT,
  libraryRoot: ROOT,
}});
writeFileSync("{prompt_out}", composed.promptXml, "utf8");
writeFileSync("{manifest_path}", composed.manifestJson(), "utf8");

const userMessage = "…"; // same as playground Request
const draft = await llmCall(composed.promptXml, userMessage);

const {{ text: final }} = await applyRewritersFromManifest(draft, composed.manifest, {{
  llmCall,
  moduleRoot: ROOT,
}});
// Empty rewriter_stack → final === draft
writeFileSync("{final_out}", final, "utf8");
console.log(final);
'''

    flags = (
        f"# UI flags: extract={extract}, speech_in_prompt={speech_in_prompt}, "
        f"post_rewrite={post_rewrite}\n"
    )
    return {
        "cli": flags + cli,
        "python": flags + python,
        "typescript": flags + typescript,
    }
