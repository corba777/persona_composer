"""CLI for persona-compose."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from persona_composer.compose import compose, compose_from_manifest
from persona_composer.decompose import decompose
from persona_composer.errors import CompositionError
from persona_composer.models import SkeletonConfig
from persona_composer.rewriter import apply_rewriters_from_manifest, apply_rewriters_from_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="persona-compose",
        description="Compose an agent system prompt from Markdown modules.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compose", help="Compose from module paths")
    c.add_argument("--identity", required=True, type=Path)
    c.add_argument("modules", nargs="*", type=Path)
    c.add_argument("--module-root", type=Path, default=None)
    c.add_argument("--out", type=Path, default=None)
    c.add_argument("--manifest", type=Path, default=None)
    c.add_argument("--output-rules", type=str, default=None)

    r = sub.add_parser("recompose", help="Compose from a saved manifest")
    r.add_argument("manifest_in", type=Path)
    r.add_argument("--module-root", type=Path, default=None)
    r.add_argument("--out", type=Path, default=None)
    r.add_argument("--manifest", type=Path, default=None)
    r.add_argument("--no-verify-hashes", action="store_true")
    r.add_argument("--output-rules", type=str, default=None)

    d = sub.add_parser(
        "decompose",
        help="Suggest trait/speech extractions (needs --llm-response JSON; no LLM in-core)",
    )
    d.add_argument("source", type=Path, help="identity.md, skill, or raw text file")
    d.add_argument(
        "--llm-response",
        type=Path,
        required=True,
        help="Path to LLM JSON response (composer never calls a model)",
    )
    d.add_argument(
        "--out-dir",
        type=Path,
        default=Path("drafts"),
        help="Directory for draft modules (default: ./drafts)",
    )
    d.add_argument("--kind", choices=["identity", "skill", "raw"], default=None)
    d.add_argument("--source-relpath", type=str, default=None, help="For adaptation:extracted source:")
    d.add_argument("--origin", type=str, default=None)
    d.add_argument("--no-write", action="store_true", help="Parse only; print JSON")
    d.add_argument("--prompt-out", type=Path, default=None, help="Also write the decompose prompt")

    w = sub.add_parser(
        "rewrite",
        help="Apply speech.mode=rewriter stack to text (needs --via echo|file stub or external)",
    )
    w.add_argument(
        "--text",
        type=str,
        default=None,
        help="Input text (else read --text-file or stdin)",
    )
    w.add_argument("--text-file", type=Path, default=None)
    w.add_argument(
        "--modules",
        nargs="*",
        type=Path,
        default=[],
        help="Rewriter speech module paths",
    )
    w.add_argument(
        "--from-manifest",
        type=Path,
        default=None,
        help="Use rewriter_stack from a compose manifest",
    )
    w.add_argument("--module-root", type=Path, default=None)
    w.add_argument(
        "--stub",
        action="store_true",
        help="Deterministic stub LLM: wrap text with [rewritten by NAME]",
    )
    w.add_argument("--out", type=Path, default=None)

    return parser


def _compose_skeleton(args: argparse.Namespace) -> SkeletonConfig | None:
    if getattr(args, "output_rules", None):
        return SkeletonConfig(output_rules=args.output_rules)
    return None


def _run_compose_commands(args: argparse.Namespace) -> int:
    skeleton = _compose_skeleton(args)
    try:
        if args.command == "compose":
            result = compose(
                args.identity,
                args.modules,
                skeleton=skeleton,
                module_root=args.module_root,
                library_root=args.module_root,
            )
        else:
            result = compose_from_manifest(
                args.manifest_in,
                skeleton=skeleton,
                module_root=args.module_root,
                library_root=args.module_root,
                verify_hashes=not args.no_verify_hashes,
            )
    except CompositionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.out:
        args.out.write_text(result.prompt_xml, encoding="utf-8")
    else:
        sys.stdout.write(result.prompt_xml)

    if args.manifest:
        args.manifest.write_text(result.manifest_json(), encoding="utf-8")

    for warning in result.manifest.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _run_decompose(args: argparse.Namespace) -> int:
    from persona_composer.decompose import build_decompose_prompt, load_decompose_source

    try:
        if args.prompt_out:
            text, kind, name = load_decompose_source(args.source)
            prompt = build_decompose_prompt(
                source_text=text,
                source_kind=args.kind or kind,
                source_name=name,
                provenance=str(args.source),
            )
            args.prompt_out.write_text(prompt, encoding="utf-8")

        response = args.llm_response.read_text(encoding="utf-8")
        result = decompose(
            args.source,
            llm_response=response,
            out_dir=None if args.no_write else args.out_dir,
            source_kind=args.kind,
            source_relpath=args.source_relpath,
            origin=args.origin,
            write_drafts=not args.no_write,
        )
    except CompositionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    if result.draft_paths:
        print(f"wrote {len(result.draft_paths)} draft file(s) under {args.out_dir}", file=sys.stderr)
    return 0


def _run_rewrite(args: argparse.Namespace) -> int:
    if args.text is not None:
        text = args.text
    elif args.text_file is not None:
        text = args.text_file.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    if not args.stub:
        print(
            "error: rewrite CLI requires --stub for now "
            "(library API accepts any llm_call callable)",
            file=sys.stderr,
        )
        return 1

    def stub(system: str, user: str) -> str:
        # Pull style name from first line of system if present
        name = system.split("\n", 1)[0][:40]
        # Extract original from template
        body = user
        if "---\n" in user:
            parts = user.split("---\n")
            if len(parts) >= 2:
                body = parts[1].rsplit("\n---", 1)[0]
        return f"[rewritten]\n{body.strip()}\n[/rewritten:{name.strip()}]"

    try:
        if args.from_manifest:
            result = apply_rewriters_from_manifest(
                text,
                args.from_manifest,
                llm_call=stub,
                module_root=args.module_root,
            )
        elif args.modules:
            result = apply_rewriters_from_paths(
                text,
                args.modules,
                llm_call=stub,
                module_root=args.module_root,
            )
        else:
            print("error: provide --modules and/or --from-manifest", file=sys.stderr)
            return 1
    except CompositionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.out:
        args.out.write_text(result.text, encoding="utf-8")
    else:
        sys.stdout.write(result.text)
        if not result.text.endswith("\n"):
            sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in ("compose", "recompose"):
        return _run_compose_commands(args)
    if args.command == "decompose":
        return _run_decompose(args)
    if args.command == "rewrite":
        return _run_rewrite(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
