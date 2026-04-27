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

import re
from pathlib import Path
from typing import Iterable

from .macros import MacroTable
from .postprocess import postprocess
from .preprocess import preprocess

__all__ = ["convert_markdown"]


# Match LaTeX \href{url}{text} in prose.  Code blocks have already been
# extracted to placeholders by preprocess() before this regex runs, so
# any \href that survives is genuinely in prose.  The pattern assumes
# neither {url} nor {text} contains a literal { or } — robust enough for
# the corpora we target (FLS, agda-algebras, 1Lab).
_HREF_PATTERN = re.compile(r"\\href\{([^}]*)\}\{([^}]*)\}")


# Match the AgdaTerm placeholder that preprocess() emits for both the
# always-on generic \Agda... family and any custom-macro entries.  In
# the LaTeX pipeline these are consumed by the agda-filter.lua Pandoc
# filter; in the Markdown pipeline there is no Pandoc, so we resolve
# them here.
_AGDA_TERM_PLACEHOLDER_PATTERN = re.compile(
    r"\\texttt\{@@AgdaTerm@@basename=(.*?)@@class=(\w+)@@\}"
)


def _rewrite_href_to_markdown(content: str) -> str:
    """Rewrite LaTeX `\\href{url}{text}` in prose as Markdown `[text](url)`.

    Markdown-literate `.lagda` files in the wild often interleave LaTeX
    `\\href` calls with otherwise-Markdown prose; without this rewrite
    they would survive verbatim into the converted output.
    """
    return _HREF_PATTERN.sub(
        lambda m: f"[{m.group(2)}]({m.group(1)})",
        content,
    )


def _resolve_agda_term_placeholders(content: str) -> str:
    """Convert AgdaTerm placeholders to kramdown attribute spans.

    `\\af{Foo}` (a custom-macro invocation) or `\\AgdaFunction{Foo}` (a
    direct generic invocation) becomes `` `Foo`{.AgdaFunction} `` — the
    inline-code-with-attribute-class syntax that kramdown (Jekyll's
    default Markdown processor) and Pandoc both recognize.  Pair with
    a `custom.css` providing per-class colors; see the formal-ledger-
    specifications project for the canonical reference.
    """
    def _unescape(s: str) -> str:
        # Reverse the @@ → @ @ escape that preprocess() applies to
        # placeholder payloads, so literal @@ in user content survives.
        return s.replace("@ @", "@@")

    def _replace(match: re.Match) -> str:
        basename = _unescape(match.group(1))
        agda_class = match.group(2)
        return f"`{basename}`{{.{agda_class}}}"

    return _AGDA_TERM_PLACEHOLDER_PATTERN.sub(_replace, content)


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

    # Stage 2: Resolve placeholders and rewrite LaTeX-prose-isms that
    # have native Markdown equivalents.  This must happen BEFORE
    # postprocess() restores code blocks: the rewrites apply to prose
    # only, and code blocks are still placeholdered at this point.
    intermediate = _rewrite_href_to_markdown(intermediate)
    intermediate = _resolve_agda_term_placeholders(intermediate)

    # Stage 3: Restore code blocks (the only postprocess step that fires
    # for Markdown-literate input; cross-ref / theorem / figure resolvers
    # are all gated by their respective flags).
    final = postprocess(
        intermediate,
        code_blocks,
        enable_cross_refs=False,
        enable_theorem_envs=False,
        enable_figure_envs=False,
    )

    # Stage 4: Write output.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(final, encoding="utf-8")
