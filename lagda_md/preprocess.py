"""
LaTeX-literate Agda preprocessor.

Transforms `.lagda` content into a form ready for Pandoc's LaTeX reader,
extracting Agda code blocks into a sidecar dictionary so Pandoc never sees
them (it would re-indent the code and break Agda's layout-sensitive syntax).

The output is the partner of `lagda_md.postprocess.postprocess`; the two
together implement a four-stage pipeline:

    .lagda  →  preprocess  →  Pandoc + Lua filter  →  postprocess  →  .lagda.md

The placeholder convention (`@@CODEBLOCK_ID_n@@`, `@@AgdaTerm@@...@@`, etc.)
is documented in `lagda_md/__init__.py`.
"""
from __future__ import annotations

import re

from .macros import MacroTable

__all__ = ["preprocess"]


# Generic Agda CSS classes recognized as `\AgdaFoo{name}` and rewritten to
# AgdaTerm placeholders.  This list is the always-on baseline; projects that
# need additional classes should add custom entries to their MacroTable.
_GENERIC_AGDA_CLASSES = (
    "AgdaFunction",
    "AgdaField",
    "AgdaDatatype",
    "AgdaRecord",
    "AgdaInductiveConstructor",
    "AgdaModule",
    "AgdaPrimitive",
    "AgdaBound",
    "AgdaArgument",
)
_GENERIC_AGDA_PATTERN = re.compile(
    r"\\(" + "|".join(_GENERIC_AGDA_CLASSES) + r")\{([^}]+)\}"
)


def preprocess(
    content: str,
    macros: MacroTable | None = None,
    *,
    enable_cross_refs: bool = False,
    enable_theorem_envs: bool = False,
    enable_figure_envs: bool = False,
) -> tuple[str, dict[str, dict]]:
    """Transform LaTeX-literate Agda content into Pandoc-ready text.

    Always-on transformations:
      * Code-block extraction (\\begin{code}...\\end{code} → @@CODEBLOCK_ID_n@@).
      * Hidden code blocks (\\begin{code}[hide]...).
      * \\ab{x} → \\AgdaBound{x} shorthand expansion.
      * ~ (LaTeX non-breaking space) → ' '.
      * Generic \\Agda...{name} expansion to AgdaTerm placeholders, for the
        nine standard Agda CSS classes listed in _GENERIC_AGDA_CLASSES.
      * Custom macros from the supplied MacroTable, also rendered as
        AgdaTerm placeholders.

    Opt-in transformations (each gated by the corresponding flag and emitting
    placeholders that lagda_md.postprocess knows how to resolve):
      * enable_cross_refs   — \\Cref{...} and \\cref{...} → @@CROSS_REF@@.
      * enable_theorem_envs — theorem/lemma/claim environments.
      * enable_figure_envs  — figure environments with \\caption / \\label.

    Returns:
        (processed_content, code_blocks) where code_blocks maps placeholder IDs
        to dicts of the form {"content": str, "hidden": bool}.
    """
    if macros is None:
        macros = MacroTable.empty()

    code_blocks: dict[str, dict] = {}

    # --- Stage 1: Protect code blocks from Pandoc -------------------------
    # Hidden blocks first, so the [hide] suffix is matched before the generic
    # pattern eats the same opening tag.
    counter = [0]

    def _capture(match: re.Match, hidden: bool) -> str:
        counter[0] += 1
        body = match.group(1) or ""
        if not body.endswith("\n"):
            body += "\n"
        placeholder = f"@@CODEBLOCK_ID_{counter[0]}@@"
        code_blocks[placeholder] = {"content": body, "hidden": hidden}
        return placeholder

    processed = re.sub(
        r"\\begin\{code\}\s*\[hide\](.*?)\\end\{code\}",
        lambda m: _capture(m, hidden=True),
        content,
        flags=re.DOTALL,
    )
    processed = re.sub(
        r"\\begin\{code\}(.*?)\\end\{code\}",
        lambda m: _capture(m, hidden=False),
        processed,
        flags=re.DOTALL,
    )

    # --- Stage 2: Always-on text transformations --------------------------
    processed = processed.replace("~", " ")
    processed = re.sub(r"\\ab\{(.*?)\}", r"\\AgdaBound{\1}", processed)

    # --- Stage 3: Project-supplied macros ---------------------------------
    if macros.entries:
        processed = _expand_custom_macros(processed, macros)

    # --- Stage 4: Generic Agda CSS-class macros ---------------------------
    processed = _GENERIC_AGDA_PATTERN.sub(
        lambda m: f"\\texttt{{@@AgdaTerm@@basename={m.group(2)}@@class={m.group(1)}@@}}",
        processed,
    )

    # --- Stage 5: Opt-in transformations ----------------------------------
    if enable_cross_refs:
        processed = _process_cross_refs(processed)
    if enable_theorem_envs:
        processed = _process_theorem_envs(processed)
    if enable_figure_envs:
        processed = _process_figure_envs(processed)

    return processed, code_blocks


# ----------------------------------------------------------------------------
# Custom macro expansion
# ----------------------------------------------------------------------------
def _expand_custom_macros(content: str, macros: MacroTable) -> str:
    """Rewrite each `\\Macro{}` from the table to an AgdaTerm placeholder.

    A macro entry with empty basename uses the macro's argument as the
    basename (this is how `\\ab{x}` would behave if it were in the table
    rather than handled as a shorthand).
    """
    pattern = re.compile(
        r"\\(" + "|".join(re.escape(name) for name in macros.keys()) + r")\{([^}]*)\}"
    )

    def _replace(match: re.Match) -> str:
        name, arg = match.group(1), match.group(2)
        entry = macros[name]
        basename = entry.basename if entry.basename else arg
        return f"\\texttt{{@@AgdaTerm@@basename={basename}@@class={entry.agda_class}@@}}"

    return pattern.sub(_replace, content)


# ----------------------------------------------------------------------------
# Opt-in: cross-references
# ----------------------------------------------------------------------------
_CREF_PATTERN = re.compile(r"\\(Cref|cref)\s*\{(.*?)\}")


def _process_cross_refs(content: str) -> str:
    """Rewrite \\Cref / \\cref → @@CROSS_REF@@ placeholders for postprocess."""
    return _CREF_PATTERN.sub(
        lambda m: (
            f"@@CROSS_REF@@command={m.group(1)}"
            f"@@targets={m.group(2).replace('@@', '@ @')}@@"
        ),
        content,
    )


# ----------------------------------------------------------------------------
# Opt-in: theorem-like environments
# ----------------------------------------------------------------------------
_THEOREM_KINDS = ("theorem", "lemma", "claim")


def _process_theorem_envs(content: str) -> str:
    """Rewrite theorem/lemma/claim environments → @@..._BLOCK@@ placeholders."""
    for kind in _THEOREM_KINDS:
        pattern = re.compile(
            r"\\begin\{" + kind + r"\}(?:\[(.*?)\])?\s*(.*?)\\end\{" + kind + r"\}",
            flags=re.DOTALL,
        )
        content = pattern.sub(_make_theorem_replacer(kind), content)
    return content


def _make_theorem_replacer(kind: str):
    def _replace(match: re.Match) -> str:
        title = match.group(1) or kind.capitalize()
        body = match.group(2)
        label_match = re.search(r"\\label\{(.*?)\}", body)
        label = label_match.group(1) if label_match else ""
        body = re.sub(r"\\label\{.*?\}", "", body).strip()
        spec = (
            f"label={label}@@title={title}" if label else f"title={title}"
        )
        return f"\n@@{kind.upper()}_BLOCK@@{spec}@@\n{body}\n"
    return _replace


# ----------------------------------------------------------------------------
# Opt-in: figure environments
# ----------------------------------------------------------------------------
_FIGURE_PATTERN = re.compile(
    r"^\s*\\begin\{figure\*?\}(\[[^\]]*\])?\s*\n(.*?)\n\s*\\end\{figure\*?\}\s*$",
    flags=re.MULTILINE | re.DOTALL,
)


def _process_figure_envs(content: str) -> str:
    """Rewrite figure environments → @@FIGURE_BLOCK@@ placeholders."""
    return _FIGURE_PATTERN.sub(_replace_figure, content)


def _replace_figure(match: re.Match) -> str:
    body = match.group(2)
    caption_text = "Untitled Section"
    label_id = ""

    caption_match = re.search(r"\\caption\{(.*?)\}", body, flags=re.DOTALL)
    if caption_match:
        raw_caption = caption_match.group(1).strip()
        squashed = re.sub(r"\s+", " ", raw_caption.replace("\n", " ")).strip()
        caption_text = squashed.replace(" ", "-").replace("@@", "@ @")
        body = body.replace(caption_match.group(0), "", 1)

    label_match = re.search(r"\\label\{(.*?)\}", body)
    if label_match:
        label_id = label_match.group(1).strip().replace("@@", "@ @")
        body = body.replace(label_match.group(0), "", 1)

    body = body.strip()
    if label_id:
        marker = (
            f"\n@@FIGURE_BLOCK_TO_SUBSECTION@@"
            f"label={label_id}@@caption={caption_text}@@\n"
        )
    else:
        marker = f"\n@@UNLABELLED_FIGURE_CAPTION@@caption={caption_text}@@\n"
    return marker + body
