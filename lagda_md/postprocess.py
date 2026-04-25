"""
Postprocessor for the literate-Agda conversion pipeline.

Takes Pandoc's GFM output (with the placeholder convention from
`lagda_md.preprocess`) and produces the final `.lagda.md` content.
The placeholder convention is documented in `lagda_md/__init__.py`.

Always-on transformations:
    * Code-block re-insertion: @@CODEBLOCK_ID_n@@ → fenced ```agda block.

Opt-in transformations (each gated by a flag matching the corresponding
flag passed to `lagda_md.preprocess.preprocess`):
    * enable_cross_refs   — resolve @@CROSS_REF@@ markers via a label map.
    * enable_theorem_envs — restore theorem/lemma/claim blocks.
    * enable_figure_envs  — restore figure blocks as Markdown subsections.

The label-map argument to `postprocess` is required when
`enable_cross_refs=True`.  When converting a single file with cross-refs
enabled, the user is responsible for supplying the map; the
`build_label_map` helper builds one from a list of preprocessor outputs.
"""
from __future__ import annotations

import logging
import re
from functools import reduce
from pathlib import Path
from typing import Callable, Mapping

__all__ = ["postprocess", "build_label_map"]

logger = logging.getLogger(__name__)

def _unescape_from_placeholder(text: str) -> str:
    """Reverse the @@ → @ @ escape applied by lagda_md.preprocess."""
    return text.replace("@ @", "@@")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def postprocess(
    intermediate_md: str,
    code_blocks: Mapping[str, dict],
    *,
    label_map: Mapping[str, Mapping[str, str]] | None = None,
    enable_cross_refs: bool = False,
    enable_theorem_envs: bool = False,
    enable_figure_envs: bool = False,
) -> str:
    """Apply postprocessing to Pandoc's intermediate Markdown output.

    Args:
        intermediate_md: The Markdown text produced by Pandoc + the package's
            Lua filter.
        code_blocks: The code-blocks dict returned by `lagda_md.preprocess`.
        label_map: Required when `enable_cross_refs=True`.  Maps label IDs to
            dicts of the form `{"file": str, "anchor": str, "caption_text": str}`.
            Build one with `build_label_map`.
        enable_cross_refs: If True, resolve @@CROSS_REF@@ placeholders.  Must
            be the same value passed to `preprocess` for the same file.
        enable_theorem_envs: If True, restore @@..._BLOCK@@ theorem placeholders.
        enable_figure_envs: If True, restore @@FIGURE_BLOCK@@ placeholders.

    Returns:
        The final `.lagda.md` content.
    """
    if enable_cross_refs and label_map is None:
        raise ValueError(
            "enable_cross_refs=True requires a label_map; "
            "use lagda_md.postprocess.build_label_map to construct one"
        )

    transformations: list[Callable[[str], str]] = [
        lambda c: _restore_code_blocks(c, code_blocks),
    ]
    if enable_figure_envs:
        transformations.append(_restore_figure_blocks)
    if enable_theorem_envs:
        transformations.append(_restore_theorem_blocks)
    if enable_cross_refs:
        assert label_map is not None  # validated above
        transformations.append(lambda c: _resolve_cross_refs(c, label_map))

    return reduce(lambda content, step: step(content), transformations, intermediate_md)


# ---------------------------------------------------------------------------
# Always-on: code-block re-insertion
# ---------------------------------------------------------------------------
_CODEBLOCK_PATTERN = re.compile(r"@@CODEBLOCK_ID_\d+@@")


def _restore_code_blocks(content: str, code_blocks: Mapping[str, dict]) -> str:
    """Replace each @@CODEBLOCK_ID_n@@ with its corresponding fenced block.

    Hidden blocks (those captured from `\\begin{code}[hide]`) are wrapped
    in HTML comments so they're type-checked by Agda but invisible by
    default in the rendered Markdown.
    """
    def _replace(match: re.Match) -> str:
        placeholder = match.group(0)
        block = code_blocks.get(placeholder, {})
        body = block.get("content", "").rstrip() + "\n"
        if block.get("hidden", False):
            return f"\n<!--\n```agda\n{body}```\n-->\n"
        return f"\n```agda\n{body}```\n"

    return _CODEBLOCK_PATTERN.sub(_replace, content)


# ---------------------------------------------------------------------------
# Opt-in: cross-references
# ---------------------------------------------------------------------------
_CROSSREF_PATTERN = re.compile(
    r"@@CROSS_REF@@command=(.*?)@@targets=(.*?)@@",
    flags=re.DOTALL,
)


def _resolve_cross_refs(
    content: str, label_map: Mapping[str, Mapping[str, str]]
) -> str:
    """Resolve each @@CROSS_REF@@ placeholder against the label map."""
    def _replace(match: re.Match) -> str:
        targets_str = _unescape_from_placeholder(match.group(2))
        labels = [t.strip() for t in targets_str.split(",") if t.strip()]
        return _format_cross_ref_links(labels, label_map)

    return _CROSSREF_PATTERN.sub(_replace, content)


def _format_cross_ref_links(
    labels: list[str], label_map: Mapping[str, Mapping[str, str]]
) -> str:
    """Format a list of label IDs as a chain of Markdown links joined by 'and'."""
    parts: list[str] = []
    for label_id in labels:
        target = label_map.get(label_id)
        if target is None:
            parts.append(f"*'{label_id}' (unresolved reference)*")
            logger.warning("Unresolved cross-reference: %r", label_id)
            continue

        caption = target.get("caption_text", label_id)
        display = caption.replace("-", " ")
        target_file = target.get("file", "")
        anchor = target.get("anchor", "")

        if target_file and anchor:
            parts.append(f"Section [{display}]({target_file}{anchor})")
        else:
            parts.append(f"*Section {display} (link generation error)*")
            logger.warning(
                "Cross-reference %r resolved but missing file/anchor", label_id
            )

    return " and ".join(parts)


# ---------------------------------------------------------------------------
# Opt-in: theorem / lemma / claim blocks
# ---------------------------------------------------------------------------
_THEOREM_BLOCK_LABELED = re.compile(
    r"@@(THEOREM|LEMMA|CLAIM)_BLOCK@@label=(.*?)@@title=(.*?)@@\n(.*?)(?=\n@@|\Z)",
    flags=re.DOTALL,
)
_THEOREM_BLOCK_UNLABELED = re.compile(
    r"@@(THEOREM|LEMMA|CLAIM)_BLOCK@@title=(.*?)@@\n(.*?)(?=\n@@|\Z)",
    flags=re.DOTALL,
)


def _restore_theorem_blocks(content: str) -> str:
    """Restore theorem/lemma/claim placeholders to styled Markdown blocks."""
    content = _THEOREM_BLOCK_LABELED.sub(
        lambda m: _format_theorem_block(
            m.group(1).lower(),
            _unescape_from_placeholder(m.group(2)),
            _unescape_from_placeholder(m.group(3)),
            m.group(4),
        ),
        content,
    )
    content = _THEOREM_BLOCK_UNLABELED.sub(
        lambda m: _format_theorem_block(
            m.group(1).lower(),
            "",
            _unescape_from_placeholder(m.group(2)),
            m.group(3),
        ),
        content,
    )
    return content


def _format_theorem_block(kind: str, label: str, title: str, body: str) -> str:
    """Format one theorem-like block as Markdown with optional anchor."""
    anchor = f'<a id="{label}"></a>\n' if label else ""
    heading = f"**{kind.capitalize()} ({title.strip(': ').strip()}).**"
    return f"{anchor}{heading}\n\n{body.strip()}\n"


# ---------------------------------------------------------------------------
# Opt-in: figures
# ---------------------------------------------------------------------------
_FIGURE_LABELED_PATTERN = re.compile(
    r"@@FIGURE_BLOCK_TO_SUBSECTION@@label=(.*?)@@caption=(.*?)@@",
    flags=re.DOTALL,
)
_FIGURE_UNLABELED_PATTERN = re.compile(
    r"@@UNLABELLED_FIGURE_CAPTION@@caption=(.*?)@@",
    flags=re.DOTALL,
)


def _restore_figure_blocks(content: str) -> str:
    """Restore figure placeholders as Markdown H3 headings."""
    content = _FIGURE_LABELED_PATTERN.sub(
        lambda m: _format_figure_subsection(_unescape_from_placeholder(m.group(2))),
        content,
    )
    content = _FIGURE_UNLABELED_PATTERN.sub(
        lambda m: _format_figure_subsection(_unescape_from_placeholder(m.group(1))),
        content,
    )
    return content


def _format_figure_subsection(caption: str) -> str:
    """Format a figure caption as an H3 heading."""
    cleaned = caption.replace("-", " ")
    squashed = re.sub(r"\s+", " ", cleaned).strip()
    return f"\n### {squashed}\n\n"


# ---------------------------------------------------------------------------
# Cross-reference label map: extraction and helpers
# ---------------------------------------------------------------------------
_LABEL_FIGURE_PATTERN = re.compile(
    r"@@FIGURE_BLOCK_TO_SUBSECTION@@label=(.*?)@@caption=(.*?)@@",
    flags=re.DOTALL,
)
_LABEL_THEOREM_PATTERN = re.compile(
    r"@@(THEOREM|LEMMA|CLAIM)_BLOCK@@label=(.*?)@@title=(.*?)@@",
    flags=re.DOTALL,
)
_LABEL_SECTION_LABEL_PATTERN = re.compile(r"\\label\{(.*?)\}")
_LABEL_SECTION_HEADING_PATTERN = re.compile(r"\\section\*?\{(.+?)\}", flags=re.DOTALL)


def build_label_map(
    sources: Mapping[Path, str],
    *,
    source_root: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Build a cross-reference label map from preprocessor outputs.

    Args:
        sources: Mapping from a `.lagda` source path to the corresponding
            preprocessor output (the placeholder-bearing string returned by
            `lagda_md.preprocess.preprocess`).
        source_root: Optional path used to compute each entry's `file` value
            relative to the project root.  When None, the file's basename is
            used.

    Returns:
        A dict mapping label IDs to `{"file": str, "anchor": str,
        "caption_text": str}`.  Suitable for passing as `label_map=` to
        `postprocess`.
    """
    label_map: dict[str, dict[str, str]] = {}

    for source_path, content in sources.items():
        relative = (
            source_path.relative_to(source_root)
            if source_root is not None
            else Path(source_path.name)
        )
        flat_filename = _get_flat_filename(relative)

        for match in _LABEL_FIGURE_PATTERN.finditer(content):
            label_id = _unescape_from_placeholder(match.group(1))
            caption = _unescape_from_placeholder(match.group(2))
            label_map[label_id] = {
                "file": flat_filename,
                "anchor": f"#{_slugify(caption)}",
                "caption_text": caption,
            }

        for match in _LABEL_THEOREM_PATTERN.finditer(content):
            kind = match.group(1).capitalize()
            label_id = _unescape_from_placeholder(match.group(2))
            title = _unescape_from_placeholder(match.group(3))
            label_map[label_id] = {
                "file": flat_filename,
                "anchor": f"#{label_id}",
                "caption_text": f"{kind} ({title.strip(': ')})",
            }

        for match in _LABEL_SECTION_LABEL_PATTERN.finditer(content):
            label_id = _unescape_from_placeholder(match.group(1))
            before = content[: match.start()]
            section_matches = list(_LABEL_SECTION_HEADING_PATTERN.finditer(before))
            section_title = (
                section_matches[-1].group(1).strip() if section_matches else label_id
            )
            label_map[label_id] = {
                "file": flat_filename,
                "anchor": f"#{label_id}",
                "caption_text": section_title,
            }

    return label_map


def _slugify(text: str | None) -> str:
    """Generate a slug from text, similar to Python-Markdown's default behavior."""
    if not text:
        return "section"
    slug = str(text).lower()
    slug = re.sub(r"[^\w\s-]", "", slug).strip()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "section"


def _get_flat_filename(relative_path: Path) -> str:
    """Compute a flat 'ModuleName.md' filename from a relative path.

    Handles `.lagda` and `.lagda.md` double extensions as well as `index`
    files; mirrors the FLS pipeline's flattening convention so cross-references
    resolve in MkDocs sites that use the same scheme.
    """
    name = relative_path.name
    if name.endswith(".lagda.md"):
        stem = name[: -len(".lagda.md")]
    elif name.endswith(".lagda"):
        stem = name[: -len(".lagda")]
    else:
        stem = relative_path.stem

    parts = list(relative_path.parent.parts)
    is_index = stem.lower() == "index"

    if not parts and is_index:
        flat_name = "index"
    elif not parts:
        flat_name = stem
    else:
        if not is_index:
            parts.append(stem)
        flat_name = ".".join(parts)

    return f"{flat_name}.md"
