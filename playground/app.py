"""Persona Composer — Streamlit playground (Vertex / OpenAI / Anthropic).

Run from repo root:
  .venv/bin/streamlit run playground/app.py

Optional API keys in repo-root `.env` (see `.env.example`):
  OPENAI_API_KEY=...
  ANTHROPIC_API_KEY=...
Without those keys, only Vertex AI presets are shown.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Repo root on path so `playground.*` and `persona_composer` resolve.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from playground.llm import (  # noqa: E402
    api_availability,
    available_presets,
    generate,
    is_vertex,
    load_env,
)

load_env(_ROOT)

import streamlit as st  # noqa: E402

from playground.export import build_markdown, build_pdf, default_basename  # noqa: E402
from playground.modules_io import (  # noqa: E402
    compose_persona,
    ensure_typed_module,
    library_root,
    list_modules_by_type,
    save_upload,
    write_identity_md,
    write_output_rules_md,
    write_role_md,
    write_speech_md,
)
from playground.styles import inject_css  # noqa: E402
from playground.module_apply import compile_persona_modules  # noqa: E402
from playground.snippets import build_repro_snippets  # noqa: E402
from playground.workflows import render_decompose_tab, render_rewrite_tab  # noqa: E402

st.set_page_config(
    page_title="Persona Composer Playground",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "theme" not in st.session_state:
    st.session_state.theme = "light"
if "last_response" not in st.session_state:
    st.session_state.last_response = ""
if "last_prompt" not in st.session_state:
    st.session_state.last_prompt = ""
if "last_error" not in st.session_state:
    st.session_state.last_error = ""
if "last_user_msg" not in st.session_state:
    st.session_state.last_user_msg = ""
if "last_meta" not in st.session_state:
    st.session_state.last_meta = {}
if "last_manifest" not in st.session_state:
    st.session_state.last_manifest = None
if "decomp_result" not in st.session_state:
    st.session_state.decomp_result = None
if "rewrite_result" not in st.session_state:
    st.session_state.rewrite_result = None
if "speech_compile_cache" not in st.session_state:
    st.session_state.speech_compile_cache = {}
if "speech_compile_notes" not in st.session_state:
    st.session_state.speech_compile_notes = []
if "persona_compile_cache" not in st.session_state:
    st.session_state.persona_compile_cache = {}
if "persona_compile_notes" not in st.session_state:
    st.session_state.persona_compile_notes = []
if "last_compose_paths" not in st.session_state:
    st.session_state.last_compose_paths = None
if "work_dir" not in st.session_state:
    st.session_state.work_dir = tempfile.mkdtemp(prefix="persona_ui_")


def _work() -> Path:
    return Path(st.session_state.work_dir)


st.markdown(
    inject_css(dark=st.session_state.theme == "dark"),
    unsafe_allow_html=True,
)

avail = api_availability()
presets = available_presets(avail)

# ---------------------------------------------------------------------------
# Sidebar — model backends
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="pc-brand">Persona ◆ Composer</div>', unsafe_allow_html=True)
    st.caption("Compose modules → call an LLM → compare personas live")

    if st.button("Toggle theme", use_container_width=True):
        st.session_state.theme = (
            "dark" if st.session_state.theme == "light" else "light"
        )
        st.rerun()

    st.divider()
    st.subheader("Model")

    bits = ["Vertex AI"]
    if avail.openai:
        bits.append("OpenAI ✓")
    else:
        bits.append("OpenAI (no key)")
    if avail.anthropic:
        bits.append("Anthropic ✓")
    else:
        bits.append("Anthropic (no key)")
    st.caption(" · ".join(bits))

    preset_labels = [m.label for m in presets] + ["Custom…"]
    preset_ix = st.selectbox(
        "Model preset",
        range(len(preset_labels)),
        format_func=lambda i: preset_labels[i],
    )

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT", ""))
    location = ""
    provider: str
    model_id: str

    if preset_ix < len(presets):
        preset = presets[preset_ix]
        provider = preset.provider
        model_id = st.text_input("Model id", value=preset.model_id)
        if is_vertex(provider):  # type: ignore[arg-type]
            project = st.text_input(
                "GCP project",
                value=project,
                help="Application Default Credentials (gcloud auth application-default login)",
            )
            location = st.text_input(
                "Location",
                value=preset.default_location,
                help=(
                    "Gemini 3.5 / Claude 4.6: `global`. "
                    "Claude models need backend vertex_claude (publishers/anthropic), "
                    "not the Gemini client (publishers/google)."
                ),
            )
        st.caption(f"Backend: **{provider}**")
    else:
        custom_options = ["vertex_gemini", "vertex_claude"]
        if avail.openai:
            custom_options.append("openai")
        if avail.anthropic:
            custom_options.append("anthropic")
        provider = st.selectbox("Provider", custom_options)
        defaults = {
            "vertex_gemini": "gemini-3.5-flash",
            "vertex_claude": "claude-opus-4-6",
            "openai": "gpt-4.1",
            "anthropic": "claude-sonnet-4-20250514",
        }
        model_id = st.text_input("Model id", value=defaults.get(provider, ""))
        if is_vertex(provider):  # type: ignore[arg-type]
            project = st.text_input(
                "GCP project",
                value=project,
                help="Application Default Credentials",
            )
            location = st.text_input(
                "Location",
                value="global" if provider in ("vertex_gemini", "vertex_claude") else "us-east5",
                help=(
                    "Gemini 3.5 / Claude 4.6: often `global`. "
                    "Older Claude dated ids: try `us-east5`. "
                    "Claude must use provider vertex_claude (Anthropic), not vertex_gemini."
                ),
            )

    temperature = st.slider("Temperature", 0.0, 1.5, 0.7, 0.05)
    max_tokens = st.number_input(
        "Max tokens",
        min_value=256,
        max_value=8192,
        value=4096,
        step=256,
        help="Gemini 2.5 thinking shares this budget — use ≥4096 if replies come back empty.",
    )

    if not avail.openai and not avail.anthropic:
        st.info(
            "Only Vertex AI is available. Add `OPENAI_API_KEY` and/or "
            "`ANTHROPIC_API_KEY` to `.env` in the repo root to unlock API backends."
        )

    st.divider()
    lib = st.text_input(
        "Module library root",
        value=str(library_root()),
        help="Folder scanned for existing identity / speech / trait modules",
    )
    module_root = Path(lib)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("### Playground")
st.markdown(
    '<p class="pc-muted">Wire <code>persona_composer</code> to Gemini or Claude on Vertex. '
    "Change identity / speech / traits and re-run — composed XML updates immediately.</p>",
    unsafe_allow_html=True,
)

_gen_kwargs = {
    "provider": provider,
    "project": project,
    "location": location,
    "model_id": model_id,
    "temperature": float(temperature),
    "max_tokens": int(max_tokens),
}

tab_chat, tab_decompose, tab_rewrite = st.tabs(["Chat", "Decompose", "Rewrite"])

with tab_decompose:
    render_decompose_tab(
        module_root=module_root,
        work_dir=_work(),
        generate_fn=generate,
        gen_kwargs=_gen_kwargs,
    )

with tab_rewrite:
    render_rewrite_tab(
        module_root=module_root,
        generate_fn=generate,
        gen_kwargs=_gen_kwargs,
    )

with tab_chat:
    col_persona, col_chat = st.columns([1.05, 1], gap="large")
    # ---------------------------------------------------------------------------
    # Persona builder
    # ---------------------------------------------------------------------------
    with col_persona:
        st.markdown("#### Persona")

        # --- Identity ---
        st.markdown("**Identity** *(required)*")
        id_mode = st.radio(
            "Identity source",
            ["Paste prompt", "Upload .md", "Library"],
            horizontal=True,
            key="id_mode",
            label_visibility="collapsed",
        )

        identity_path: Path | None = None
        if id_mode == "Paste prompt":
            id_name = st.text_input("Identity name", value="DemoAgent", key="id_name")
            id_body = st.text_area(
                "Identity / system prompt body",
                height=160,
                value=(
                    "You are the gate guard of Amber Outpost. Protect the gate. "
                    "Speak briefly. Stay in character."
                ),
                key="id_body",
            )
            if id_body.strip():
                identity_path = write_identity_md(_work(), name=id_name, body=id_body)
        elif id_mode == "Upload .md":
            up = st.file_uploader("Identity markdown", type=["md", "markdown", "txt"], key="id_up")
            if up is not None:
                raw = save_upload(_work(), filename=up.name, data=up.getvalue())
                identity_path = ensure_typed_module(
                    raw,
                    expected_type="identity",
                    fallback_name=Path(up.name).stem,
                    work_dir=_work(),
                )
        else:
            options = list_modules_by_type(module_root, "identity")
            if not options:
                st.warning("No identity modules found in library root.")
            else:
                labels = [o[0] for o in options]
                choice = st.selectbox("Existing identity", labels, key="id_lib")
                identity_path = dict(options)[choice]

        # --- Speech ---
        st.markdown("**Speech** *(optional)*")
        use_speech = st.checkbox("Attach speech module", value=True)
        speech_path: Path | None = None
        speech_in_prompt = True
        if use_speech:
            sp_mode = st.radio(
                "Speech source",
                ["Paste style", "Upload .md", "Library"],
                horizontal=True,
                key="sp_mode",
                label_visibility="collapsed",
            )
            if sp_mode == "Paste style":
                sp_name = st.text_input("Speech name", value="Curt", key="sp_name")
                sp_body = st.text_area(
                    "Speech directives",
                    height=100,
                    value="Use short sentences. No small talk. Prefer blunt clarity.",
                    key="sp_body",
                )
                if sp_body.strip():
                    speech_path = write_speech_md(_work(), name=sp_name, body=sp_body)
            elif sp_mode == "Upload .md":
                up = st.file_uploader("Speech markdown", type=["md", "markdown", "txt"], key="sp_up")
                if up is not None:
                    raw = save_upload(_work(), filename=up.name, data=up.getvalue())
                    speech_path = ensure_typed_module(
                        raw,
                        expected_type="speech",
                        fallback_name=Path(up.name).stem,
                        work_dir=_work(),
                    )
            else:
                options = list_modules_by_type(module_root, "speech")
                if not options:
                    st.info("No speech modules in library.")
                else:
                    labels = [o[0] for o in options]
                    choice = st.selectbox("Existing speech", labels, key="sp_lib")
                    speech_path = dict(options)[choice]

            speech_in_prompt = st.checkbox(
                "Include speech in prompt",
                value=True,
                key="speech_in_prompt",
                help="If off, speech is only used when Post-rewrite is enabled (mode:rewriter).",
            )
        # --- Traits ---
        st.markdown("**Traits** *(optional)*")
        trait_options = list_modules_by_type(module_root, "trait")
        trait_labels = [o[0] for o in trait_options]
        selected_traits = st.multiselect(
            "Active traits",
            trait_labels,
            default=[t for t in trait_labels if "Territorial" in t or "Cautious" in t][:2],
            key="traits",
        )
        trait_paths = [dict(trait_options)[label] for label in selected_traits]

        # --- Role ---
        st.markdown("**Role** *(optional)*")
        use_role = st.checkbox("Attach role module", value=False, key="use_role")
        role_path: Path | None = None
        if use_role:
            role_mode = st.radio(
                "Role source",
                ["Paste text", "Upload .md", "Library"],
                horizontal=True,
                key="role_mode",
                label_visibility="collapsed",
            )
            if role_mode == "Paste text":
                role_name = st.text_input("Role name", value="Gatekeeper", key="role_name")
                role_body = st.text_area(
                    "Role directives",
                    height=100,
                    value="Challenge strangers. Admit those with a valid seal.",
                    key="role_body",
                )
                if role_body.strip():
                    role_path = write_role_md(_work(), name=role_name, body=role_body)
            elif role_mode == "Upload .md":
                up = st.file_uploader(
                    "Role markdown", type=["md", "markdown", "txt"], key="role_up"
                )
                if up is not None:
                    raw = save_upload(_work(), filename=up.name, data=up.getvalue())
                    role_path = ensure_typed_module(
                        raw,
                        expected_type="role",
                        fallback_name=Path(up.name).stem,
                        work_dir=_work(),
                    )
            else:
                role_options = list_modules_by_type(module_root, "role")
                if not role_options:
                    st.info("No role modules in library.")
                else:
                    labels = [o[0] for o in role_options]
                    choice = st.selectbox("Existing role", labels, key="role_lib")
                    role_path = dict(role_options)[choice]

        # --- Output rules (optional) ---
        st.markdown("**Output rules** *(optional)*")
        use_out = st.checkbox("Attach output_rules", value=True, key="use_out")
        output_rules_path: Path | None = None
        if use_out:
            out_mode = st.radio(
                "Output rules source",
                ["Paste text", "Upload .md", "Library"],
                horizontal=True,
                key="out_mode",
                label_visibility="collapsed",
            )
            if out_mode == "Paste text":
                out_name = st.text_input("Output rules name", value="Default", key="out_name")
                out_body = st.text_area(
                    "Output rules body",
                    height=90,
                    value=(
                        "Follow the sections above. Prefer concrete actions over vague intent."
                    ),
                    key="out_body",
                )
                if out_body.strip():
                    output_rules_path = write_output_rules_md(
                        _work(), name=out_name, body=out_body
                    )
            elif out_mode == "Upload .md":
                up = st.file_uploader(
                    "Output rules markdown",
                    type=["md", "markdown", "txt"],
                    key="out_up",
                )
                if up is not None:
                    raw = save_upload(_work(), filename=up.name, data=up.getvalue())
                    output_rules_path = ensure_typed_module(
                        raw,
                        expected_type="output_rules",
                        fallback_name=Path(up.name).stem,
                        work_dir=_work(),
                    )
            else:
                options = list_modules_by_type(module_root, "output_rules")
                if not options:
                    st.info("No output_rules modules in library.")
                else:
                    labels = [o[0] for o in options]
                    # Prefer Default if present
                    default_ix = next(
                        (i for i, lab in enumerate(labels) if "Default" in lab), 0
                    )
                    choice = st.selectbox(
                        "Existing output_rules",
                        labels,
                        index=default_ix,
                        key="out_lib",
                    )
                    output_rules_path = dict(options)[choice]

        st.markdown("**Adaptation pipeline** *(all attached modules)*")
        persona_extract = st.checkbox(
            "Extract / adapt first",
            value=False,
            key="persona_extract",
            help=(
                "On Generate, distill every attached module (identity, speech, "
                "traits, role, output_rules) into adaptation:extracted overlays. "
                "Uses the sidebar LLM."
            ),
        )
        persona_post_rewrite = st.checkbox(
            "Post-rewrite output",
            value=False,
            key="persona_post_rewrite",
            help=(
                "Compile speech as mode:rewriter and restyle the model reply after "
                "Generate. Requires an attached speech module."
            ),
        )
        if persona_post_rewrite and (not use_speech or speech_path is None):
            st.warning("Post-rewrite needs an attached speech module.")
        if (
            use_speech
            and speech_path is not None
            and not speech_in_prompt
            and not persona_post_rewrite
        ):
            st.warning("Speech is attached but neither in-prompt nor Post-rewrite is on.")
        if st.session_state.persona_compile_notes:
            with st.expander("Compiled modules", expanded=False):
                for note in st.session_state.persona_compile_notes:
                    st.caption(note)
                cache = st.session_state.persona_compile_cache or {}
                for key in ("last_identity",):
                    p = cache.get(key)
                    if p and Path(p).is_file():
                        st.markdown(f"`{Path(p).name}` (identity)")
                        st.code(Path(p).read_text(encoding="utf-8")[:4000], language="markdown")
                for p in cache.get("last_modules") or []:
                    if Path(p).is_file():
                        st.markdown(f"`{Path(p).name}`")
                        st.code(Path(p).read_text(encoding="utf-8")[:4000], language="markdown")

        extras: list[Path] = []
        if speech_path is not None and speech_in_prompt:
            extras.append(speech_path)
        if role_path is not None:
            extras.append(role_path)
        extras.extend(trait_paths)
        if output_rules_path is not None:
            extras.append(output_rules_path)
        if persona_extract:
            st.caption(
                "Extract/adapt runs on **Generate** (cache reused when sources unchanged). "
                "XML preview below may still show un-extracted modules until then."
            )

        # Prefer last successful compile paths for preview when cache is warm.
        preview_identity = identity_path
        preview_extras = list(extras)
        cache = st.session_state.persona_compile_cache or {}
        if (
            persona_extract
            and cache.get("last_identity")
            and Path(cache["last_identity"]).is_file()
            and identity_path is not None
        ):
            preview_identity = Path(cache["last_identity"])
            preview_extras = [Path(p) for p in (cache.get("last_modules") or []) if Path(p).is_file()]
            # Drop rewriter-only from preview XML noise is ok — rewriter excluded by compose

        composed_xml = ""
        warnings: list[str] = []
        if preview_identity is not None:
            try:
                bundle = compose_persona(
                    identity_path=preview_identity,
                    extra_paths=preview_extras,
                    module_root=module_root if module_root.is_dir() else None,
                )
                composed_xml = bundle.prompt_xml
                warnings = bundle.warnings
                st.session_state.last_prompt = composed_xml
                st.session_state.last_manifest = json.loads(bundle.manifest_json)
            except Exception as exc:
                st.error(f"Compose failed: {exc}")
        else:
            st.info("Provide an identity to compose a prompt.")

        for w in warnings:
            st.warning(w)

        with st.expander("Composed system prompt (XML)", expanded=True):
            if composed_xml:
                st.code(composed_xml, language="xml")
            else:
                st.caption("Nothing composed yet.")

        # Repro snippets (paths from last Generate compile, else current selection)
        snip_id = None
        snip_mods: list[Path] = []
        if st.session_state.last_compose_paths:
            snip_id = Path(st.session_state.last_compose_paths["identity"])
            snip_mods = [Path(p) for p in st.session_state.last_compose_paths["modules"]]
        elif identity_path is not None:
            snip_id = identity_path
            snip_mods = list(extras)
            if persona_post_rewrite and speech_path is not None and not speech_in_prompt:
                pass  # rewriter appears after compile
        if snip_id is not None:
            snippets = build_repro_snippets(
                identity_path=snip_id,
                module_paths=snip_mods,
                module_root=module_root if module_root.is_dir() else None,
                repo_root=_ROOT,
                extract=persona_extract,
                post_rewrite=persona_post_rewrite,
                speech_in_prompt=speech_in_prompt,
            )
            with st.expander("Reproduce without UI (CLI / Python / TypeScript)", expanded=False):
                st.caption(
                    "Uses the module paths from the last successful Generate when available "
                    "(including extracted / rewriter overlays)."
                )
                tab_cli, tab_py, tab_ts = st.tabs(["CLI", "Python", "TypeScript"])
                with tab_cli:
                    st.code(snippets["cli"], language="bash")
                with tab_py:
                    st.code(snippets["python"], language="python")
                with tab_ts:
                    st.code(snippets["typescript"], language="typescript")

    # ---------------------------------------------------------------------------
    # Chat / run
    # ---------------------------------------------------------------------------
    with col_chat:
        st.markdown("#### Request")
        user_msg = st.text_area(
            "User message",
            height=140,
            value="A traveler approaches the gate at dusk without a seal. What do you say?",
            key="user_msg",
        )

        run = st.button("Generate", type="primary", use_container_width=True)

        if run:
            st.session_state.last_error = ""
            if identity_path is None:
                st.session_state.last_error = "Compose a persona (identity required) before generating."
            elif (
                use_speech
                and speech_path is not None
                and not speech_in_prompt
                and not persona_post_rewrite
            ):
                st.session_state.last_error = (
                    "Speech is attached but neither Include in prompt nor Post-rewrite is selected."
                )
            elif persona_post_rewrite and (not use_speech or speech_path is None):
                st.session_state.last_error = "Post-rewrite requires an attached speech module."
            else:
                try:
                    root = module_root if module_root.is_dir() else None
                    source_extras: list[Path] = []
                    if speech_path is not None:
                        source_extras.append(speech_path)
                    if role_path is not None:
                        source_extras.append(role_path)
                    source_extras.extend(trait_paths)
                    if output_rules_path is not None:
                        source_extras.append(output_rules_path)

                    def _llm_pair(system: str, user: str) -> str:
                        return generate(
                            provider=provider,  # type: ignore[arg-type]
                            project=project,
                            location=location,
                            model_id=model_id,
                            system_prompt=system,
                            user_message=user,
                            temperature=float(temperature),
                            max_tokens=int(max_tokens),
                        )

                    need_compile = persona_extract or persona_post_rewrite
                    if need_compile:
                        with st.spinner("Compiling persona modules (extract / rewriter)…"):
                            compiled, cache = compile_persona_modules(
                                identity_path=identity_path,
                                extra_paths=source_extras,
                                work_dir=_work(),
                                module_root=root,
                                extract=persona_extract,
                                post_rewrite=persona_post_rewrite,
                                speech_in_prompt=speech_in_prompt,
                                llm_call=_llm_pair if persona_extract else None,
                                cache=st.session_state.persona_compile_cache,
                            )
                        st.session_state.persona_compile_cache = cache
                        st.session_state.persona_compile_notes = list(compiled.notes)
                        run_identity = compiled.identity_path
                        run_extras = list(compiled.module_paths)
                    else:
                        run_identity = identity_path
                        run_extras = []
                        if speech_path is not None and speech_in_prompt:
                            run_extras.append(speech_path)
                        if role_path is not None:
                            run_extras.append(role_path)
                        run_extras.extend(trait_paths)
                        if output_rules_path is not None:
                            run_extras.append(output_rules_path)

                    st.session_state.last_compose_paths = {
                        "identity": str(run_identity),
                        "modules": [str(p) for p in run_extras],
                    }

                    with st.spinner("Composing persona…"):
                        bundle = compose_persona(
                            identity_path=run_identity,
                            extra_paths=run_extras,
                            module_root=root,
                        )
                    prompt_xml = bundle.prompt_xml
                    manifest = json.loads(bundle.manifest_json)
                    st.session_state.last_prompt = prompt_xml
                    st.session_state.last_manifest = manifest

                    with st.spinner(f"Calling {provider}:{model_id}…"):
                        text = generate(
                            provider=provider,  # type: ignore[arg-type]
                            project=project,
                            location=location,
                            model_id=model_id,
                            system_prompt=prompt_xml,
                            user_message=user_msg,
                            temperature=float(temperature),
                            max_tokens=int(max_tokens),
                        )

                    if persona_post_rewrite and (manifest.get("rewriter_stack") or []):
                        from persona_composer.rewriter import apply_rewriters_from_manifest

                        with st.spinner("Post-rewrite…"):
                            rewritten = apply_rewriters_from_manifest(
                                text,
                                manifest,
                                llm_call=_llm_pair,
                                module_root=root,
                            )
                        text = rewritten.text

                    st.session_state.last_response = text
                    st.session_state.last_user_msg = user_msg
                    st.session_state.last_meta = {
                        "project": project,
                        "provider": provider,
                        "model_id": model_id,
                        "location": location,
                        "temperature": float(temperature),
                        "speech_in_prompt": speech_in_prompt,
                        "persona_extract": persona_extract,
                        "persona_post_rewrite": persona_post_rewrite,
                    }
                except Exception as exc:
                    st.session_state.last_error = str(exc)
                    st.session_state.last_response = ""

        if st.session_state.last_error:
            st.error(st.session_state.last_error)

        st.markdown("#### Model output")
        if st.session_state.last_response:
            st.markdown(st.session_state.last_response)
        else:
            st.caption("Response appears here after Generate.")

        # --- Export ---
        can_export = bool(
            st.session_state.last_response or st.session_state.last_prompt
        )
        st.markdown("#### Export")
        if not can_export:
            st.caption("Generate (or compose) first to enable downloads.")
        else:
            meta = st.session_state.last_meta or {
                "project": project,
                "provider": provider,
                "model_id": model_id,
                "location": location,
                "temperature": float(temperature),
            }
            md_text = build_markdown(
                project=str(meta.get("project", project)),
                provider=str(meta.get("provider", provider)),
                model_id=str(meta.get("model_id", model_id)),
                location=str(meta.get("location", location)),
                temperature=float(meta.get("temperature", temperature)),
                user_message=st.session_state.last_user_msg or user_msg,
                system_prompt=st.session_state.last_prompt or composed_xml,
                model_output=st.session_state.last_response,
                manifest=st.session_state.last_manifest,
            )
            base = default_basename()
            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    label="Download Markdown",
                    data=md_text.encode("utf-8"),
                    file_name=f"{base}.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key="dl_md",
                )
            with dl2:
                try:
                    pdf_bytes = build_pdf(
                        project=str(meta.get("project", project)),
                        provider=str(meta.get("provider", provider)),
                        model_id=str(meta.get("model_id", model_id)),
                        location=str(meta.get("location", location)),
                        temperature=float(meta.get("temperature", temperature)),
                        user_message=st.session_state.last_user_msg or user_msg,
                        system_prompt=st.session_state.last_prompt or composed_xml,
                        model_output=st.session_state.last_response,
                        manifest=st.session_state.last_manifest,
                    )
                    st.download_button(
                        label="Download PDF",
                        data=pdf_bytes,
                        file_name=f"{base}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="dl_pdf",
                    )
                except Exception as exc:
                    st.warning(f"PDF export failed: {exc}")

        st.divider()
        st.markdown("#### Quick A/B tip")
        st.markdown(
            '<p class="pc-muted">Toggle traits or swap speech, then Generate again — '
            "the composed XML on the left updates on every widget change. "
            "For a true side-by-side, open a second browser tab with different settings.</p>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Footer hints
# ---------------------------------------------------------------------------
st.divider()
st.markdown(
    '<p class="pc-muted">'
    "Vertex: <code>gcloud auth application-default login</code> + GCP project. "
    "Optional API backends: put <code>OPENAI_API_KEY</code> / <code>ANTHROPIC_API_KEY</code> "
    "in repo-root <code>.env</code> (see <code>.env.example</code>). "
    "Without those keys, only Vertex presets appear."
    "</p>",
    unsafe_allow_html=True,
)
