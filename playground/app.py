"""Persona Composer — Streamlit playground (Vertex / OpenAI / Anthropic).

Run from repo root:
  .venv/bin/streamlit run playground/app.py

Optional API keys in repo-root `.env` (see `.env.example`):
  OPENAI_API_KEY=...
  ANTHROPIC_API_KEY=...
Without those keys, only Vertex AI presets are shown.
"""

from __future__ import annotations

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
    write_speech_md,
)
from playground.styles import inject_css  # noqa: E402

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
            location = st.text_input("Location", value=preset.default_location)
        st.caption(f"Backend: **{provider}**")
    else:
        custom_options = ["vertex_gemini", "vertex_claude"]
        if avail.openai:
            custom_options.append("openai")
        if avail.anthropic:
            custom_options.append("anthropic")
        provider = st.selectbox("Provider", custom_options)
        defaults = {
            "vertex_gemini": "gemini-2.5-flash",
            "vertex_claude": "claude-sonnet-4@20250514",
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
                value="us-central1" if provider == "vertex_gemini" else "us-east5",
            )

    temperature = st.slider("Temperature", 0.0, 1.5, 0.7, 0.05)
    max_tokens = st.number_input(
        "Max tokens", min_value=256, max_value=8192, value=2048, step=256
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
            # Prefer prompt-mode; still list all
            if not options:
                st.info("No speech modules in library.")
            else:
                labels = [o[0] for o in options]
                choice = st.selectbox("Existing speech", labels, key="sp_lib")
                speech_path = dict(options)[choice]

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

    # --- Role (optional library) ---
    role_options = list_modules_by_type(module_root, "role")
    role_path: Path | None = None
    if role_options:
        role_labels = ["(none)"] + [o[0] for o in role_options]
        role_choice = st.selectbox("Role", role_labels, key="role")
        if role_choice != "(none)":
            role_path = dict(role_options)[role_choice]

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

    extras: list[Path] = []
    if speech_path is not None:
        extras.append(speech_path)
    if role_path is not None:
        extras.append(role_path)
    extras.extend(trait_paths)
    if output_rules_path is not None:
        extras.append(output_rules_path)

    composed_xml = ""
    warnings: list[str] = []
    if identity_path is not None:
        try:
            bundle = compose_persona(
                identity_path=identity_path,
                extra_paths=extras,
                module_root=module_root if module_root.is_dir() else None,
            )
            composed_xml = bundle.prompt_xml
            warnings = bundle.warnings
            st.session_state.last_prompt = composed_xml
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
        if not composed_xml:
            st.session_state.last_error = "Compose a persona (identity required) before generating."
        else:
            try:
                with st.spinner(f"Calling {provider}:{model_id}…"):
                    text = generate(
                        provider=provider,  # type: ignore[arg-type]
                        project=project,
                        location=location,
                        model_id=model_id,
                        system_prompt=composed_xml,
                        user_message=user_msg,
                        temperature=float(temperature),
                        max_tokens=int(max_tokens),
                    )
                st.session_state.last_response = text
                st.session_state.last_user_msg = user_msg
                st.session_state.last_prompt = composed_xml
                st.session_state.last_meta = {
                    "project": project,
                    "provider": provider,
                    "model_id": model_id,
                    "location": location,
                    "temperature": float(temperature),
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
