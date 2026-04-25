"""
Core conversion entry point.

Wraps preprocess, Pandoc invocation, and postprocess into a single
operation on one file.  The CLI in `convert_lagda.py` builds on this.

`convert_file` is the per-file primitive.  `convert_tree` is a thin
wrapper for whole-tree migration that handles cross-reference label-map
construction in a two-pass fashion.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .macros import MacroTable
from .postprocess import build_label_map, postprocess
from .preprocess import preprocess

__all__ = ["ConversionError", "convert_file", "convert_tree"]

logger = logging.getLogger(__name__)


class ConversionError(RuntimeError):
    """Raised when conversion fails for a specific file."""

    def __init__(self, source: Path, stage: str, detail: str):
        super().__init__(
            f"conversion of {source} failed at {stage}: {detail}"
        )
        self.source = source
        self.stage = stage
        self.detail = detail


# Default Lua filters bundled with the package.
_BUNDLED_FILTERS_DIR = Path(__file__).parent / "filters"
_DEFAULT_FILTER = _BUNDLED_FILTERS_DIR / "agda-filter.lua"
_CROSSREFS_FILTER = _BUNDLED_FILTERS_DIR / "cross-refs.lua"


@dataclass(frozen=True)
class _ConversionOptions:
    """Internal bundle of conversion options for a single file."""
    macros: MacroTable
    enable_cross_refs: bool
    enable_theorem_envs: bool
    enable_figure_envs: bool
    extra_lua_filters: tuple[Path, ...]
    pandoc: str  # the executable name, configurable for testing


def convert_file(
    input_path: Path,
    output_path: Path,
    *,
    macros: MacroTable | None = None,
    enable_cross_refs: bool = False,
    enable_theorem_envs: bool = False,
    enable_figure_envs: bool = False,
    label_map: Mapping[str, Mapping[str, str]] | None = None,
    extra_lua_filters: Iterable[Path] = (),
    pandoc: str = "pandoc",
    keep_temp: bool = False,
) -> None:
    """Convert one .lagda file to .lagda.md.

    Args:
        input_path: Path to the .lagda source.
        output_path: Path where the .lagda.md result is written.  Parent
            directories are created if they don't exist.
        macros: Optional macro table.  Defaults to the package's default table.
        enable_cross_refs: If True, resolve \\Cref / \\cref using label_map.
        enable_theorem_envs: If True, restore theorem/lemma/claim placeholders.
        enable_figure_envs: If True, restore figure placeholders.
        label_map: Required when enable_cross_refs=True.  See `build_label_map`.
        extra_lua_filters: Additional Lua filters layered on top of the
            package defaults.  Used for project-specific extensions.
        pandoc: Name of the Pandoc executable.  Override for testing.
        keep_temp: If True, the temp directory is preserved (useful for
            debugging Pandoc output).  Otherwise it is deleted.

    Raises:
        ConversionError: If any stage of the pipeline fails.
        FileNotFoundError: If `input_path` doesn't exist.
        ValueError: If enable_cross_refs=True but label_map=None.
    """
    if macros is None:
        macros = MacroTable.default()

    if not input_path.exists():
        raise FileNotFoundError(f"input file does not exist: {input_path}")
    if enable_cross_refs and label_map is None:
        raise ValueError(
            "enable_cross_refs=True requires a label_map; "
            "use lagda_md.postprocess.build_label_map to construct one"
        )

    options = _ConversionOptions(
        macros=macros,
        enable_cross_refs=enable_cross_refs,
        enable_theorem_envs=enable_theorem_envs,
        enable_figure_envs=enable_figure_envs,
        extra_lua_filters=tuple(extra_lua_filters),
        pandoc=pandoc,
    )

    temp_dir = Path(tempfile.mkdtemp(prefix="lagda_md_"))
    try:
        _convert_one(input_path, output_path, options, label_map, temp_dir)
    finally:
        if not keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            logger.info("kept temp dir for inspection: %s", temp_dir)


def convert_tree(
    inputs: Iterable[Path],
    *,
    in_root: Path,
    out_root: Path,
    macros: MacroTable | None = None,
    enable_cross_refs: bool = False,
    enable_theorem_envs: bool = False,
    enable_figure_envs: bool = False,
    extra_lua_filters: Iterable[Path] = (),
    pandoc: str = "pandoc",
    keep_temp: bool = False,
) -> tuple[list[Path], list[tuple[Path, Exception]]]:
    """Convert a tree of .lagda files into a parallel tree of .lagda.md files.

    For projects using cross-references, this is the recommended entry
    point: it does a first pass over every input to build the global
    label map, then a second pass that runs each file's full pipeline
    with that map in scope.  For projects without cross-references, only
    the second pass is meaningful and the label map remains empty.

    Args:
        inputs: Iterable of input .lagda paths.
        in_root: The directory under which input paths live.  Used to
            compute output paths and label map keys.
        out_root: The directory under which output paths are written.
            Mirrors the input tree.
        Other args: forwarded to `convert_file`.

    Returns:
        A tuple `(succeeded, failed)`.  `succeeded` is the list of output
        paths written.  `failed` is a list of (input_path, exception) pairs.
    """
    if macros is None:
        macros = MacroTable.default()

    inputs = list(inputs)

    # First pass for cross-refs: preprocess every file, collect outputs.
    label_map: dict[str, dict[str, str]] = {}
    if enable_cross_refs:
        logger.info("first pass: building cross-reference label map")
        preprocessed: dict[Path, str] = {}
        for src in inputs:
            try:
                content = src.read_text(encoding="utf-8")
                pre, _blocks = preprocess(
                    content,
                    macros=macros,
                    enable_cross_refs=True,
                    enable_theorem_envs=enable_theorem_envs,
                    enable_figure_envs=enable_figure_envs,
                )
                preprocessed[src] = pre
            except Exception as e:
                logger.warning("preprocess failed for %s: %s", src, e)
        label_map = build_label_map(preprocessed, source_root=in_root)
        logger.info("collected %d label entries", len(label_map))

    # Second pass: per-file conversion using the (possibly empty) label map.
    succeeded: list[Path] = []
    failed: list[tuple[Path, Exception]] = []
    for src in inputs:
        try:
            relative = src.relative_to(in_root)
            dst = out_root / relative.with_suffix("").with_suffix(".lagda.md")
            convert_file(
                src,
                dst,
                macros=macros,
                enable_cross_refs=enable_cross_refs,
                enable_theorem_envs=enable_theorem_envs,
                enable_figure_envs=enable_figure_envs,
                label_map=label_map if enable_cross_refs else None,
                extra_lua_filters=extra_lua_filters,
                pandoc=pandoc,
                keep_temp=keep_temp,
            )
            succeeded.append(dst)
        except Exception as e:
            failed.append((src, e))
            logger.warning("conversion failed for %s: %s", src, e)

    return succeeded, failed


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _convert_one(
    input_path: Path,
    output_path: Path,
    options: _ConversionOptions,
    label_map: Mapping[str, Mapping[str, str]] | None,
    temp_dir: Path,
) -> None:
    """The four-stage pipeline for one file."""
    try:
        content = input_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConversionError(input_path, "read", str(e)) from e

    # Stage 1: preprocess.
    try:
        intermediate_text, code_blocks = preprocess(
            content,
            macros=options.macros,
            enable_cross_refs=options.enable_cross_refs,
            enable_theorem_envs=options.enable_theorem_envs,
            enable_figure_envs=options.enable_figure_envs,
        )
    except Exception as e:
        raise ConversionError(input_path, "preprocess", str(e)) from e

    temp_input = temp_dir / "preprocessed.tex"
    temp_output = temp_dir / "intermediate.md"
    try:
        temp_input.write_text(intermediate_text, encoding="utf-8")
    except OSError as e:
        raise ConversionError(input_path, "write-temp", str(e)) from e

    # Stage 2: Pandoc + Lua filter(s).
    filters = [_DEFAULT_FILTER]
    if options.enable_cross_refs:
        filters.append(_CROSSREFS_FILTER)
    filters.extend(options.extra_lua_filters)

    cmd = [options.pandoc, "-f", "latex", "-t", "gfm+attributes"]
    for f in filters:
        cmd.extend(["--lua-filter", str(f)])
    cmd.extend(["-o", str(temp_output), str(temp_input)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise ConversionError(input_path, "pandoc", f"executable not found: {options.pandoc}") from e
    if result.returncode != 0:
        raise ConversionError(
            input_path,
            "pandoc",
            f"return code {result.returncode}: {result.stderr.strip()}",
        )

    # Stage 3: postprocess.
    try:
        intermediate_md = temp_output.read_text(encoding="utf-8")
    except OSError as e:
        raise ConversionError(input_path, "read-intermediate", str(e)) from e

    try:
        final = postprocess(
            intermediate_md,
            code_blocks,
            label_map=label_map,
            enable_cross_refs=options.enable_cross_refs,
            enable_theorem_envs=options.enable_theorem_envs,
            enable_figure_envs=options.enable_figure_envs,
        )
    except Exception as e:
        raise ConversionError(input_path, "postprocess", str(e)) from e

    # Stage 4: write output.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_path.write_text(final, encoding="utf-8")
    except OSError as e:
        raise ConversionError(input_path, "write-output", str(e)) from e
