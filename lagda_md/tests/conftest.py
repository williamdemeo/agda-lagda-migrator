"""Shared pytest fixtures for lagda_md tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running the tests without installing the package.
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
