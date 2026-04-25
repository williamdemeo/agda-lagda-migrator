"""
agda-lagda-migrator: convert LaTeX-literate Agda to Markdown-literate Agda.

The four-stage pipeline:

    .lagda  -->  preprocess  -->  Pandoc + Lua filter  -->  postprocess  -->  .lagda.md

The boundary between the four stages is mediated by `@@`-delimited
placeholders, which let stages pass information through Pandoc without
Pandoc misinterpreting it.  The placeholder convention:

    @@CODEBLOCK_ID_n@@
        Stand-in for an Agda code block.  Inserted by preprocess, restored
        as a fenced code block by postprocess.  Always-on.

    \\texttt{@@AgdaTerm@@basename=NAME@@class=CLASS@@}
        Stand-in for an Agda identifier (function, datatype, etc.) appearing
        in prose.  Inserted by preprocess, rendered with appropriate CSS
        class by the agda-filter.lua Pandoc filter.  Always-on.

    @@CROSS_REF@@command=NAME@@targets=KEY,KEY,...@@
        Stand-in for a \\Cref or \\cref.  Inserted by preprocess when
        enable_cross_refs=True, resolved to a Markdown link by postprocess
        against a label map.

    @@THEOREM_BLOCK@@... / @@LEMMA_BLOCK@@... / @@CLAIM_BLOCK@@...
        Stand-in for a theorem/lemma/claim environment.  Inserted by
        preprocess when enable_theorem_envs=True, restored as a styled block
        by postprocess.

    @@FIGURE_BLOCK_TO_SUBSECTION@@... / @@UNLABELLED_FIGURE_CAPTION@@...
        Stand-in for a figure environment.  Inserted by preprocess when
        enable_figure_envs=True, restored as a Markdown subsection by
        postprocess.

The `@@` literal in input content is escaped to `@ @` (with a space) by the
preprocess stage and unescaped by the postprocess stage, so user content can
contain `@@` safely.
"""

from .macros import MacroEntry, MacroTable
from .preprocess import preprocess
from .postprocess import postprocess, build_label_map

__all__ = ["MacroEntry", "MacroTable", "preprocess", "postprocess", "build_label_map"]
