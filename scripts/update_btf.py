#!/usr/bin/env python3
"""Entry point for the Kylin V10 BTF archive updater.

Runs under ``python -I`` because it parses data downloaded from an external
server; the package directory is added explicitly so isolated mode works.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from kylin_btf.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
