"""UI tests: the real page in headless Chromium, Python replaced by a JS mock.

The ``ui`` folder is served on localhost (ES modules need http), and
``mock_api.js`` stands in for ``window.pywebview.api``: it records calls in
``window.__mock.calls``, answers with state snapshots, and can push events.
No pywebview, no Python app, no device.

Needs the dev extra: ``pip install -e ".[dev]"`` and
``python -m playwright install chromium``. Skipped when Playwright is missing.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import threading

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "src", "chu2", "app", "ui"))
MOCK_JS = os.path.join(HERE, "mock_api.js")


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".svg": "image/svg+xml", ".woff2": "font/woff2", ".txt": "text/plain",
    }

    def log_message(self, *args):  # keep test output quiet
        pass


class _Server(http.server.ThreadingHTTPServer):
    # The default listen backlog (5) refuses connections when a busy machine is
    # slow to accept them: the page then misses a module and never gets ready.
    request_queue_size = 128


@pytest.fixture(scope="session")
def ui_url():
    server = _Server(("127.0.0.1", 0), functools.partial(_Handler, directory=UI_DIR))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()


# Seven filters and a preamp: filters 3 and 6 are the smallest, so they are not kept.
APO_TEXT = """Preamp: -6.2 dB
Filter 1: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.70
Filter 2: ON PK Fc 180 Hz Gain -2.1 dB Q 0.80
Filter 3: ON PK Fc 1500 Hz Gain 1.2 dB Q 1.40
Filter 4: ON PK Fc 3200 Hz Gain -3.4 dB Q 2.00
Filter 5: ON PK Fc 5800 Hz Gain 2.6 dB Q 3.00
Filter 6: ON PK Fc 7400 Hz Gain -0.8 dB Q 4.00
Filter 7: ON HSC Fc 10000 Hz Gain -1.9 dB Q 0.70
"""


@pytest.fixture(scope="session")
def mock_library(tmp_path_factory):
    """The real library (chu2.library) with one of "Mine", as the mock serves it,
    and real import previews and a real share code (chu2.transfer, chu2.sharecode)."""
    from chu2 import library, quicktune, sharecode, transfer
    from chu2.app.api import effective_band
    from chu2.store import Store

    lib = library.Library(Store(str(tmp_path_factory.mktemp("library"))))
    lib.save("Night Drive", ["Music"], quicktune.compose("fps", ["sparkle"], "standard")[0])
    presets = lib.presets()
    for item in presets:
        item["on_chu2"] = item["id"] == "mine:night-drive"
    fps = [effective_band(b) for b in quicktune.compose("fps", [], "standard")[0]]
    code = sharecode.encode("FPS", fps)
    return {"presets": presets, "recipes": quicktune.recipes(), "apo_text": APO_TEXT,
            "previews": {"apo": transfer.read_text(APO_TEXT, "HD 600 ParametricEQ.txt"),
                         "code": transfer.read_text(code)},
            "share": {"code": code, "text": sharecode.describe(fps)}}


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def open_app(browser, ui_url, mock_library):
    """open_app(state=None, reduced_motion="no-preference", before_goto=None) -> page, ready.

    ``state`` overrides fields of the mock's first snapshot; ``before_goto(page)``
    can add routes before the page loads. A JavaScript error on the page, or any
    request that leaves the local server, fails the test.
    """
    contexts, errors, outside = [], [], []

    def _open(state=None, reduced_motion="no-preference", before_goto=None):
        context = browser.new_context(viewport={"width": 1280, "height": 688},
                                      reduced_motion=reduced_motion,
                                      permissions=["clipboard-read", "clipboard-write"])
        contexts.append(context)
        page = context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("request", lambda req: None if req.url.startswith((ui_url, "data:"))
                else outside.append(req.url))
        page.add_init_script("window.__mockState = %s;" % json.dumps(state or {}))
        page.add_init_script("window.__mockLibrary = %s;" % json.dumps(mock_library))
        page.add_init_script(path=MOCK_JS)
        if before_goto:
            before_goto(page)
        page.goto(ui_url + "/index.html")
        page.wait_for_selector("[data-ready='true']")
        return page

    yield _open
    for context in contexts:
        context.close()
    assert not errors, errors
    assert not outside, outside  # everything is bundled: the app works offline


@pytest.fixture
def calls():
    """calls(page, method) -> the argument lists of every call the page made to ``method``."""
    def _calls(page, method):
        return page.evaluate(
            "(m) => window.__mock.calls.filter((c) => c[0] === m).map((c) => c.slice(1))", method)
    return _calls
