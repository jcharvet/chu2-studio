"""Start CHU 2 Studio: ``chu2-studio [--fake-device] [--debug] [--smoke-test]``.

One pywebview window (Edge WebView2) shows ``ui/index.html`` through
pywebview's own HTTP server (WebView2 blocks ES modules over ``file://``).
``Api`` is exposed to the page as ``window.pywebview.api``; events go the
other way through :class:`EventPump`, which calls
``window.chu2.onEvent(name, data)`` from its own thread, because
``evaluate_js`` waits for the GUI thread and the device worker must never wait.

``--smoke-test`` (for the packaged ``.exe``) always uses the fake CHU 2 and a
temporary data folder, waits until the page is ready, closes, and exits 0; 1 if
the page never got ready.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import time
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .. import dsp
from ..device_service import DeviceService
from ..fake_device import FakePlug
from ..store import THEMES, Store, default_root
from .api import Api

TITLE = "CHU 2 Studio"
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
UI_INDEX = os.path.join(UI_DIR, "index.html")
#: the window's colour before the page paints, per theme (tokens.css --bg)
THEME_BACKGROUND = dict(zip(THEMES, ("#0A0B0F", "#11111B", "#0E1210", "#DCE0E8", "#EDEAE4")))
_OPEN, _SAVE = 10, 30  # webview.FileDialog.OPEN / SAVE (no pywebview import needed here)

logger = logging.getLogger(__name__)


class EventPump:
    """Delivers ``push(name, data)`` to the page without blocking the caller.

    Runs ``evaluate(script)`` on its own thread. When several ``state``
    snapshots are queued, only the newest is delivered.
    """

    def __init__(self, evaluate: Callable[[str], Any]) -> None:
        self._evaluate = evaluate
        self._queue: "queue.Queue[Optional[Tuple[str, Dict[str, Any]]]]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="chu2-ui-events", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def push(self, name: str, data: Dict[str, Any]) -> None:
        self._queue.put((name, data))

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while True:
            batch: List[Optional[Tuple[str, Dict[str, Any]]]] = [self._queue.get()]
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            states = [i for i, item in enumerate(batch) if item is not None and item[0] == "state"]
            for i, item in enumerate(batch):
                if item is None:
                    return
                if item[0] == "state" and i != states[-1]:
                    continue  # a newer snapshot follows
                self._deliver(*item)

    def _deliver(self, name: str, data: Dict[str, Any]) -> None:
        script = "window.chu2 && window.chu2.onEvent(%s, %s)" % (json.dumps(name), json.dumps(data))
        try:
            self._evaluate(script)
        except Exception:
            logger.exception("could not deliver %r to the page", name)


class Dialogs:
    """The window's native Open / Save dialogs, for ``Api.import_file`` / ``export_file``.

    pywebview runs them on the GUI thread; the calling bridge thread waits.
    """

    def __init__(self, window: Callable[[], Any]) -> None:
        self._window = window

    def open_file(self) -> Optional[str]:
        return _first(self._window().create_file_dialog(
            _OPEN, file_types=("EQ files (*.txt;*.json)", "All files (*.*)")))

    def save_file(self, filename: str, kind: str) -> Optional[str]:
        types = ("Text files (*.txt)",) if kind == "apo" else ("CHU 2 Studio presets (*.json)",)
        return _first(self._window().create_file_dialog(_SAVE, save_filename=filename, file_types=types))


def _first(picked: Any) -> Optional[str]:
    if not picked:
        return None
    return picked if isinstance(picked, str) else str(picked[0])


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="chu2-studio", description=TITLE)
    parser.add_argument("--fake-device", action="store_true",
                        help="use a simulated CHU 2 instead of the real one")
    parser.add_argument("--debug", action="store_true", help="enable the WebView2 dev tools")
    parser.add_argument("--smoke-test", action="store_true",
                        help="start with the fake CHU 2, check the page loads, exit 0 (for the .exe)")
    return parser.parse_args(argv)


def build(push: Callable[[str, Dict[str, Any]], None], close_window: Callable[[], None],
          fake_device: bool = False, store: Optional[Store] = None,
          dialogs: Any = None) -> Tuple[Api, DeviceService]:
    """The Api and its DeviceService, wired together (no window, no thread yet).

    A fake-device run keeps its files in a ``fake-device`` subfolder, so it never
    writes the real first-seen backup, settings or last saved design.
    """
    if store is None:
        store = Store(os.path.join(default_root(), "fake-device")) if fake_device else Store()
    if fake_device:
        plug = FakePlug()
        open_transport, is_present = plug.open, plug.is_present
    else:
        open_transport, is_present = dsp.HidTransport.open, dsp.hid_present
    api = Api(store, push, close_window, dialogs)
    service = DeviceService(open_transport, is_present, api._on_device_event)
    api._attach(service)
    return api, service


def _setup_logging(debug: bool, folder: str) -> None:
    level = logging.DEBUG if debug else logging.INFO
    if getattr(sys, "frozen", False):  # the .exe has no console: log next to the app's files
        os.makedirs(folder, exist_ok=True)
        handler = RotatingFileHandler(os.path.join(folder, "chu2-studio.log"), maxBytes=1_000_000,
                                      backupCount=2, encoding="utf-8")
        logging.basicConfig(level=level, handlers=[handler],
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=level)


def _wait_for_page(window: Any, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if window.evaluate_js("!!document.querySelector(\"[data-ready='true']\")"):
                return True
        except Exception:
            logger.debug("page not ready yet", exc_info=True)
        time.sleep(0.2)
    return False


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    store = Store(tempfile.mkdtemp(prefix="chu2-smoke-")) if args.smoke_test else None
    _setup_logging(args.debug, store.root if store else default_root())
    import webview  # here, so tests and the CLI never need pywebview

    windows: List[Any] = []
    pump = EventPump(lambda script: windows[0].evaluate_js(script))
    api, service = build(pump.push, lambda: windows[0].destroy(),
                         fake_device=args.fake_device or args.smoke_test, store=store,
                         dialogs=Dialogs(lambda: windows[0]))
    theme = api.get_state()["settings"]["theme"]
    window = webview.create_window(TITLE, url=UI_INDEX, js_api=api, width=1280, height=800,
                                   min_size=(1024, 700),
                                   background_color=THEME_BACKGROUND.get(theme, "#0A0B0F"))
    windows.append(window)
    window.events.closing += api._on_window_closing  # False keeps the window open
    page = {"ready": False}

    def on_start() -> None:
        pump.start()
        service.start()
        if args.smoke_test:
            page["ready"] = _wait_for_page(window)
            window.destroy()

    try:
        webview.start(on_start, http_server=True, debug=args.debug)
    finally:
        api._shutdown()
        pump.stop()
    return 0 if page["ready"] or not args.smoke_test else 1


if __name__ == "__main__":
    raise SystemExit(main())
