"""
Macro tables for literate-Agda preprocessing.

A `MacroTable` maps LaTeX macro names (without the leading backslash) to
metadata describing how the macro should be rendered as an Agda term in the
intermediate Pandoc-readable form.  Each entry has two fields:

  basename    The text that should appear as the rendered identifier.
  agda_class  The CSS class used for syntax highlighting in the rendered
              HTML — typically one of AgdaFunction, AgdaField, AgdaDatatype,
              AgdaRecord, AgdaInductiveConstructor, AgdaModule, AgdaPrimitive,
              AgdaBound, AgdaArgument.

JSON serialization
==================

The on-disk representation wraps a macro-name → metadata mapping under a
top-level `agda_terms` key:

    {
      "agda_terms": {
        "AgdaModule":   {"basename": "Foo.Bar.Baz",       "agda_class": "AgdaModule"},
        "hrefAgdaDocs": {"basename": "Agda documentation", "agda_class": "AgdaModule"}
      }
    }

The wrapper exists to leave room for future top-level sections (e.g., for
environment handlers or string replacements) without breaking compatibility
with existing tables.  This is the canonical schema; the same shape is used
by the formal-ledger-specifications worked example.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class MacroEntry:
    """One macro's rendering metadata."""
    basename: str
    agda_class: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, str]) -> MacroEntry:
        try:
            return cls(basename=raw["basename"], agda_class=raw["agda_class"])
        except KeyError as missing:
            raise ValueError(
                f"Macro entry missing required field {missing}; "
                f"got keys {sorted(raw.keys())}"
            ) from None


@dataclass(frozen=True)
class MacroTable:
    """A table of `\\Macro{}` rewrites, keyed by macro name (no backslash)."""
    entries: Mapping[str, MacroEntry] = field(default_factory=dict)

    def __getitem__(self, key: str) -> MacroEntry:
        return self.entries[key]

    def __contains__(self, key: object) -> bool:
        return key in self.entries

    def keys(self):
        return self.entries.keys()

    @classmethod
    def empty(cls) -> MacroTable:
        return cls(entries={})

    @classmethod
    def from_json(cls, path: Path) -> MacroTable:
        """Load a macro table from a JSON file.

        See this module's docstring for the schema; the JSON must have a
        top-level `agda_terms` key whose value maps macro names to entry
        specifications.
        """
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw, source=path)

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, object], *, source: Path | str | None = None
    ) -> MacroTable:
        """Construct a MacroTable from an already-decoded JSON-shaped dict."""
        payload = raw.get("agda_terms")
        if not isinstance(payload, Mapping):
            origin = f" in {source}" if source else ""
            raise ValueError(
                f"Macro table{origin} is missing a top-level `agda_terms` "
                f"key.  Expected schema: "
                f'{{"agda_terms": {{"<macro>": {{"basename": ..., '
                f'"agda_class": ...}}}}}}'
            )

        entries = {
            name: MacroEntry.from_dict(spec)
            for name, spec in payload.items()
            if isinstance(spec, Mapping)
        }
        return cls(entries=entries)

    @classmethod
    def default(cls) -> MacroTable:
        """A small starter table with macros most literate-Agda projects use.

        Loaded lazily from the bundled JSON resource so users can inspect the
        defaults as data rather than reading them out of Python source.
        """
        return cls.from_json(_DEFAULT_MACROS_PATH)

    def merge(self, other: MacroTable) -> MacroTable:
        """Return a new MacroTable in which `other`'s entries override `self`'s."""
        merged = dict(self.entries)
        merged.update(other.entries)
        return MacroTable(entries=merged)


_DEFAULT_MACROS_PATH = Path(__file__).parent / "macros" / "default.json"
