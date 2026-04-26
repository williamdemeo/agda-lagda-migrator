"""Tests for lagda_md.markdown_pipeline and the Markdown-literate
input format end-to-end.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lagda_md.cli import main
from lagda_md.core import convert_file
from lagda_md.macros import MacroEntry, MacroTable
from lagda_md.markdown_pipeline import convert_markdown


# ---------------------------------------------------------------------------
# Direct convert_markdown tests
# ---------------------------------------------------------------------------
class TestConvertMarkdown:
    def test_minimal_markdown_literate_file(self, tmp_path: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text(
            "# A heading\n"
            "\n"
            "Some prose.\n"
            "\n"
            "\\begin{code}\n"
            "data ⊤ : Set where tt : ⊤\n"
            "\\end{code}\n"
            "\n"
            "More prose.\n",
            encoding="utf-8",
        )
        convert_markdown(src, dst)
        result = dst.read_text(encoding="utf-8")

        assert "# A heading" in result
        assert "Some prose." in result
        assert "More prose." in result
        assert "```agda" in result
        assert "data ⊤ : Set where tt : ⊤" in result
        # Code-block placeholder should be gone:
        assert "@@CODEBLOCK_ID_" not in result

    def test_yaml_front_matter_preserved(self, tmp_path: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text(
            "---\n"
            "layout: default\n"
            'title: "My Module"\n'
            "---\n"
            "\n"
            "Body content.\n",
            encoding="utf-8",
        )
        convert_markdown(src, dst)
        result = dst.read_text(encoding="utf-8")
        assert result.startswith("---\nlayout: default\n")
        assert "Body content." in result

    def test_hidden_code_blocks_wrapped_in_html_comments(self, tmp_path: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text(
            "Public prose.\n"
            "\n"
            "\\begin{code}[hide]\n"
            "{-# OPTIONS --safe #-}\n"
            "module Foo where\n"
            "\\end{code}\n",
            encoding="utf-8",
        )
        convert_markdown(src, dst)
        result = dst.read_text(encoding="utf-8")
        assert "<!--" in result
        assert "module Foo where" in result
        assert "-->" in result

    def test_creates_parent_directories(self, tmp_path: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "deep" / "nested" / "out" / "Foo.lagda.md"
        src.write_text("# Hi\n\\begin{code}\nfoo = 1\n\\end{code}\n", encoding="utf-8")
        convert_markdown(src, dst)
        assert dst.exists()

    def test_missing_input_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            convert_markdown(tmp_path / "nope.lagda", tmp_path / "out.lagda.md")

    def test_custom_macros_applied_to_prose(self, tmp_path: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text(
            "Use \\af{Subalgebras} as a reference.\n", encoding="utf-8"
        )
        macros = MacroTable.from_dict(
            {
                "agda_terms": {
                    "af": {"basename": "", "agda_class": "AgdaFunction"},
                }
            }
        )
        convert_markdown(src, dst, macros=macros)
        result = dst.read_text(encoding="utf-8")
        assert "Subalgebras" in result
        # The custom-macro expansion produces a placeholder which Pandoc
        # would normally consume; in the Markdown pipeline there is no
        # Pandoc, so the AgdaTerm placeholder appears as raw text.  The
        # downstream MkDocs / Jekyll site is expected to handle these.
        assert "@@AgdaTerm@@basename=Subalgebras@@class=AgdaFunction@@" in result

    def test_no_code_blocks_passthrough(self, tmp_path: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text(
            "# Just prose\n\nNo code in this file.\n", encoding="utf-8"
        )
        convert_markdown(src, dst)
        result = dst.read_text(encoding="utf-8")
        assert "# Just prose" in result
        assert "No code in this file." in result

    def test_multiple_code_blocks_restored_in_order(self, tmp_path: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text(
            "First.\n\n"
            "\\begin{code}\nA = 1\n\\end{code}\n\n"
            "Second.\n\n"
            "\\begin{code}\nB = 2\n\\end{code}\n\n"
            "Third.\n",
            encoding="utf-8",
        )
        convert_markdown(src, dst)
        result = dst.read_text(encoding="utf-8")
        assert result.index("A = 1") < result.index("B = 2")
        assert result.index("First.") < result.index("Second.")
        assert result.index("Second.") < result.index("Third.")


# ---------------------------------------------------------------------------
# convert_file dispatch + opt-in-flag rejection
# ---------------------------------------------------------------------------
class TestConvertFileDispatch:
    def test_markdown_format_dispatches_to_markdown_pipeline(self, tmp_path: Path):
        # Without Pandoc installed, the LaTeX pipeline would fail at Pandoc
        # invocation.  The Markdown pipeline doesn't invoke Pandoc, so this
        # test passes purely on the dispatch correctness.
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text("# Hi\n\\begin{code}\nfoo = 1\n\\end{code}\n", encoding="utf-8")
        convert_file(src, dst, input_format="markdown")
        assert dst.exists()
        assert "```agda" in dst.read_text(encoding="utf-8")

    def test_invalid_input_format_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="input_format must be"):
            convert_file(
                tmp_path / "x.lagda",
                tmp_path / "x.lagda.md",
                input_format="rst",
            )

    @pytest.mark.parametrize(
        "flag",
        ["enable_cross_refs", "enable_theorem_envs", "enable_figure_envs"],
    )
    def test_markdown_input_with_optin_flag_raises(self, tmp_path: Path, flag: str):
        src = tmp_path / "Foo.lagda"
        src.write_text("trivial\n", encoding="utf-8")
        kwargs = {"input_format": "markdown", flag: True}
        with pytest.raises(ValueError, match="opt-in"):
            convert_file(
                src,
                tmp_path / "Foo.lagda.md",
                **kwargs,
            )


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------
class TestCLIMarkdownMode:
    def test_input_format_markdown_via_cli(self, tmp_path: Path, capsys):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text(
            "---\nlayout: default\n---\n\n"
            "# Test\n\n"
            "\\begin{code}\nfoo = 1\n\\end{code}\n",
            encoding="utf-8",
        )

        rc = main([str(src), str(dst), "--input-format", "markdown"])
        assert rc == 0
        result = dst.read_text(encoding="utf-8")
        assert "layout: default" in result
        assert "```agda" in result

    def test_input_format_default_is_latex(self, capsys):
        # Verify the help output documents 'latex' as the default.
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        assert "--input-format" in out
        assert "latex" in out


# ---------------------------------------------------------------------------
# agda-algebras corpus shape (the failing case from the smoke test)
# ---------------------------------------------------------------------------
class TestAgdaAlgebrasShape:
    def test_general_operations_and_relations_shape_round_trips(
        self, tmp_path: Path
    ):
        """Reproduces the smoke-test failure case from #11's discovery.

        agda-algebras's docs/lagda/Demos/GeneralOperationsAndRelations.lagda
        has YAML front matter, a Markdown heading, reference-style
        Markdown links, a Jekyll include directive, and a single hidden
        code block.  The LaTeX pipeline failed with a Pandoc parser error
        ("unexpected ()").  The Markdown pipeline should handle it
        cleanly.
        """
        src = tmp_path / "GeneralOperationsAndRelations.lagda"
        dst = tmp_path / "GeneralOperationsAndRelations.lagda.md"
        src.write_text(
            "---\n"
            "layout: default\n"
            'title : "Demos.GeneralOperationsAndRelations module"\n'
            'date : "2022-04-27"\n'
            'author: "the agda-algebras development team"\n'
            "---\n"
            "\n"
            '### <a id="general-operations-and-relations">'
            "General Opereations and Relations</a>\n"
            "\n"
            "+  [Signatures][Overture.Signatures]\n"
            "+  [Operations][Overture.Operations]\n"
            "+  [Relations][Base.Relations]\n"
            "   +  [Discrete Relations][Base.Relations.Discrete]\n"
            "   +  [Continuous Relations][Base.Relations.Continuous]\n"
            "+  [Containers][]\n"
            "\n"
            "\\begin{code}[hide]\n"
            "{-# OPTIONS --cubical-compatible --exact-split --safe #-}\n"
            "\n"
            "module Demos.GeneralOperationsAndRelations where\n"
            "\\end{code}\n"
            "\n"
            "{% include UALib.Links.md %}\n",
            encoding="utf-8",
        )

        convert_markdown(src, dst)
        result = dst.read_text(encoding="utf-8")

        # Front matter preserved.
        assert "layout: default" in result
        # Heading preserved.
        assert "general-operations-and-relations" in result
        # Reference-style link preserved (we shouldn't be touching it).
        assert "[Signatures][Overture.Signatures]" in result
        # Jekyll directive preserved.
        assert "{% include UALib.Links.md %}" in result
        # Hidden code block restored as commented Agda block.
        assert "<!--" in result
        assert "module Demos.GeneralOperationsAndRelations where" in result
