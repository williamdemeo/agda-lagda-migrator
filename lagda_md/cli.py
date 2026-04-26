"""
Command-line interface for lagda_md.

Invoked via `python3 -m lagda_md ...` or directly as `convert_lagda.py ...`.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .core import convert_file, convert_tree
from .macros import MacroTable

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate conversion mode.

    Return values:
        0: success.
        1: argument-validation failure (e.g., --in-tree without --out-tree).
        2: conversion failure (e.g., Pandoc returned a nonzero exit code).

    `argparse` parser errors (unknown flags, invalid values) raise
    `SystemExit(2)` per the standard library convention, bypassing this
    return-code path; callers wishing to recover from parse errors must
    catch `SystemExit` explicitly.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    macros = (
        MacroTable.from_json(args.macros) if args.macros else MacroTable.default()
    )
    extra_filters = [Path(f) for f in args.extra_filter or ()]

    if args.in_tree:
        if args.check:
            print(
                "error: --check is currently single-file-only; "
                "use --check on individual files instead of with --in-tree",
                file=sys.stderr,
            )
            return 1
        if args.out_tree is None:
            print("error: --in-tree requires --out-tree", file=sys.stderr)
            return 1
        return _run_tree_mode(args, macros, extra_filters)
    if args.input is None:
        print("error: INPUT is required unless --in-tree is given", file=sys.stderr)
        return 1
    if args.check:
        return _run_check_mode(args, macros, extra_filters)
    if args.output is None:
        print("error: OUTPUT is required for single-file conversion", file=sys.stderr)
        return 1
    return _run_single_mode(args, macros, extra_filters)


# ---------------------------------------------------------------------------
# Mode dispatchers
# ---------------------------------------------------------------------------
def _run_single_mode(
    args: argparse.Namespace, macros: MacroTable, extra_filters: list[Path]
) -> int:
    """Single-file conversion."""
    try:
        convert_file(
            args.input,
            args.output,
            input_format=args.input_format,
            macros=macros,
            enable_cross_refs=args.enable_cross_refs,
            enable_theorem_envs=args.enable_theorem_envs,
            enable_figure_envs=args.enable_figure_envs,
            label_map=None,  # cross-refs across files not meaningful in single mode
            extra_lua_filters=extra_filters,
            pandoc=args.pandoc,
            keep_temp=args.keep_temp,
        )
    except ValueError as e:
        # enable_cross_refs without a label map; fall through with a hint.
        print(f"error: {e}", file=sys.stderr)
        print(
            "hint: cross-references can only be resolved across a tree; "
            "use --in-tree mode for a multi-file project",
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print(f"error: conversion failed: {e}", file=sys.stderr)
        return 2

    print(f"wrote {args.output}")
    return 0


def _run_tree_mode(
    args: argparse.Namespace, macros: MacroTable, extra_filters: list[Path]
) -> int:
    """Whole-tree conversion."""
    in_root: Path = args.in_tree
    out_root: Path = args.out_tree

    if not in_root.is_dir():
        print(f"error: {in_root} is not a directory", file=sys.stderr)
        return 1

    inputs = sorted(in_root.rglob("*.lagda"))
    if not inputs:
        print(f"error: no .lagda files found under {in_root}", file=sys.stderr)
        return 1

    print(f"found {len(inputs)} .lagda files under {in_root}")

    succeeded, failed = convert_tree(
        inputs,
        in_root=in_root,
        out_root=out_root,
        input_format=args.input_format,
        macros=macros,
        enable_cross_refs=args.enable_cross_refs,
        enable_theorem_envs=args.enable_theorem_envs,
        enable_figure_envs=args.enable_figure_envs,
        extra_lua_filters=extra_filters,
        pandoc=args.pandoc,
        keep_temp=args.keep_temp,
    )

    print(f"converted {len(succeeded)} of {len(inputs)} files")
    if failed:
        print(f"failures ({len(failed)}):", file=sys.stderr)
        for src, exc in failed:
            print(f"  {src}: {exc}", file=sys.stderr)
        return 2
    return 0


def _run_check_mode(
    args: argparse.Namespace, macros: MacroTable, extra_filters: list[Path]
) -> int:
    """Validate that conversion would succeed, without writing output."""
    import tempfile

    # Use a throwaway output path under a temp dir.
    with tempfile.TemporaryDirectory() as tmp:
        scratch_output = Path(tmp) / "scratch.lagda.md"
        try:
            convert_file(
                args.input,
                scratch_output,
                input_format=args.input_format,
                macros=macros,
                enable_cross_refs=False,
                enable_theorem_envs=args.enable_theorem_envs,
                enable_figure_envs=args.enable_figure_envs,
                label_map=None,
                extra_lua_filters=extra_filters,
                pandoc=args.pandoc,
                keep_temp=False,
            )
        except Exception as e:
            print(f"check failed: {e}", file=sys.stderr)
            return 2

    print(f"check passed: {args.input} would convert successfully")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="convert_lagda",
        description=(
            "Convert LaTeX-literate Agda (.lagda) to Markdown-literate Agda "
            "(.lagda.md), via a four-stage pipeline of preprocessing, "
            "Pandoc, a Lua filter, and postprocessing."
        ),
    )

    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Input .lagda file (required for single-file or --check mode)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="Output .lagda.md file (required for single-file mode)",
    )

    tree = parser.add_argument_group("tree mode")
    tree.add_argument(
        "--in-tree",
        type=Path,
        metavar="DIR",
        help="Convert every .lagda under DIR (recursive).",
    )
    tree.add_argument(
        "--out-tree",
        type=Path,
        metavar="DIR",
        help="Write outputs to DIR, mirroring the input directory structure.",
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Run conversion without writing output; exit 0 on success.",
    )

    formats = parser.add_argument_group("input format")
    formats.add_argument(
        "--input-format",
        choices=["latex", "markdown"],
        default="latex",
        metavar="FORMAT",
        help=(
            "Input file flavor.  'latex' (default) treats the .lagda "
            "file as LaTeX-literate Agda and runs through Pandoc.  "
            "'markdown' treats it as Markdown-literate Agda with "
            "\\begin{code} fences and skips Pandoc."
        ),
    )

    customization = parser.add_argument_group("customization")
    customization.add_argument(
        "--macros",
        type=Path,
        metavar="FILE",
        help="Path to a JSON macro table.  Default: the package-bundled default.",
    )
    customization.add_argument(
        "--extra-filter",
        action="append",
        metavar="FILE",
        help="Additional Pandoc Lua filter to layer on the defaults.  Repeat for multiple.",
    )

    optins = parser.add_argument_group("opt-in transformations")
    optins.add_argument(
        "--enable-cross-refs",
        action="store_true",
        help=r"Resolve \Cref / \cref / \label / \caption (loads cross-refs.lua filter).",
    )
    optins.add_argument(
        "--enable-theorem-envs",
        action="store_true",
        help=r"Restore \begin{theorem}, \begin{lemma}, \begin{claim} environments.",
    )
    optins.add_argument(
        "--enable-figure-envs",
        action="store_true",
        help=r"Restore \begin{figure} environments as Markdown subsections.",
    )

    debug = parser.add_argument_group("debugging")
    debug.add_argument(
        "--pandoc",
        default="pandoc",
        metavar="EXEC",
        help="Pandoc executable name (default: pandoc).",
    )
    debug.add_argument(
        "--keep-temp",
        action="store_true",
        help="Preserve the temporary working directory after conversion.",
    )
    debug.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging.",
    )

    return parser
