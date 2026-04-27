<!-- File: docs/corpora/agda-algebras.md -->

# Corpus validation: agda-algebras

This document records the end-to-end validation of `lagda_md`'s Markdown-literate input pipeline against the [agda-algebras](https://github.com/ualib/agda-algebras) corpus, performed for migrator issue [#6](https://github.com/williamdemeo/agda-lagda-migrator/issues/6).  It is the second external-corpus validation of the package, after the formal-ledger-specifications corpus that originally seeded the LaTeX pipeline at `examples/fls-pipeline/`.

##  Corpus snapshot

+  Repository: https://github.com/ualib/agda-algebras
+  Branch: `280-m1-8-apply-agda-lagda-migrator`
+  Source layout at validation time: 127 `.lagda` files under `docs/lagda/`, authored as Markdown prose with `\begin{code}…\end{code}` Agda fences (the agda-algebras and 1Lab convention).
+  Toolchain: Agda 2.8.0, stdlib 2.3, `--cubical-compatible --safe`.

The audit script `scripts/audit_lagda_migration.sh` in the agda-algebras repo classified the corpus as 127 `.lagda` files paired with 127 `.agda` companions under `src/`, of which 3 were skeletons (pragma + module-header only) and 124 were "substantive" by line-count heuristic.  All 124 substantive `.agda` companions were derived mechanically by the project's `admin/illiterator/` Haskell program from their `.lagda` partners, so the `.lagda` files were the single source of truth for both prose and code.

##  Macros encountered

A grep of the corpus body revealed five custom macros beyond `lagda_md`'s always-on baselines (the nine generic `\Agda…{name}` classes plus the `\ab{x}` shorthand):

| Macro    | Frequency | Mapped to                       |
|----------|----------:|---------------------------------|
| `\ab{}`  | 6         | `AgdaBound` (also default-table)|
| `\af{}`  | 3         | `AgdaFunction`                  |
| `\au{}`  | 2         | `AgdaArgument`                  |
| `\as{}`  | 1         | `AgdaSymbol`                    |
| `\ar{}`  | 1         | `AgdaRecord`                    |

Counts derived by:

```sh
grep -rEho '\\[a-zA-Z]+\{' --include='*.lagda' docs/lagda/ | sort | uniq -c | sort -rn
```

The corresponding macro table lives in agda-algebras at `admin/agda-algebras-macros.json` and was passed via `--macros` on the conversion command.

##  Conversion command

```sh
python3 /path/to/agda-lagda-migrator/convert_lagda.py \
    --input-format markdown \
    --macros admin/agda-algebras-macros.json \
    --in-tree docs/lagda/ \
    --out-tree _scratch/converted/
```

Output: `converted 127 of 127 files`.

##  Validation method

The acceptance test for the migrator's correctness on this corpus is end-to-end Agda type-checking of the migrated tree.  After the converted files were placed at their canonical `src/X/Y/Z.lagda.md` paths and the now-redundant `.agda` companions deleted, the corpus's existing `make check` target was run.  This builds `src/Everything.agda` from a `find … *.lagda.md … *.agda` enumeration and invokes Agda on it.

##  Result

`make check` passes.

Excerpt of `make check` output:

```
target: Everything.agda
  wrote src/Everything.agda (127 modules)
target: check
agda +RTS -M6G -A128M -RTS  src/Everything.agda
Checking Everything (…/src/Everything.agda).
 Checking Base (…/src/Base.lagda.md).
…
 Checking agda-algebras (…/src/agda-algebras.lagda.md).
```

All 127 modules of the migrated tree type-check cleanly under the project's `--cubical-compatible --safe` flag set.

##  Findings

###  Migrator behavior was correct

The migrator's Markdown pipeline produced faithful conversions in every case.  The five custom-macro shorthands resolved correctly to kramdown attribute spans of the form `` `name`{.AgdaClass} ``, and code blocks were preserved verbatim under `` ```agda `` fences.  YAML front matter, Markdown headings, reference-style links, and Jekyll directives like `{% include UALib.Links.md %}` were passed through unchanged.

###  Two adjustments required, both narrowly scoped

+  **Corpus-side: `\begin{code}` used for non-type-checked illustrative snippets.**  In a small number of files the corpus author had used `\begin{code}…\end{code}` to wrap explanatory code intended for visual presentation only, with no expectation of compilation.  Under the literate-LaTeX pipeline this worked because `agda --latex` highlights such blocks but the rendered HTML's `make html` was the only consumer; under the new `.lagda.md` shape, every `` ```agda `` fence is consumed by the type-checker.  The corpus maintainer addressed this case-by-case by removing the fences and re-indenting as four-space code blocks, which Markdown renders as monospace without invoking Agda.  The migrator did the right thing — it converted every code fence faithfully — and no migrator change is indicated.
+  **Migrator-side: blank-line padding around code fences.**  The corpus convention was to leave a blank line after `\begin{code}` and before `\end{code}`; the migrator preserves these, producing converted files with an extra blank line between the opening `` ```agda `` fence and the first line of code.  This is cosmetic and does not affect type-checking or rendering correctness, but produces visually noisy output.  Tracked as enhancement [#15](https://github.com/williamdemeo/agda-lagda-migrator/issues/15); a future `--trim-fence-padding` flag would address it.

##  Conclusion

The Markdown-literate pipeline is validated for the agda-algebras shape of corpus.  Of 127 files converted, 127 type-check, with the residual issues identified narrowly scoped (one corpus-side authoring convention; one migrator-side cosmetic enhancement).  The pipeline is fit for production use on similar Markdown-literate Agda corpora.

##  Reproduction

The full migration including the validation step lives on the agda-algebras branch [`280-m1-8-apply-agda-lagda-migrator`](https://github.com/ualib/agda-algebras/tree/280-m1-8-apply-agda-lagda-migrator).  See ualib/agda-algebras#280 for context, [ADR-004](https://github.com/ualib/agda-algebras/blob/master/docs/adr/004-lagda-md-canonical.md) for the design rationale, and the corresponding migrator PR for the kramdown-attribute-span change that landed alongside this validation.


