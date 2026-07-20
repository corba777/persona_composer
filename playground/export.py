"""Export playground runs to Markdown and PDF."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any


def build_markdown(
    *,
    project: str,
    provider: str,
    model_id: str,
    location: str,
    temperature: float,
    user_message: str,
    system_prompt: str,
    model_output: str,
    manifest: dict[str, Any] | None = None,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    parts = [
        "# Persona Composer — run export",
        "",
        f"_Exported {ts}_",
        "",
        "## Model",
        "",
        f"- **Provider:** `{provider}`",
        f"- **Model:** `{model_id}`",
        f"- **Location:** `{location}`",
        f"- **Project:** `{project}`",
        f"- **Temperature:** `{temperature}`",
        "",
        "## User message",
        "",
        user_message.strip() or "_(empty)_",
        "",
        "## Composed system prompt",
        "",
        "```xml",
        system_prompt.rstrip(),
        "```",
        "",
        "## Model output",
        "",
        model_output.strip() or "_(no output)_",
        "",
    ]
    if manifest is not None:
        parts.extend(
            [
                "## Experiment manifest",
                "",
                "```json",
                json.dumps(manifest, indent=2).rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(parts)


def _find_unicode_font() -> Path | None:
    """Prefer a TTF that covers Latin + Cyrillic (pohuy, etc.)."""
    candidates = [
        Path(__file__).resolve().parent / "assets" / "DejaVuSans.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def build_pdf(
    *,
    project: str,
    provider: str,
    model_id: str,
    location: str,
    temperature: float,
    user_message: str,
    system_prompt: str,
    model_output: str,
    manifest: dict[str, Any] | None = None,
) -> bytes:
    from fpdf import FPDF

    font_path = _find_unicode_font()
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.set_margins(16, 16, 16)

    if font_path is not None:
        pdf.add_font("ExportFont", fname=str(font_path))
        pdf.add_font("ExportFont", style="B", fname=str(font_path))
        font_name = "ExportFont"
        use_bold = True
    else:
        font_name = "Helvetica"
        use_bold = True

    def heading(text: str, size: int = 14) -> None:
        pdf.set_font(font_name, "B" if use_bold else "", size)
        pdf.multi_cell(0, 8, text)
        pdf.ln(2)

    def body(text: str, size: int = 10) -> None:
        pdf.set_font(font_name, size=size)
        safe = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not safe.strip():
            safe = "(empty)"
        pdf.multi_cell(0, 5, safe)
        pdf.ln(3)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    heading("Persona Composer — run export", 16)
    body(f"Exported {ts}", 9)

    heading("Model")
    body(
        f"Provider: {provider}\n"
        f"Model: {model_id}\n"
        f"Location: {location}\n"
        f"Project: {project}\n"
        f"Temperature: {temperature}"
    )

    heading("User message")
    body(user_message)

    heading("Composed system prompt")
    body(system_prompt, size=8)

    heading("Model output")
    body(model_output)

    if manifest is not None:
        heading("Experiment manifest")
        body(json.dumps(manifest, indent=2), size=7)

    if font_path is None:
        pdf.set_font("Helvetica", size=8)
        pdf.multi_cell(
            0,
            4,
            "Note: Unicode font not found; non-Latin glyphs may be missing. "
            "Place DejaVuSans.ttf in playground/assets/ for full coverage.",
        )

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def default_basename() -> str:
    return datetime.now(timezone.utc).strftime("persona_run_%Y%m%d_%H%M%S")
