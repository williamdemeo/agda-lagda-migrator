"""Tests for lagda_md.macros."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lagda_md.macros import MacroEntry, MacroTable


class TestMacroEntry:
    def test_from_dict_with_required_fields(self):
        e = MacroEntry.from_dict({"basename": "Foo", "agda_class": "AgdaModule"})
        assert e.basename == "Foo"
        assert e.agda_class == "AgdaModule"

    def test_from_dict_missing_basename_raises(self):
        with pytest.raises(ValueError, match="basename"):
            MacroEntry.from_dict({"agda_class": "AgdaModule"})

    def test_from_dict_missing_agda_class_raises(self):
        with pytest.raises(ValueError, match="agda_class"):
            MacroEntry.from_dict({"basename": "Foo"})


class TestMacroTableLoading:
    def test_empty(self):
        t = MacroTable.empty()
        assert len(list(t.keys())) == 0

    def test_default_loads(self):
        # The bundled default JSON should load and contain at least one entry.
        t = MacroTable.default()
        assert len(list(t.keys())) >= 1

    def test_from_dict_nested_schema(self):
        raw = {
            "agda_terms": {
                "AgdaModule": {"basename": "Foo", "agda_class": "AgdaModule"},
                "myref": {"basename": "", "agda_class": "AgdaFunction"},
            }
        }
        t = MacroTable.from_dict(raw)
        assert "AgdaModule" in t
        assert "myref" in t
        assert t["AgdaModule"].basename == "Foo"

    def test_from_dict_flat_schema_is_rejected(self):
        flat = {
            "AgdaModule": {"basename": "Foo", "agda_class": "AgdaModule"},
        }
        with pytest.raises(ValueError, match="agda_terms"):
            MacroTable.from_dict(flat)

    def test_from_dict_missing_agda_terms_is_rejected(self):
        with pytest.raises(ValueError, match="agda_terms"):
            MacroTable.from_dict({})

    def test_from_json_roundtrip(self, tmp_path: Path):
        path = tmp_path / "m.json"
        path.write_text(
            json.dumps(
                {
                    "agda_terms": {
                        "X": {"basename": "X", "agda_class": "AgdaFunction"}
                    }
                }
            )
        )
        t = MacroTable.from_json(path)
        assert "X" in t

    def test_merge_other_overrides_self(self):
        a = MacroTable.from_dict(
            {
                "agda_terms": {
                    "X": {"basename": "old", "agda_class": "AgdaModule"}
                }
            }
        )
        b = MacroTable.from_dict(
            {
                "agda_terms": {
                    "X": {"basename": "new", "agda_class": "AgdaModule"}
                }
            }
        )
        merged = a.merge(b)
        assert merged["X"].basename == "new"

    def test_from_dict_non_mapping_entry_is_rejected(self):
        raw = {
            "agda_terms": {
                "AgdaModule": "not a dict",
            }
        }
        with pytest.raises(ValueError, match="invalid entry for macro"):
            MacroTable.from_dict(raw)
