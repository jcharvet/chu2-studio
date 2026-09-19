"""Standalone GUI entry point.

Allows ``python src/gui/chu2_gui.py`` to work without installing the package.
The installed ``chu2-gui`` console script (see pyproject.toml) calls
``chu2.gui.main`` directly.
"""

from __future__ import annotations

import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from chu2.gui import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
