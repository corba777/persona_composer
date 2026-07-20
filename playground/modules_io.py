"""Helpers to materialize persona modules from paste / upload / library."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from persona_composer import compose
from persona_composer.models import SkeletonConfig
from persona_composer.parse import parse_module, split_frontmatter

SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass
class ComposeBundle:
    prompt_xml: str
    manifest_json: str
    warnings: list[str]
    work_dir: Path


def library_root() -> Path:
    """Default module library shipped with tests (demo content)."""
    return (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "modules"
    )


def list_modules_by_type(root: Path, type_name: str) -> list[tuple[str, Path]]:
    """Return (display_name, path) for modules of a given type under root."""
    found: list[tuple[str, Path]] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
            fm, _ = split_frontmatter(text)
        except Exception:
            continue
        if fm.get("type") != type_name:
            continue
        name = str(fm.get("name") or path.stem)
        found.append((f"{name} ({path.relative_to(root)})", path))
    return found


def _safe(name: str) -> str:
    cleaned = SAFE_NAME.sub("_", name.strip()) or "Module"
    return cleaned[:64]


def write_identity_md(work_dir: Path, *, name: str, body: str) -> Path:
    path = work_dir / f"identity_{_safe(name)}.md"
    path.write_text(
        f"---\ntype: identity\nname: {_safe(name)}\n---\n{body.strip()}\n",
        encoding="utf-8",
    )
    return path


def write_speech_md(work_dir: Path, *, name: str, body: str) -> Path:
    path = work_dir / f"speech_{_safe(name)}.md"
    path.write_text(
        f"---\ntype: speech\nname: {_safe(name)}\n---\n{body.strip()}\n",
        encoding="utf-8",
    )
    return path


def write_output_rules_md(work_dir: Path, *, name: str, body: str) -> Path:
    path = work_dir / f"output_rules_{_safe(name)}.md"
    path.write_text(
        f"---\ntype: output_rules\nname: {_safe(name)}\n---\n{body.strip()}\n",
        encoding="utf-8",
    )
    return path


def save_upload(work_dir: Path, *, filename: str, data: bytes) -> Path:
    dest = work_dir / Path(filename).name
    dest.write_bytes(data)
    # Ensure it parses as a module (has frontmatter); if not, wrap later
    return dest


def ensure_typed_module(
    path: Path,
    *,
    expected_type: str,
    fallback_name: str,
    work_dir: Path,
) -> Path:
    """
    If uploaded file already has matching frontmatter, use as-is.
    If it has no frontmatter, wrap body as the expected type.
    """
    text = path.read_text(encoding="utf-8")
    try:
        fm, body = split_frontmatter(text)
        if fm.get("type") == expected_type:
            return path
        # Wrong type — re-wrap body
        content_body = body
        name = str(fm.get("name") or fallback_name)
    except Exception:
        content_body = text
        name = fallback_name

    if expected_type == "identity":
        return write_identity_md(work_dir, name=name, body=content_body)
    if expected_type == "speech":
        return write_speech_md(work_dir, name=name, body=content_body)
    if expected_type == "output_rules":
        return write_output_rules_md(work_dir, name=name, body=content_body)
    raise ValueError(f"unsupported wrap type: {expected_type}")


def compose_persona(
    *,
    identity_path: Path,
    extra_paths: list[Path],
    module_root: Path | None,
    output_rules: str | None = None,
) -> ComposeBundle:
    work_dir = Path(tempfile.mkdtemp(prefix="persona_play_"))
    # Keep paths as given; composer resolves vendor sources via module_root
    skeleton = None
    if output_rules:
        skeleton = SkeletonConfig(output_rules=output_rules)

    result = compose(
        identity_path,
        extra_paths,
        module_root=module_root,
        library_root=module_root,
        skeleton=skeleton,
    )
    return ComposeBundle(
        prompt_xml=result.prompt_xml,
        manifest_json=result.manifest_json(),
        warnings=list(result.manifest.warnings),
        work_dir=work_dir,
    )


def peek_module_name(path: Path) -> str:
    try:
        mod = parse_module(path)
        return mod.name
    except Exception:
        return path.stem
