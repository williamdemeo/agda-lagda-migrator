"""Tests for lagda_md.cli and lagda_md.core.

These tests use a fake Pandoc executable (a shell script that
copies stdin to stdout, after the temp file is read) so the CLI
runs end-to-end without depending on Pandoc being installed.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from lagda_md.cli import main
from lagda_md.core import ConversionError, convert_file, convert_tree


# ---------------------------------------------------------------------------
# Test fixtures: a fake pandoc that just copies its input file to its
# output file, so the four-stage pipeline runs without Pandoc installed.
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_pandoc(tmp_path: Path) -> Path:
    """A no-op Pandoc replacement that copies its --output's matching input."""
    fake = tmp_path / "fake_pandoc.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "# Argument-parsing pandoc stand-in.  Reads -o for the output path,\n"
        "# treats the last positional arg as the input.\n"
        "out=\"\"\n"
        "args=()\n"
        "while [[ $# -gt 0 ]]; do\n"
        "  case \"$1\" in\n"
        "    -o) out=\"$2\"; shift 2 ;;\n"
        "    --lua-filter) shift 2 ;;\n"
        "    -f|-t) shift 2 ;;\n"
        "    *) args+=(\"$1\"); shift ;;\n"
        "  esac\n"
        "done\n"
        "in=\"${args[-1]}\"\n"
        "cp \"$in\" \"$out\"\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return fake


# ---------------------------------------------------------------------------
# convert_file — single-file behavior
# ---------------------------------------------------------------------------
class TestConvertFile:
    def test_simple_file_round_trips(self, tmp_path: Path, fake_pandoc: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text(
            "Some prose.\n"
            "\\begin{code}\n"
            "data ⊤ : Set where tt : ⊤\n"
            "\\end{code}\n",
            encoding="utf-8",
        )
        convert_file(src, dst, pandoc=str(fake_pandoc))
        assert dst.exists()
        result = dst.read_text(encoding="utf-8")
        assert "Some prose." in result
        assert "data ⊤ : Set where tt : ⊤" in result
        assert "```agda" in result

    def test_creates_parent_directories(self, tmp_path: Path, fake_pandoc: Path):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "out" / "subtree" / "Foo.lagda.md"
        src.write_text("\\begin{code}\nfoo = 1\n\\end{code}\n", encoding="utf-8")
        convert_file(src, dst, pandoc=str(fake_pandoc))
        assert dst.exists()
        assert dst.parent.is_dir()

    def test_missing_input_raises(self, tmp_path: Path, fake_pandoc: Path):
        with pytest.raises(FileNotFoundError):
            convert_file(
                tmp_path / "nope.lagda",
                tmp_path / "out.lagda.md",
                pandoc=str(fake_pandoc),
            )

    def test_pandoc_executable_missing_raises_conversion_error(
        self, tmp_path: Path
    ):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text("\\begin{code}\nfoo = 1\n\\end{code}\n", encoding="utf-8")
        with pytest.raises(ConversionError, match="pandoc"):
            convert_file(src, dst, pandoc="this-binary-does-not-exist")

    def test_cross_refs_without_label_map_raises(
        self, tmp_path: Path, fake_pandoc: Path
    ):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text("trivial\n", encoding="utf-8")
        with pytest.raises(ValueError, match="label_map"):
            convert_file(
                src, dst, pandoc=str(fake_pandoc), enable_cross_refs=True
            )


# ---------------------------------------------------------------------------
# convert_tree — whole-tree behavior
# ---------------------------------------------------------------------------
class TestConvertTree:
    def test_mirrors_directory_structure(
        self, tmp_path: Path, fake_pandoc: Path
    ):
        in_root = tmp_path / "in"
        out_root = tmp_path / "out"
        (in_root / "a").mkdir(parents=True)
        (in_root / "b" / "c").mkdir(parents=True)
        (in_root / "a" / "M1.lagda").write_text(
            "\\begin{code}\nfoo = 1\n\\end{code}\n", encoding="utf-8"
        )
        (in_root / "b" / "c" / "M2.lagda").write_text(
            "\\begin{code}\nbar = 2\n\\end{code}\n", encoding="utf-8"
        )

        succeeded, failed = convert_tree(
            list(in_root.rglob("*.lagda")),
            in_root=in_root,
            out_root=out_root,
            pandoc=str(fake_pandoc),
        )
        assert len(succeeded) == 2
        assert len(failed) == 0
        assert (out_root / "a" / "M1.lagda.md").exists()
        assert (out_root / "b" / "c" / "M2.lagda.md").exists()

    def test_collects_failures_without_aborting(
        self, tmp_path: Path, fake_pandoc: Path
    ):
        in_root = tmp_path / "in"
        out_root = tmp_path / "out"
        in_root.mkdir()
        (in_root / "good.lagda").write_text(
            "\\begin{code}\nfoo = 1\n\\end{code}\n", encoding="utf-8"
        )

        # Simulate a per-file failure by making the output path's parent
        # un-writable.  (Skip the test if running as root, where chmod
        # has no effect.)
        if os.geteuid() == 0:
            pytest.skip("test relies on filesystem permissions; running as root")
        out_root.mkdir(mode=0o555)
        try:
            succeeded, failed = convert_tree(
                list(in_root.rglob("*.lagda")),
                in_root=in_root,
                out_root=out_root,
                pandoc=str(fake_pandoc),
            )
            assert len(succeeded) == 0
            assert len(failed) == 1
            assert failed[0][0] == in_root / "good.lagda"
        finally:
            out_root.chmod(0o755)


# ---------------------------------------------------------------------------
# CLI — argument parsing and exit codes
# ---------------------------------------------------------------------------
class TestCLI:
    def test_help_succeeds(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "convert_lagda" in out
        assert "--in-tree" in out

    def test_missing_args_returns_usage_error(self, capsys):
        rc = main([])
        assert rc == 1  # CLI usage error: returns 1 with a stderr message
        err = capsys.readouterr().err
        assert "INPUT is required" in err

    def test_single_file_conversion(
        self, tmp_path: Path, fake_pandoc: Path, capsys
    ):
        src = tmp_path / "Foo.lagda"
        dst = tmp_path / "Foo.lagda.md"
        src.write_text("\\begin{code}\nfoo = 1\n\\end{code}\n", encoding="utf-8")

        rc = main([
            str(src), str(dst),
            "--pandoc", str(fake_pandoc),
        ])
        assert rc == 0
        assert dst.exists()
        out = capsys.readouterr().out
        assert "wrote" in out

    def test_check_mode_succeeds_without_writing(
        self, tmp_path: Path, fake_pandoc: Path, capsys
    ):
        src = tmp_path / "Foo.lagda"
        src.write_text("\\begin{code}\nfoo = 1\n\\end{code}\n", encoding="utf-8")
        # Output not provided; --check should still succeed.
        rc = main([str(src), "--check", "--pandoc", str(fake_pandoc)])
        assert rc == 0
        assert "check passed" in capsys.readouterr().out

    def test_in_tree_mode_with_no_lagda_files_errors(
        self, tmp_path: Path, fake_pandoc: Path
    ):
        empty_in = tmp_path / "empty"
        empty_in.mkdir()
        rc = main([
            "--in-tree", str(empty_in),
            "--out-tree", str(tmp_path / "out"),
            "--pandoc", str(fake_pandoc),
        ])
        assert rc == 1
