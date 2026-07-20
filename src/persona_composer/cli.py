"""CLI for persona-compose."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from persona_composer.compose import compose, compose_from_manifest
from persona_composer.errors import CompositionError
from persona_composer.models import SkeletonConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="persona-compose",
        description="Compose an agent system prompt from Markdown modules.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compose", help="Compose from module paths")
    c.add_argument(
        "--identity",
        required=True,
        type=Path,
        help="Path to the identity module (.md)",
    )
    c.add_argument(
        "modules",
        nargs="*",
        type=Path,
        help="Additional module paths",
    )
    c.add_argument(
        "--module-root",
        type=Path,
        default=None,
        help="Root for resolving vendor source: paths",
    )
    c.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write prompt XML to this path (default: stdout)",
    )
    c.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Write manifest JSON to this path",
    )
    c.add_argument(
        "--output-rules",
        type=str,
        default=None,
        help="Override skeleton output_rules text",
    )

    r = sub.add_parser("recompose", help="Compose from a saved manifest")
    r.add_argument("manifest_in", type=Path, help="Input manifest JSON")
    r.add_argument("--module-root", type=Path, default=None)
    r.add_argument("--out", type=Path, default=None)
    r.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Write refreshed manifest JSON",
    )
    r.add_argument("--no-verify-hashes", action="store_true")
    r.add_argument("--output-rules", type=str, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    skeleton = None
    if getattr(args, "output_rules", None):
        skeleton = SkeletonConfig(output_rules=args.output_rules)

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


if __name__ == "__main__":
    raise SystemExit(main())
