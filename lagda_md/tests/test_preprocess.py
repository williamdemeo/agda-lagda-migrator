"""Tests for lagda_md.preprocess."""
from __future__ import annotations

import pytest

from lagda_md.macros import MacroEntry, MacroTable
from lagda_md.preprocess import preprocess


# ---------------------------------------------------------------------------
# Always-on transformations
# ---------------------------------------------------------------------------
class TestCodeBlockExtraction:
    def test_visible_block_is_extracted(self):
        content = (
            "Some prose.\n"
            "\\begin{code}\n"
            "data ⊤ : Set where tt : ⊤\n"
            "\\end{code}\n"
            "More prose.\n"
        )
        text, blocks = preprocess(content)

        assert "@@CODEBLOCK_ID_1@@" in text
        assert "\\begin{code}" not in text
        assert blocks["@@CODEBLOCK_ID_1@@"]["hidden"] is False
        assert "data ⊤" in blocks["@@CODEBLOCK_ID_1@@"]["content"]

    def test_hidden_block_is_extracted_and_flagged(self):
        content = (
            "\\begin{code}[hide]\n"
            "open import Foo\n"
            "\\end{code}\n"
        )
        text, blocks = preprocess(content)

        assert "@@CODEBLOCK_ID_1@@" in text
        assert blocks["@@CODEBLOCK_ID_1@@"]["hidden"] is True
        assert "open import Foo" in blocks["@@CODEBLOCK_ID_1@@"]["content"]

    def test_multiple_blocks_get_distinct_ids(self):
        content = (
            "\\begin{code}\nA\n\\end{code}\n"
            "Prose.\n"
            "\\begin{code}\nB\n\\end{code}\n"
        )
        text, blocks = preprocess(content)
        assert "@@CODEBLOCK_ID_1@@" in text
        assert "@@CODEBLOCK_ID_2@@" in text
        assert len(blocks) == 2

    def test_content_ends_with_newline(self):
        # The preprocessor should append a trailing newline if absent, so
        # that postprocess can produce well-formed fenced blocks.
        content = "\\begin{code}\nfoo = 1\\end{code}"
        _text, blocks = preprocess(content)
        assert blocks["@@CODEBLOCK_ID_1@@"]["content"].endswith("\n")


class TestGenericAgdaMacros:
    @pytest.mark.parametrize(
        "macro_class",
        [
            "AgdaFunction",
            "AgdaField",
            "AgdaDatatype",
            "AgdaRecord",
            "AgdaInductiveConstructor",
            "AgdaModule",
            "AgdaPrimitive",
            "AgdaBound",
            "AgdaArgument",
        ],
    )
    def test_class_is_recognized(self, macro_class):
        content = f"See \\{macro_class}{{foo}} for details."
        text, _blocks = preprocess(content)
        assert f"basename=foo@@class={macro_class}" in text

    def test_unknown_class_passes_through(self):
        content = "See \\AgdaCustomClass{foo} for details."
        text, _blocks = preprocess(content)
        assert "AgdaCustomClass" in text  # not matched, original survives
        assert "@@AgdaTerm@@" not in text


class TestAbShorthand:
    def test_ab_expands_to_agdabound(self):
        content = "Let \\ab{x} be a binding."
        text, _blocks = preprocess(content)
        assert "basename=x@@class=AgdaBound" in text


class TestNonBreakingSpace:
    def test_tilde_becomes_space(self):
        content = "Theorem~1 says..."
        text, _blocks = preprocess(content)
        assert "Theorem 1 says" in text


class TestCustomMacros:
    def test_custom_macro_with_basename(self):
        macros = MacroTable(
            entries={
                "MyMod": MacroEntry(basename="MyModule", agda_class="AgdaModule"),
            }
        )
        text, _blocks = preprocess("See \\MyMod{} for details.", macros)
        assert "basename=MyModule@@class=AgdaModule" in text

    def test_custom_macro_with_empty_basename_uses_argument(self):
        macros = MacroTable(
            entries={
                "myref": MacroEntry(basename="", agda_class="AgdaFunction"),
            }
        )
        text, _blocks = preprocess("See \\myref{specificFunc} please.", macros)
        assert "basename=specificFunc@@class=AgdaFunction" in text


class TestCustomMacroPrecedenceOverShorthand:
    def test_custom_ab_overrides_builtin_shorthand(self):
        macros = MacroTable(
            entries={
                "ab": MacroEntry(basename="", agda_class="AgdaArgument"),
            }
        )
        text, _blocks = preprocess("Let \\ab{x} be a binding.", macros)
        # The custom entry's class wins over the hardcoded \ab → \AgdaBound rule.
        assert "basename=x@@class=AgdaArgument" in text
        assert "AgdaBound" not in text

    def test_default_ab_shorthand_applies_when_no_custom_table(self):
        text, _blocks = preprocess("Let \\ab{x} be a binding.")
        # No custom entry; hardcoded shorthand fires.
        assert "basename=x@@class=AgdaBound" in text


# ---------------------------------------------------------------------------
# Opt-in flags
# ---------------------------------------------------------------------------
class TestCrossRefsFlag:
    def test_disabled_by_default(self):
        text, _blocks = preprocess("See \\Cref{sec:intro}.")
        assert "@@CROSS_REF@@" not in text
        assert "\\Cref" in text  # left untouched

    def test_enabled_emits_placeholder(self):
        text, _blocks = preprocess(
            "See \\Cref{sec:intro}.", enable_cross_refs=True
        )
        assert "@@CROSS_REF@@command=Cref@@targets=sec:intro@@" in text
        assert "\\Cref" not in text

    def test_lowercase_cref_also_handled(self):
        text, _blocks = preprocess(
            "See \\cref{sec:intro}.", enable_cross_refs=True
        )
        assert "@@CROSS_REF@@command=cref@@" in text


class TestTheoremEnvsFlag:
    def test_disabled_by_default(self):
        content = (
            "\\begin{theorem}[Birkhoff]\n"
            "Every variety is closed under HSP.\n"
            "\\end{theorem}\n"
        )
        text, _blocks = preprocess(content)
        assert "@@THEOREM_BLOCK@@" not in text
        assert "\\begin{theorem}" in text

    def test_enabled_emits_placeholder_with_title(self):
        content = (
            "\\begin{theorem}[Birkhoff]\n"
            "Every variety is closed under HSP.\n"
            "\\end{theorem}\n"
        )
        text, _blocks = preprocess(content, enable_theorem_envs=True)
        assert "@@THEOREM_BLOCK@@title=Birkhoff@@" in text
        assert "Every variety is closed under HSP." in text

    def test_enabled_handles_label(self):
        content = (
            "\\begin{lemma}[Useful]\n"
            "\\label{lem:useful}\n"
            "Body.\n"
            "\\end{lemma}\n"
        )
        text, _blocks = preprocess(content, enable_theorem_envs=True)
        assert "@@LEMMA_BLOCK@@label=lem:useful@@title=Useful@@" in text


class TestFigureEnvsFlag:
    def test_disabled_by_default(self):
        content = (
            "\\begin{figure}\n"
            "Some figure.\n"
            "\\caption{A caption}\n"
            "\\label{fig:test}\n"
            "\\end{figure}\n"
        )
        text, _blocks = preprocess(content)
        assert "@@FIGURE_BLOCK" not in text

    def test_enabled_with_label(self):
        content = (
            "\\begin{figure}\n"
            "Body.\n"
            "\\caption{A caption}\n"
            "\\label{fig:test}\n"
            "\\end{figure}\n"
        )
        text, _blocks = preprocess(content, enable_figure_envs=True)
        assert "@@FIGURE_BLOCK_TO_SUBSECTION@@" in text
        assert "label=fig:test@@" in text
        assert "caption=A-caption@@" in text

    def test_enabled_without_label(self):
        content = (
            "\\begin{figure}\n"
            "Body.\n"
            "\\caption{A caption}\n"
            "\\end{figure}\n"
        )
        text, _blocks = preprocess(content, enable_figure_envs=True)
        assert "@@UNLABELLED_FIGURE_CAPTION@@" in text

class TestNonBreakingSpaceFlag:
    def test_normalize_tildes_default_is_true(self):
        text, _blocks = preprocess("a~b")
        assert text == "a b"

    def test_normalize_tildes_false_preserves(self):
        text, _blocks = preprocess("a~b", normalize_tildes=False)
        assert text == "a~b"

# ---------------------------------------------------------------------------
# agda-algebras smoke test
# ---------------------------------------------------------------------------
class TestAgdaAlgebrasShape:
    """Sanity check on a synthetic input shaped like agda-algebras content."""

    def test_no_optin_placeholders_appear_by_default(self):
        # agda-algebras uses no \Cref, \begin{theorem}, or \begin{figure}.
        content = (
            "% Some prose with \\AgdaModule{Setoid.Algebras.Basic} reference.\n"
            "\\begin{code}\n"
            "open import Level using ( Level )\n"
            "\\end{code}\n"
            "More prose using \\ab{α} as a level.\n"
        )
        text, blocks = preprocess(content)

        assert len(blocks) == 1
        assert "@@AgdaTerm@@basename=Setoid.Algebras.Basic" in text
        assert "@@AgdaTerm@@basename=α@@class=AgdaBound" in text
        # No opt-in placeholders should appear:
        for marker in (
            "@@CROSS_REF@@",
            "@@THEOREM_BLOCK@@",
            "@@FIGURE_BLOCK_TO_SUBSECTION@@",
            "@@UNLABELLED_FIGURE_CAPTION@@",
        ):
            assert marker not in text
