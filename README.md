# agda-lagda-migrator

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

A Python package and command-line tool for converting LaTeX-literate Agda (`.lagda`) files into Markdown-literate Agda (`.lagda.md`) files.

This is the form a growing number of Agda projects are migrating toward — [1Lab](https://1lab.dev), [agda-categories](https://github.com/agda/agda-categories), [agda-algebras](https://github.com/ualib/agda-algebras), and others — because `.lagda.md` files render directly on GitHub, work cleanly with MkDocs and Jekyll, and serve as higher-quality training corpora for language models than either pure `.agda` or pure `.lagda` form.

## Quick start

The tool requires Python 3.10+ and (for LaTeX-literate input only) [Pandoc](https://pandoc.org) 3.0+.

```sh
git clone https://github.com/williamdemeo/agda-lagda-migrator.git
cd agda-lagda-migrator
chmod +x convert_lagda.py
```

For a `.lagda` file authored as **Markdown prose with `\begin{code}` fences for Agda code** (the agda-algebras and 1Lab convention):

```sh
./convert_lagda.py --input-format markdown INPUT.lagda OUTPUT.lagda.md
```

For a `.lagda` file authored as **LaTeX prose with `\begin{code}` fences for Agda code** (the formal-ledger-specifications convention; Pandoc required):

```sh
./convert_lagda.py INPUT.lagda OUTPUT.lagda.md
```

For converting a whole tree:

```sh
./convert_lagda.py --input-format markdown --in-tree PATH/TO/SOURCES --out-tree PATH/TO/OUTPUTS
```

## Why this exists

A `.lagda` file is Agda code with prose around it. Historically, those files have been authored in two distinct conventions:

+   **LaTeX-literate.** The prose is LaTeX, processed by `agda --latex` to produce typeset PDFs and websites. This is what the formal-ledger-specifications project uses, and was the original convention when Agda's literate mode was introduced.

+   **Markdown-literate.** The prose is Markdown, processed by tools like Jekyll or MkDocs to produce browsable websites. This is what 1Lab, agda-algebras, agda-categories, and a growing number of newer projects use. GitHub renders these directly.

Modern Agda has first-class support for `.lagda.md` (Markdown-literate Agda). Projects originally authored in the older `.lagda` form can migrate by converting their files in bulk. This tool automates that conversion.

The conversion needs to handle two non-trivial concerns:

1.  **Agda code blocks must survive intact.** Pandoc's Markdown reader and writer reindent code, which breaks Agda's layout-sensitive syntax. The pipeline extracts code blocks before any Markdown-or-LaTeX processing happens and restores them afterward.
2.  **Project-specific macros need consistent rewriting.** Each project tends to define its own LaTeX shorthands for Agda identifiers (e.g., `\ab` for `\AgdaBound`, `\af` for `\AgdaFunction`). The tool accepts a JSON macro table that specifies each shorthand's rendering.

## How it works

The tool implements two parallel pipelines, both of which extract Agda code blocks first and restore them last.

For **Markdown-literate input** (`--input-format markdown`):

```
.lagda  →  extract code blocks  →  apply macros  →  restore code blocks  →  .lagda.md
```

The prose is already in the target format, so Pandoc is bypassed entirely. YAML front matter, Markdown headings, reference-style links, and Jekyll directives are passed through unchanged; only `\begin{code}` blocks are rewritten as fenced `\`\`\`agda` blocks, and any macros from the supplied table are expanded inline.

For **LaTeX-literate input** (the default):

```
.lagda  →  extract code blocks  →  Pandoc + Lua filter  →  restore code blocks  →  .lagda.md
```

The prose runs through Pandoc's LaTeX reader and GFM writer. A Pandoc Lua filter handles Agda-specific macros and is layered with optional filters for cross-references, theorem environments, and figure environments. The full FLS-style rendering pipeline lives in `examples/fls-pipeline/` as a worked example for projects wanting a complete MkDocs site rather than just the conversion.

## Macro tables

Both pipelines accept a `--macros` flag pointing at a JSON file describing project-specific macros:

```json
{
  "agda_terms": {
    "ab": { "basename": "",  "agda_class": "AgdaBound" },
    "af": { "basename": "",  "agda_class": "AgdaFunction" },
    "ar": { "basename": "",  "agda_class": "AgdaRecord" }
  }
}
```

Each entry maps a macro name (without the leading backslash) to a rendering specification. An empty `basename` causes the macro's argument to be used as the rendered name; a non-empty `basename` is used directly regardless of the argument.

The package ships with a small default table (`lagda_md/macros/default.json`) covering common cases. Project-specific tables go alongside the project's source.

## Validation

This package was extracted from the [IntersectMBO formal-ledger-specifications](https://github.com/IntersectMBO/formal-ledger-specifications) project at commit `f6e177f5`, where the four-stage LaTeX pipeline was used to migrate the entire Cardano formal ledger specification corpus from `.lagda` to `.lagda.md`. That work is preserved as a worked example at `examples/fls-pipeline/`.

The Markdown-literate pipeline is being validated against the [agda-algebras](https://github.com/ualib/agda-algebras) corpus (127 files, all authored in Markdown-with-LaTeX-fences form) as a second-corpus check.  See [issue #6](https://github.com/williamdemeo/agda-lagda-migrator/issues/6) for the validation work in progress.

## Available transformations

Some transformations apply unconditionally; others are gated by opt-in flags.

**Always-on transformations** apply to every conversion:

+   Agda code-block extraction and restoration (visible and hidden).
+   Generic `\Agda...{name}` macro expansion for the nine standard Agda CSS classes (`AgdaFunction`, `AgdaField`, `AgdaDatatype`, `AgdaRecord`, `AgdaInductiveConstructor`, `AgdaModule`, `AgdaPrimitive`, `AgdaBound`, `AgdaArgument`).
+   `\ab{x}` shorthand expansion to `\AgdaBound{x}`.
+   Custom macros from the supplied `--macros` table.

The Markdown pipeline (`--input-format markdown`) additionally:

+   Resolves all custom-macro and `\Agda...` invocations to **kramdown attribute spans** of the form `` `name`{.AgdaClass} ``.  Jekyll's default kramdown processor and most other modern Markdown engines style these via CSS class.  Pair with a `custom.css` providing per-class rules; see the formal-ledger-specifications project for the canonical reference.
+   Rewrites LaTeX `\href{url}{text}` as Markdown `[text](url)`.

**Opt-in transformations** apply only to LaTeX-literate input and only when their flags are passed:

+   `--enable-cross-refs` — Resolves `\label{...}`, `\Cref{...}`, `\cref{...}` against a label map computed from the whole input tree. Loads `lagda_md/filters/cross-refs.lua` as an additional Pandoc filter.
+   `--enable-theorem-envs` — Restores `\begin{theorem}`, `\begin{lemma}`, `\begin{claim}` environments as styled Markdown blocks.
+   `--enable-figure-envs` — Restores `\begin{figure}` environments as Markdown subsections.

For Markdown-literate input, these flags are explicitly rejected (Markdown has its own native conventions for cross-references, theorems, and figures, and authors of Markdown-literate `.lagda` files use those rather than the LaTeX environments).

## Limitations

The tool's scope is intentionally narrow. It does not:

+   Build static websites. The output is `.lagda.md` files; rendering them as a website is a downstream concern. See `examples/fls-pipeline/` for a complete MkDocs example.
+   Auto-detect input format. The user passes `--input-format`; if the wrong format is chosen, the failure is loud (Pandoc parser error or unexpanded macros).
+   Handle bibliography processing or citation rewriting. The FLS example pipeline does this, but it depends on a specific BibTeX integration not generalizable enough to belong in the package.
+   Convert *between* the two formats. Source-to-source rewriting from LaTeX-literate to Markdown-literate (or vice versa) is a different problem.

## Architecture

```
agda-lagda-migrator/
├── convert_lagda.py            # CLI wrapper
├── lagda_md/                   # Importable Python package
│   ├── core.py                 # convert_file, convert_tree, dispatch
│   ├── preprocess.py           # Code-block extraction + macro expansion
│   ├── postprocess.py          # Code-block restoration + opt-in resolvers
│   ├── markdown_pipeline.py    # Markdown-literate input handler
│   ├── macros.py               # MacroTable abstraction
│   ├── cli.py                  # argparse-based CLI dispatch
│   ├── filters/
│   │   ├── agda-filter.lua     # Default Pandoc Lua filter
│   │   └── cross-refs.lua      # Optional cross-ref Lua filter
│   └── tests/                  # pytest test suite
├── examples/
│   └── fls-pipeline/           # The full FLS pipeline as a worked example
└── README.md
```

The package's public API is documented in `lagda_md/__init__.py`. The CLI's flags are documented in `--help`.

## Provenance

Extracted from [IntersectMBO/formal-ledger-specifications](https://github.com/IntersectMBO/formal-ledger-specifications) commit [`534652f22802118b2f8e9f6beae69084d91453d3`](https://github.com/IntersectMBO/formal-ledger-specifications/commit/534652f22802118b2f8e9f6beae69084d91453d3), specifically the `build-tools/scripts/md/` subdirectory at commit `f6e177f5`. See `NOTICE` for attribution.

## License

Apache License, Version 2.0. See `LICENSE`.
