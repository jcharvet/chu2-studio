"""Start CHU 2 Studio when Windows starts.

The app lives in the tray, and the silence that stops the CHU 2 clicking
(:mod:`chu2.keepawake`) only plays while it runs, so "start at login" is what
makes that stick. One value under Windows' own ``Run`` key: no shortcut, no COM,
no service, and removing the value is the whole of turning it off.

``winreg`` is standard library on Windows and missing elsewhere, so
:func:`available` is False there and the switch is disabled.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import List, Optional

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CHU 2 Studio"

try:  # pragma: no cover - the import is the platform check
    import winreg as _winreg
except ImportError:  # pragma: no cover
    _winreg = None  # type: ignore

winreg = _winreg


def available() -> bool:
    return winreg is not None


def command() -> str:
    """What Windows should run: the .exe once frozen, this module in development."""
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable])
    return subprocess.list2cmdline([sys.executable, "-m", "chu2.app.main"])


def enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return True


def enable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
    except OSError as exc:
        logger.warning("could not set the login entry: %s", exc)
        return False
    return True


def disable() -> None:
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
    except OSError as exc:  # pragma: no cover
        logger.warning("could not remove the login entry: %s", exc)
