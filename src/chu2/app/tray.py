"""The tray icon: closing the window hides the app instead of quitting it.

The CHU 2 clicks when its amplifier wakes (test #36), and the silence that stops
that only plays while the app is running. Quitting on every window close made the
switch useless, so the window now hides and the icon stays. **Quit** on the icon's
menu is the only thing that really exits.

``pystray`` and Pillow are imported when the tray starts, not when this module is
imported, so the tests, the CLI and a machine without a tray never need them. It
has to be a plain ``import pystray`` statement: PyInstaller reads those to decide
what to bundle, and a dynamic ``__import__("pystray")`` is invisible to it, which
once shipped an .exe with no tray at all.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

ICON_NAME = "icon.ico"
TITLE = "CHU 2 Studio"


def icon_path() -> Optional[str]:
    """The .ico, wherever this is running from."""
    roots = [getattr(sys, "_MEIPASS", None),
             os.path.dirname(os.path.abspath(sys.executable)),
             os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                          "packaging")]
    for root in roots:
        if not root:
            continue
        candidate = os.path.join(root, ICON_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


class Tray:
    """Wraps pystray. ``backend`` is only replaced by the tests."""

    def __init__(self, on_show: Callable[[], None], on_quit: Callable[[], None],
                 clicking_stopped: Callable[[], bool],
                 set_clicking_stopped: Callable[[bool], None],
                 backend: Any = None) -> None:
        self._on_show = on_show
        self._on_quit = on_quit
        self._stopped = clicking_stopped
        self._set_stopped = set_clicking_stopped
        self._backend = backend
        self._icon: Any = None
        self._thread: Optional[threading.Thread] = None

    # ---- lifecycle ---------------------------------------------------------- #
    def start(self) -> bool:
        """Show the icon. False if this machine cannot, which is not an error."""
        # Everything is inside the guard: a desktop with no tray, a missing Pillow or a
        # backend that raises must leave the app running, just without an icon.
        try:
            if self._backend is not None:
                pystray = self._backend
            else:
                import pystray  # noqa: PLC0415 - a plain import, so PyInstaller bundles it
            menu = pystray.Menu(
                pystray.MenuItem("Show CHU 2 Studio", self._show, default=True),
                pystray.MenuItem("Stop the click before every sound", self._toggle,
                                 checked=lambda _item: self._stopped()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            )
            icon = pystray.Icon("chu2-studio", self._image(), TITLE, menu)
            thread = threading.Thread(target=icon.run, name="chu2-tray", daemon=True)
            thread.start()
        except Exception as exc:
            logger.warning("no tray icon: %s", exc)
            return False
        self._icon, self._thread = icon, thread
        return True

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception as exc:  # pragma: no cover
                logger.warning("could not stop the tray icon: %s", exc)
            self._icon = None

    def notify(self, message: str) -> None:
        """A one-line balloon; ignored where the desktop has no notifications."""
        if self._icon is None:
            return
        try:
            self._icon.notify(message, TITLE)
        except Exception as exc:  # pragma: no cover
            logger.debug("no notification: %s", exc)

    # ---- menu --------------------------------------------------------------- #
    def _show(self, _icon: Any = None, _item: Any = None) -> None:
        self._on_show()

    def _toggle(self, _icon: Any = None, _item: Any = None) -> None:
        self._set_stopped(not self._stopped())

    def _quit(self, _icon: Any = None, _item: Any = None) -> None:
        self.stop()
        self._on_quit()

    # ---- icon --------------------------------------------------------------- #
    def _image(self) -> Any:
        from PIL import Image, ImageDraw

        path = icon_path()
        if path:
            return Image.open(path)
        # ponytail: a plain navy square beats crashing when the .ico is missing.
        image = Image.new("RGB", (64, 64), "#171F67")
        ImageDraw.Draw(image).ellipse((16, 16, 48, 48), fill="#F7F4EF")
        return image
