"""Decompose / rewrite panels for the Streamlit playground."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st

from persona_composer.decompose import decompose
from persona_composer.parse import split_frontmatter
from persona_composer.rewriter import (
    apply_rewriters_from_manifest,
    apply_rewriters_from_paths,
)
from playground.modules_io import list_modules_by_type, save_upload


GenerateFn = Callable[..., str]


def list_rewriter_modules(root: Path) -> list[tuple[str, Path]]:
    """Speech modules with ``mode: rewriter`` under ``root``."""
    found: list[tuple[str, Path]] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("*.md")):
        try:
            fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if fm.get("type") != "speech":
            continue
        if str(fm.get("mode") or "prompt").lower() != "rewriter":
            continue
        name = str(fm.get("name") or path.stem)
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path.name
        found.append((f"{name} ({rel})", path))
    return found


def render_decompose_tab(
    *,
    module_root: Path,
    work_dir: Path,
    generate_fn: GenerateFn,
    gen_kwargs: dict[str, Any],
) -> None:
    st.markdown("#### Decompose")
    st.caption(
        "Split a monolith identity or vendored skill into draft modules. "
        "Core never calls a model — playground injects the sidebar LLM as "
        "`llm_call`. Review drafts before composing."
    )

    src_mode = st.radio(
        "Source",
        ["Paste", "Upload", "Library identity"],
        horizontal=True,
        key="decomp_src_mode",
    )
    source: str | Path | None = None
    source_kind = st.selectbox(
        "Source kind",
        ["identity", "skill", "raw"],
        index=0,
        key="decomp_kind",
    )

    if src_mode == "Paste":
        body = st.text_area("Source text", height=220, key="decomp_paste")
        if body.strip():
            source = body
    elif src_mode == "Upload":
        up = st.file_uploader("Markdown / skill file", type=["md", "txt"], key="decomp_up")
        if up is not None:
            source = save_upload(work_dir, filename=up.name, data=up.getvalue())
    else:
        options = list_modules_by_type(module_root, "identity")
        if not options:
            st.info("No identity modules in library.")
        else:
            labels = [o[0] for o in options]
            choice = st.selectbox("Identity", labels, key="decomp_lib")
            source = dict(options)[choice]

    out_dir = work_dir / "drafts"
    write_drafts = st.checkbox("Write draft modules to work dir", value=True, key="decomp_write")

    if st.button("Run decompose", type="primary", key="decomp_run"):
        if source is None or (isinstance(source, str) and not source.strip()):
            st.error("Provide a source first.")
        else:
            def llm_call(prompt: str) -> str:
                return generate_fn(
                    **gen_kwargs,
                    system_prompt=(
                        "You decompose agent personas into modular Markdown. "
                        "Return ONLY the JSON object described in the user "
                        "message. No markdown fences, no commentary."
                    ),
                    user_message=prompt,
                )

            try:
                with st.spinner("Decomposing…"):
                    result = decompose(
                        source,
                        llm_call=llm_call,
                        out_dir=out_dir if write_drafts else None,
                        source_kind=source_kind,  # type: ignore[arg-type]
                        write_drafts=write_drafts,
                    )
                st.session_state.decomp_result = result.to_dict()
                st.session_state.decomp_drafts = [str(p) for p in result.draft_paths]
            except Exception as exc:
                st.session_state.decomp_result = None
                st.error(str(exc))

    data = st.session_state.get("decomp_result")
    if data:
        st.markdown("##### Summary")
        st.write(data.get("summary") or "_(none)_")
        if data.get("remaining_identity_body"):
            with st.expander("Remaining identity body", expanded=False):
                st.code(data["remaining_identity_body"], language="markdown")
        st.markdown("##### Suggestions")
        st.json(data.get("suggestions") or [])
        drafts = st.session_state.get("decomp_drafts") or []
        if drafts:
            st.markdown("##### Draft files")
            for p in drafts:
                st.code(p, language="text")
            st.caption(f"Drafts under `{out_dir}` — review, then use in Chat / Library.")
        with st.expander("Raw decompose result JSON", expanded=False):
            st.code(json.dumps(data, indent=2), language="json")


def render_rewrite_tab(
    *,
    module_root: Path,
    generate_fn: GenerateFn,
    gen_kwargs: dict[str, Any],
) -> None:
    st.markdown("#### Rewrite")
    st.caption(
        "Post-pass with `speech.mode: rewriter` modules. "
        "Empty `rewriter_stack` in a manifest is a no-op. "
        "Uses the sidebar model as `llm_call(system, user)`."
    )

    default_text = st.session_state.get("last_response") or ""
    text = st.text_area(
        "Draft text",
        value=default_text,
        height=180,
        key="rewrite_text",
        help="Defaults to last Chat Generate output when present.",
    )

    mode = st.radio(
        "Rewriter source",
        ["Last compose manifest", "Pick rewriter modules"],
        horizontal=True,
        key="rewrite_src",
    )

    module_paths: list[Path] = []
    use_manifest = mode == "Last compose manifest"
    if use_manifest:
        man = st.session_state.get("last_manifest")
        if not man:
            st.info("Compose a persona in Chat first (manifest needed).")
        else:
            stack = man.get("rewriter_stack") or []
            st.caption(f"rewriter_stack: {len(stack)} module(s)")
            if stack:
                st.json(stack)
            else:
                st.caption("Stack empty → rewrite will return the draft unchanged.")
    else:
        options = list_rewriter_modules(module_root)
        if not options:
            st.info(
                "No `mode: rewriter` speech modules in the library. "
                "Demo: tests/fixtures/modules/speech/fancy_rewriter.md"
            )
        else:
            labels = [o[0] for o in options]
            picked = st.multiselect("Rewriter modules", labels, key="rewrite_mods")
            by_label = dict(options)
            module_paths = [by_label[x] for x in picked]

    if st.button("Run rewrite", type="primary", key="rewrite_run"):
        if not text.strip():
            st.error("Draft text is empty.")
        else:

            def llm_call(system: str, user: str) -> str:
                return generate_fn(
                    **gen_kwargs,
                    system_prompt=system,
                    user_message=user,
                )

            try:
                with st.spinner("Rewriting…"):
                    if use_manifest:
                        man = st.session_state.get("last_manifest")
                        if not man:
                            raise ValueError("No compose manifest in session")
                        result = apply_rewriters_from_manifest(
                            text,
                            man,
                            llm_call=llm_call,
                            module_root=module_root if module_root.is_dir() else None,
                        )
                    else:
                        if not module_paths:
                            raise ValueError("Pick at least one rewriter module")
                        result = apply_rewriters_from_paths(
                            text,
                            module_paths,
                            llm_call=llm_call,
                            module_root=module_root if module_root.is_dir() else None,
                        )
                st.session_state.rewrite_result = {
                    "text": result.text,
                    "steps": [
                        {
                            "module_name": s.module_name,
                            "module_path": s.module_path,
                            "output": s.output,
                        }
                        for s in result.steps
                    ],
                }
            except Exception as exc:
                st.session_state.rewrite_result = None
                st.error(str(exc))

    data = st.session_state.get("rewrite_result")
    if data:
        st.markdown("##### Rewritten text")
        st.markdown(data["text"])
        steps = data.get("steps") or []
        if steps:
            with st.expander(f"Steps ({len(steps)})", expanded=False):
                for i, step in enumerate(steps, 1):
                    st.markdown(f"**{i}. {step['module_name']}** — `{step['module_path']}`")
                    st.code(step["output"], language="markdown")
        if st.button("Use rewritten text as last Chat output", key="rewrite_to_chat"):
            st.session_state.last_response = data["text"]
            st.success("Copied into Chat model output / export.")
