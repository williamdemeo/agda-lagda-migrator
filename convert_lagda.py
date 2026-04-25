#!/usr/bin/env python3
"""Convenience wrapper for ``python3 -m lagda_md``.

This script lets you run the converter as ``./convert_lagda.py ...``
without installing the package.  Equivalent to ``python3 -m lagda_md``.
"""
from __future__ import annotations

import sys

from lagda_md.cli import main


if __name__ == "__main__":
    sys.exit(main())
