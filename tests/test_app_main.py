"""The window shell without a window: event pump, wiring, flags.

    python -m pytest -q tests/test_app_main.py
"""

import importlib.util
import json
import os
import threading
import time

import pytest

from chu2.app import main as app_main
from chu2.store import THEMES, Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, path):
    """A module that is not in the package (packaging/build_exe.py)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wait(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    return predicate()


def test_pump_delivers_events_in_order_as_page_calls():
    scripts = []
    pump = app_main.EventPump(scripts.append)
    pump.start()
    pump.push("backup_saved", {"saved_at": "2026-09-19T14:02:00"})
    pump.push("close_requested", {"changes": 1})
    assert _wait(lambda: len(scripts) == 2)
    pump.stop()
    assert scripts[0] == ('window.chu2 && window.chu2.onEvent("backup_saved", '
                          '{"saved_at": "2026-09-19T14:02:00"})')
    assert json.loads(scripts[1].split(", ", 1)[1][:-1]) == {"changes": 1}


def test_pump_skips_state_snapshots_that_a_newer_one_replaces():
    gate = threading.Event()
    scripts = []

    def slow_evaluate(script):
        gate.wait(2)
        scripts.append(script)

    pump = app_main.EventPump(slow_evaluate)
    pump.start()
    pump.push("state", {"rev": 1})  # taken at once, blocks in slow_evaluate
    time.sleep(0.05)
    for rev in (2, 3, 4):
        pump.push("state", {"rev": rev})
    pump.push("backup_saved", {"saved_at": "x"})
    gate.set()
    assert _wait(lambda: len(scripts) == 3)
    pump.stop()
    assert ['"rev": 1' in scripts[0], '"rev": 4' in scripts[1], "backup_saved" in scripts[2]] == [True] * 3


def test_pump_survives_a_failing_page_call():
    calls = []

    def flaky(script):
        calls.append(script)
        if len(calls) == 1:
            raise RuntimeError("page not ready")

    pump = app_main.EventPump(flaky)
    pump.start()
    pump.push("a", {})
    pump.push("b", {})
    assert _wait(lambda: len(calls) == 2)
    pump.stop()


def test_stop_without_start_is_safe():
    app_main.EventPump(lambda s: None).stop()


def test_build_with_the_fake_device_connects(tmp_path):
    pushed = []
    api, service = app_main.build(lambda n, d: pushed.append(n), lambda: None, fake_device=True,
                                  store=Store(str(tmp_path)))
    service.run_once(now=0)
    assert api.get_state()["connected"] and "state" in pushed


def test_flags():
    args = app_main.parse_args(["--fake-device", "--debug"])
    assert args.fake_device and args.debug
    assert not app_main.parse_args([]).fake_device


def test_the_page_exists():
    with open(app_main.UI_INDEX, encoding="utf-8") as handle:
        page = handle.read()
    assert '<script type="module" src="app.js"' in page
    assert os.path.isfile(os.path.join(app_main.UI_DIR, "vendor", "vue.esm-browser.prod.js"))


def test_the_fake_device_keeps_its_own_files(tmp_path, monkeypatch):
    """A --fake-device run must never write the real first-seen backup or settings."""
    monkeypatch.setenv("CHU2STUDIO_HOME", str(tmp_path))
    fake_api, _ = app_main.build(lambda n, d: None, lambda: None, fake_device=True)
    real_api, _ = app_main.build(lambda n, d: None, lambda: None)
    assert fake_api._store.root == os.path.join(str(tmp_path), "fake-device")
    assert real_api._store.root == str(tmp_path)


def test_dialogs_use_the_windows_own_open_and_save():
    asked = []

    class Window:
        def __init__(self, answer):
            self.answer = answer

        def create_file_dialog(self, kind, **options):
            asked.append((kind, options))
            return self.answer

    assert app_main.Dialogs(lambda: Window(("C:/eq.txt",))).open_file() == "C:/eq.txt"
    assert app_main.Dialogs(lambda: Window("C:/out.txt")).save_file("Warm.txt", "apo") == "C:/out.txt"
    assert app_main.Dialogs(lambda: Window(None)).open_file() is None
    assert asked[1] == (30, {"save_filename": "Warm.txt", "file_types": ("Text files (*.txt)",)})


def test_dialog_numbers_match_pywebview():
    webview = pytest.importorskip("webview")
    assert (webview.FileDialog.OPEN, webview.FileDialog.SAVE) == (app_main._OPEN, app_main._SAVE)


def test_smoke_test_flag_and_theme_colours():
    assert app_main.parse_args(["--smoke-test"]).smoke_test
    assert set(app_main.THEME_BACKGROUND) == set(THEMES)


def test_the_smoke_test_waits_for_a_cold_webview2():
    """A GitHub runner needed more than 30 s to show the page the first time."""
    build_exe = _load("build_exe", os.path.join(ROOT, "packaging", "build_exe.py"))
    assert app_main.SMOKE_PAGE_TIMEOUT_S >= 90
    # the build script must wait longer than the app, or its message blames the wrong thing
    assert build_exe.SMOKE_TIMEOUT > app_main.SMOKE_PAGE_TIMEOUT_S


def test_a_failed_build_shows_the_last_smoke_log(tmp_path, monkeypatch):
    """A build machine throws its temp folder away, so the message must carry the log."""
    build_exe = _load("build_exe", os.path.join(ROOT, "packaging", "build_exe.py"))
    monkeypatch.setattr(build_exe.tempfile, "gettempdir", lambda: str(tmp_path))
    for name, text, when in (("chu2-smoke-old", "an older run", 1_000), ("chu2-smoke-new", "page never ready", 2_000)):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "chu2-studio.log").write_text(text, encoding="utf-8")
        os.utime(folder, (when, when))
    assert "page never ready" in build_exe.smoke_log()

