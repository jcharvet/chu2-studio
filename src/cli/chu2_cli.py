"""Standalone CLI entry point.

Allows ``python src/cli/chu2_cli.py`` to work without installing the package.
The installed ``chu2`` console script (see pyproject.toml) calls
``chu2.cli.main`` directly and does not need this bootstrap.
"""

from __future__ import annotations

import os
import sys

# Make the ``chu2`` package importable when running from a source checkout.
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from chu2.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
