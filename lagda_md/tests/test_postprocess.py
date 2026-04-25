"""Tests for lagda_md.postprocess."""
from __future__ import annotations

from pathlib import Path

import pytest

from lagda_md.postprocess import build_label_map, postprocess
from lagda_md.preprocess import preprocess


# ---------------------------------------------------------------------------
# Always-on: code-block restoration
# ---------------------------------------------------------------------------
class TestCodeBlockRestoration:
    def test_visible_block_restored_as_fenced(self):
        intermediate = "Some prose.\n\n@@CODEBLOCK_ID_1@@\n\nMore prose.\n"
        blocks = {
            "@@CODEBLOCK_ID_1@@": {"content": "data ⊤ : Set\n", "hidden": False}
        }
        result = postprocess(intermediate, blocks)
        assert "```agda" in result
        assert "data ⊤ : Set" in result
        assert "@@CODEBLOCK_ID_1@@" not in result

    def test_hidden_block_wrapped_in_html_comments(self):
        intermediate = "Prose. @@CODEBLOCK_ID_1@@ More.\n"
        blocks = {
            "@@CODEBLOCK_ID_1@@": {
                "content": "open import Foo\n",
                "hidden": True,
            }
        }
        result = postprocess(intermediate, blocks)
        assert "<!--" in result
        assert "```agda" in result
        assert "open import Foo" in result
        assert "-->" in result

    def test_multiple_blocks_restored_in_order(self):
        intermediate = "@@CODEBLOCK_ID_1@@\n\n@@CODEBLOCK_ID_2@@\n"
        blocks = {
            "@@CODEBLOCK_ID_1@@": {"content": "A\n", "hidden": False},
            "@@CODEBLOCK_ID_2@@": {"content": "B\n", "hidden": False},
        }
        result = postprocess(intermediate, blocks)
        assert result.index("A") < result.index("B")

    def test_unknown_placeholder_renders_empty_block(self):
        intermediate = "@@CODEBLOCK_ID_99@@"
        result = postprocess(intermediate, {})
        assert "```agda" in result


# ---------------------------------------------------------------------------
# Round-trip with preprocess
# ---------------------------------------------------------------------------
class TestPreprocessPostprocessRoundTrip:
    def test_visible_code_block_round_trip(self):
        original = (
            "Some prose.\n"
            "\\begin{code}\n"
            "data ⊤ : Set where tt : ⊤\n"
            "\\end{code}\n"
            "More prose.\n"
        )
        intermediate, blocks = preprocess(original)
        result = postprocess(intermediate, blocks)
        assert "```agda" in result
        assert "data ⊤ : Set where tt : ⊤" in result
        assert "Some prose." in result
        assert "More prose." in result

    def test_hidden_code_block_round_trip(self):
        original = (
            "\\begin{code}[hide]\n"
            "open import Universe\n"
            "\\end{code}\n"
        )
        intermediate, blocks = preprocess(original)
        result = postprocess(intermediate, blocks)
        assert "<!--" in result
        assert "open import Universe" in result


# ---------------------------------------------------------------------------
# Opt-in flags
# ---------------------------------------------------------------------------
class TestCrossRefsFlag:
    def test_disabled_by_default(self):
        intermediate = "See @@CROSS_REF@@command=Cref@@targets=sec:intro@@."
        result = postprocess(intermediate, {})
        assert "@@CROSS_REF@@" in result

    def test_enabled_requires_label_map(self):
        with pytest.raises(ValueError, match="label_map"):
            postprocess("any content", {}, enable_cross_refs=True)

    def test_enabled_resolves_known_label(self):
        intermediate = "See @@CROSS_REF@@command=Cref@@targets=sec:intro@@."
        label_map = {
            "sec:intro": {
                "file": "Intro.md",
                "anchor": "#sec:intro",
                "caption_text": "Introduction",
            }
        }
        result = postprocess(
            intermediate, {}, label_map=label_map, enable_cross_refs=True
        )
        assert "[Introduction](Intro.md#sec:intro)" in result
        assert "Section " in result

    def test_unresolved_label_yields_warning_marker(self, caplog):
        intermediate = "See @@CROSS_REF@@command=Cref@@targets=sec:missing@@."
        result = postprocess(
            intermediate, {}, label_map={}, enable_cross_refs=True
        )
        assert "unresolved reference" in result
        assert any("Unresolved" in r.message for r in caplog.records)

    def test_multiple_targets_joined_with_and(self):
        intermediate = "See @@CROSS_REF@@command=Cref@@targets=a,b@@."
        label_map = {
            "a": {"file": "X.md", "anchor": "#a", "caption_text": "A"},
            "b": {"file": "X.md", "anchor": "#b", "caption_text": "B"},
        }
        result = postprocess(
            intermediate, {}, label_map=label_map, enable_cross_refs=True
        )
        assert " and " in result
        assert "[A](X.md#a)" in result
        assert "[B](X.md#b)" in result


class TestTheoremEnvsFlag:
    def test_disabled_by_default(self):
        intermediate = "@@THEOREM_BLOCK@@title=Birkhoff@@\nA proof body.\n"
        result = postprocess(intermediate, {})
        assert "@@THEOREM_BLOCK@@" in result

    def test_enabled_renders_unlabeled_block(self):
        intermediate = "@@THEOREM_BLOCK@@title=Birkhoff@@\nA proof body.\n"
        result = postprocess(intermediate, {}, enable_theorem_envs=True)
        assert "**Theorem (Birkhoff).**" in result
        assert "A proof body." in result
        assert "@@THEOREM_BLOCK@@" not in result

    def test_enabled_renders_labeled_block_with_anchor(self):
        intermediate = (
            "@@LEMMA_BLOCK@@label=lem:useful@@title=Useful@@\n"
            "Body of the lemma.\n"
        )
        result = postprocess(intermediate, {}, enable_theorem_envs=True)
        assert '<a id="lem:useful"></a>' in result
        assert "**Lemma (Useful).**" in result


class TestFigureEnvsFlag:
    def test_disabled_by_default(self):
        intermediate = (
            "@@FIGURE_BLOCK_TO_SUBSECTION@@label=fig:test@@caption=A-figure@@"
        )
        result = postprocess(intermediate, {})
        assert "@@FIGURE_BLOCK_TO_SUBSECTION@@" in result

    def test_enabled_labeled_figure_renders_as_subsection(self):
        intermediate = (
            "@@FIGURE_BLOCK_TO_SUBSECTION@@label=fig:test@@caption=A-figure@@"
        )
        result = postprocess(intermediate, {}, enable_figure_envs=True)
        assert "### A figure" in result
        assert "@@" not in result

    def test_enabled_unlabeled_figure_renders_as_subsection(self):
        intermediate = "@@UNLABELLED_FIGURE_CAPTION@@caption=Just-a-caption@@"
        result = postprocess(intermediate, {}, enable_figure_envs=True)
        assert "### Just a caption" in result


# ---------------------------------------------------------------------------
# Placeholder escape symmetry
# ---------------------------------------------------------------------------
class TestPlaceholderEscapeRoundTrip:
    def test_at_at_in_cross_ref_target_round_trips(self):
        # If a label ID contains @@, preprocess escapes it to @ @ on the way
        # in.  postprocess must reverse the escape so the resolved label
        # matches the original key in the label map.
        intermediate = "See @@CROSS_REF@@command=Cref@@targets=sec:foo@ @bar@@."
        label_map = {
            "sec:foo@@bar": {
                "file": "X.md",
                "anchor": "#sec:foo_bar",
                "caption_text": "Section title",
            }
        }
        result = postprocess(
            intermediate, {}, label_map=label_map, enable_cross_refs=True
        )
        assert "Section title" in result
        assert "unresolved reference" not in result

    def test_at_at_in_theorem_label_round_trips(self):
        intermediate = (
            "@@LEMMA_BLOCK@@label=lem:weird@ @case@@title=Useful@@\n"
            "Body.\n"
        )
        result = postprocess(intermediate, {}, enable_theorem_envs=True)
        # The label survives unescaping into the HTML anchor.
        assert '<a id="lem:weird@@case"></a>' in result


# ---------------------------------------------------------------------------
# Label-map construction
# ---------------------------------------------------------------------------
class TestBuildLabelMap:
    def test_empty_sources(self):
        assert build_label_map({}) == {}

    def test_collects_labeled_figure(self):
        sources = {
            Path("foo.lagda"): (
                "Some prose.\n"
                "@@FIGURE_BLOCK_TO_SUBSECTION@@label=fig:diagram@@caption=My-Diagram@@\n"
                "More prose.\n"
            )
        }
        m = build_label_map(sources)
        assert "fig:diagram" in m
        assert m["fig:diagram"]["caption_text"] == "My-Diagram"
        assert m["fig:diagram"]["file"] == "foo.md"

    def test_collects_labeled_theorem(self):
        sources = {
            Path("foo.lagda"): (
                "@@THEOREM_BLOCK@@label=thm:big@@title=Big@@\nBody.\n"
            )
        }
        m = build_label_map(sources)
        assert "thm:big" in m
        assert "Theorem (Big)" in m["thm:big"]["caption_text"]

    def test_uses_relative_path_from_source_root(self, tmp_path: Path):
        src_root = tmp_path
        src_file = src_root / "Sub" / "Module.lagda"
        sources = {
            src_file: (
                "@@THEOREM_BLOCK@@label=thm:foo@@title=Foo@@\nBody.\n"
            )
        }
        m = build_label_map(sources, source_root=src_root)
        assert m["thm:foo"]["file"] == "Sub.Module.md"

    def test_section_label_resolves_to_preceding_heading(self):
        sources = {
            Path("foo.lagda"): (
                "\\section{Introduction}\n"
                "Some prose.\n"
                "\\label{sec:intro}\n"
                "More prose.\n"
            )
        }
        m = build_label_map(sources)
        assert "sec:intro" in m
        assert m["sec:intro"]["caption_text"] == "Introduction"

    def test_unescapes_at_at_in_label_id(self):
        sources = {
            Path("foo.lagda"): (
                "@@THEOREM_BLOCK@@label=thm:weird@ @case@@title=Foo@@\nBody.\n"
            )
        }
        m = build_label_map(sources)
        assert "thm:weird@@case" in m


# ---------------------------------------------------------------------------
# agda-algebras shape
# ---------------------------------------------------------------------------
class TestAgdaAlgebrasShape:
    """Sanity check: code-only corpus with no opt-in flags."""

    def test_minimal_pipeline_passes_through_prose(self):
        original = (
            "Some prose with no LaTeX commands.\n"
            "\\begin{code}\n"
            "open import Level using ( Level )\n"
            "\\end{code}\n"
            "More prose.\n"
        )
        intermediate, blocks = preprocess(original)
        result = postprocess(intermediate, blocks)

        assert "Some prose with no LaTeX commands." in result
        assert "More prose." in result
        assert "open import Level using ( Level )" in result
        assert "```agda" in result
        for marker in ("@@CROSS_REF@@", "@@THEOREM_BLOCK@@", "@@FIGURE_BLOCK"):
            assert marker not in result
