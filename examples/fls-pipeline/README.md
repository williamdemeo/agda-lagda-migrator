# FLS Pipeline (Worked Example)

This directory preserves the original conversion pipeline as it lived in `IntersectMBO/formal-ledger-specifications` at commit [`534652f`](https://github.com/IntersectMBO/formal-ledger-specifications/commit/534652f22802118b2f8e9f6beae69084d91453d3), specifically extracted from commit [`f6e177f5`](https://github.com/IntersectMBO/formal-ledger-specifications/commit/f6e177f5) for the version that pre-dates the `fls-shake` build orchestrator.

## Status

Reference implementation, not maintained.  This pipeline was used in production at IOHK to migrate the Cardano formal ledger specifications from LaTeX-literate to Markdown-literate Agda.  After the migration completed, the scripts were retired in place.

The successor for new projects is the `lagda_md/` Python package (and the `convert_lagda.py` CLI) at the repository root.  This directory exists because the FLS pipeline does several things the lean conversion tool deliberately does not: bibliography processing, MkDocs site assembly, TikZ-to-SVG figure generation, custom Agda HTML highlighting via `--fls-main-only`, FLS-specific admonitions and macros.  Projects wanting the full FLS treatment can read this code as a worked example.

## What's here

+  `build.py` — orchestrator running an eight-stage pipeline that culminates in a complete MkDocs site at `_build/md/mkdocs/`.
+  `modules/latex_pipeline.py` — the seven-stage `.lagda → .lagda.md` conversion proper, including bibliography, label-map, and theorem-block handling.
+  `modules/latex_preprocessor.py` — LaTeX-side preprocessing including FLS-specific macros (Conway/NoConway, hrefCIP, modulenote).
+  `modules/bibtex_processor.py` — citation handling for BibTeX-style references.
+  `modules/site_assembly.py` — MkDocs site assembly including TikZ SVG generation.
+  `agda-filter.lua` — the full FLS Pandoc Lua filter, including FLS-specific HighlightPlaceholder and `\Cref`/`\label`/`\caption` handlers.

## How to read this

Start with `build.py:main()` for the high-level shape, then read `modules/latex_pipeline.py:process_latex_files()` for the conversion-specific stages.  The other modules are called from those two and are easier to understand in context.

## Running it

This pipeline assumes the FLS repository layout (a specific `BuildConfig` with paths into `src/`, `build-tools/static/latex/`, etc.) and is not directly runnable outside that layout.  To use the conversion logic on a different project, prefer the lean `convert_lagda.py` at the repository root.
