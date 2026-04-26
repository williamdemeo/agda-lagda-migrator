"""
Markdown-literate Agda conversion pipeline.

Handles `.lagda` files that are authored as Markdown prose with
`\\begin{code}...\\end{code}` fences for Agda code (rather than as LaTeX
prose, which is what the four-stage Pandoc pipeline in `lagda_md.core`
handles).

This pipeline is structurally simpler than the LaTeX one because the
prose doesn't need conversion — it's already in the target format.
The work reduces to:

    1. Extract `\\begin{code}...\\end{code}` blocks (reusing the
       always-on machinery in `lagda_md.preprocess`).
    2. Expand custom and generic Agda macros in the prose.
    3. Restore code blocks as fenced ```` ```agda ```` blocks (reusing
       the always-on machinery in `lagda_md.postprocess`).

YAML front matter, Markdown headings, reference-style links, Jekyll
directives, and other Markdown-native constructs survive unchanged.

The opt-in flags from the LaTeX pipeline (cross-refs, theorem envs,
figure envs) don't apply here: Markdown-literate authors use Markdown's
native mechanisms (reference-style links, custom CSS classes, headings)
for those constructs and don't need our placeholder protocol.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .macros import MacroTable
from .postprocess import postprocess
from .preprocess import preprocess

__all__ = ["convert_markdown"]


def convert_markdown(
    input_path: Path,
    output_path: Path,
    *,
    macros: MacroTable | None = None,
) -> None:
    """Convert one Markdown-literate .lagda file to .lagda.md.

    Args:
        input_path: Path to the .lagda source.
        output_path: Path where the .lagda.md result is written.
            Parent directories are created if absent.
        macros: Optional macro table.  Defaults to the package's
            default table.  Pass `MacroTable.empty()` to disable
            *custom* macro expansion; the built-in preprocessor
            transformations (`\\ab` shorthand, generic `\\Agda...`
            class expansion, `~` normalization) always apply.

    Raises:
        FileNotFoundError: If `input_path` doesn't exist.
        OSError: If reading input or writing output fails.
    """
    if macros is None:
        macros = MacroTable.default()

    if not input_path.exists():
        raise FileNotFoundError(f"input file does not exist: {input_path}")

    content = input_path.read_text(encoding="utf-8")

    # Stage 1: Extract code blocks and expand macros.  Opt-in flags are
    # all False — none of them are meaningful for Markdown-literate input.
    # Tilde normalization is also disabled: in Markdown-literate prose,
    # ~ has its own meanings (strikethrough ~~text~~, YAML null `key: ~`).
    intermediate, code_blocks = preprocess(
        content,
        macros=macros,
        normalize_tildes=False,
        enable_cross_refs=False,
        enable_theorem_envs=False,
        enable_figure_envs=False,
    )

    # Stage 2: Restore code blocks (the only postprocess step that fires
    # for Markdown-literate input; cross-ref / theorem / figure resolvers
    # are all gated by their respective flags).
    final = postprocess(
        intermediate,
        code_blocks,
        enable_cross_refs=False,
        enable_theorem_envs=False,
        enable_figure_envs=False,
    )

    # Stage 3: Write output.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(final, encoding="utf-8")
